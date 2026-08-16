"""Categorias de limpieza: ubicaciones del sistema y reglas winapp2."""

import fnmatch
import os
import threading

from .utils import (PROGRESS_DELETE, PROGRESS_RULES, _delete_path,
                    _fast_folder_stats, _parallel_map, _safe_size, glob_like)
from .winapp2 import default_winapp_file, parse_winapp_rules


def user_dirs():
    return {
        "temp": r"%TEMP%",
        "win_temp": r"C:\Windows\Temp",
        "prefetch": r"C:\Windows\Prefetch",
        "recent": r"%APPDATA%\Microsoft\Windows\Recent",
        "explorer_cache": r"%LOCALAPPDATA%\Microsoft\Windows\Explorer",
        "edge": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
        "chrome": r"%LOCALAPPDATA%\Google\Chrome\User Data",
        "brave": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",
        "vivaldi": r"%LOCALAPPDATA%\Vivaldi\User Data",
        "opera": r"%APPDATA%\Opera Software\Opera Stable",
        "opera_gx": r"%APPDATA%\Opera Software\Opera GX Stable",
        "firefox": r"%APPDATA%\Mozilla\Firefox\Profiles",
        "update_cache": r"C:\Windows\SoftwareDistribution\Download",
        "cbs_logs": r"C:\Windows\Logs\CBS",
        "dump": r"%LOCALAPPDATA%\CrashDumps",
    }


def browser_cache_folders(base):
    cache_folders = [
        "Cache", "Cache/Cache_Data", "Code Cache", "Code Cache/JS Cache",
        "GPUCache", "Service Worker/CacheStorage", "Service Worker/ScriptCache",
        "GrShaderCache", "ShaderCache", "DawnCache", "DawnGraphiteCache",
        "DawnWebGPUCache", "blob_storage", "CachedData",
    ]
    result = []
    if not os.path.isdir(base):
        return result
    try:
        for entry in os.listdir(base):
            p = os.path.join(base, entry)
            if not os.path.isdir(p):
                continue
            for cf in cache_folders:
                result.append(os.path.join(p, cf))
    except OSError:
        pass
    return result


class CleanCategory:
    """Una categoria de limpieza con sus ubicaciones de origen."""

    def __init__(self, key, label, description, locations, icon="\U0001F5D1"):
        self.key = key
        self.label = label
        self.description = description
        self.locations = locations
        self.icon = icon
        self.needs_admin = False
        self.recycle_bin = False
        self.rules = None
        self.size = 0
        self.files = 0
        self.errors = 0

    def _locations_existing(self):
        out = []
        for loc in self.locations:
            for h in glob_like(os.path.expandvars(loc)):
                if os.path.exists(h):
                    out.append(h)
        return out

    @staticmethod
    def _match_name(name, patterns_lower):
        if not patterns_lower:
            return True
        low = name.lower()
        for p in patterns_lower:
            if fnmatch.fnmatch(low, p):
                return True
        return False

    def _rule_roots(self):
        """Genera (regla, raiz_existente) para cada regla winapp2.

        La raiz se normaliza y absolutiza una sola vez aqui: is_excluded
        (winapp2) recibe rutas absolutas y solo aplica normcase, evitando
        una llamada GetFullPathName por archivo."""
        for rule in self.rules or []:
            root = os.path.normcase(os.path.abspath(
                os.path.expandvars(rule.root)))
            if os.path.exists(root):
                yield rule, root

    def _iter_targets(self):
        """Itera (regla_o_None, ruta) de todo lo que la categoria limpiaria.

        Un unico recorrido para escanear, listar y borrar. En las reglas
        winapp2 se aplican mascaras, recursion y exclusiones ExcludeKey;
        en las categorias normales solo se toca el nivel superior de cada
        ubicacion (las carpetas se eliminan enteras al limpiar)."""
        if self.rules:
            for rule, root in self._rule_roots():
                if os.path.isfile(root):
                    if (self._match_name(os.path.basename(root), rule.patterns_lower)
                            and not rule.is_excluded(root)):
                        yield rule, root
                    continue
                for cur, dirs, fnames in os.walk(root):
                    if not rule.recurse:
                        dirs[:] = []
                    for name in fnames:
                        path = os.path.join(cur, name)
                        if (self._match_name(name, rule.patterns_lower)
                                and not rule.is_excluded(path)):
                            yield rule, path
        else:
            for loc in self._locations_existing():
                if os.path.isdir(loc):
                    try:
                        for name in os.listdir(loc):
                            yield None, os.path.join(loc, name)
                    except OSError:
                        pass
                else:
                    yield None, loc

    def _scan_rules(self, on_progress=None):
        # Cada categoria se escanea en su propio hilo; dentro se recorren las
        # raices en serie (el paralelismo aqui no gana en disco de uso normal).
        self.size = 0
        self.files = 0
        for _rule, path in self._iter_targets():
            self.size += _safe_size(path)
            self.files += 1
            if on_progress and self.files % PROGRESS_RULES == 0:
                on_progress(self.files)
        return self.size

    def scan(self, on_progress=None):
        if self.rules:
            return self._scan_rules(on_progress)
        self.size = 0
        self.files = 0
        for loc in self._locations_existing():
            if os.path.isdir(loc):
                size, files = _fast_folder_stats(loc, on_progress)
                self.size += size
                self.files += files
            else:
                self.files += 1
                try:
                    self.size += os.path.getsize(loc)
                except OSError:
                    pass
        return self.size

    def list_files(self, limit=1000):
        """Devuelve (rutas, numero_escaneado) para la vista previa.

        La cuenta escaneada se detiene al llegar al limite (`len(files)
        <= limit`), no es el total real de objetivos."""
        files = []
        scanned = 0
        for _rule, path in self._iter_targets():
            scanned += 1
            files.append(path)
            if len(files) >= limit:
                break
        return files, scanned

    def clean(self, on_file=None, on_progress=None, target_bytes=0):
        # Recolectar objetivos en un unico pase y borrarlos en paralelo.
        # (para categorias normales solo se borra el nivel superior de cada
        # ubicacion; las carpetas se eliminan enteras con rmtree).
        targets = []
        remove_roots = []
        for rule, path in self._iter_targets():
            targets.append(path)
            if rule is not None and rule.remove_self:
                root = os.path.abspath(os.path.expandvars(rule.root))
                if root not in remove_roots:
                    remove_roots.append(root)
        # Evitar doble borrado si dos reglas/ubicaciones solapan.
        targets = list(dict.fromkeys(targets))
        if on_file:
            for t in targets:
                on_file(t)

        lock = threading.Lock()
        state = {"removed": 0, "errors": 0, "freed": 0, "done": 0}

        def _delete_one(target):
            size = _safe_size(target)
            ok = _delete_path(target)
            with lock:
                state["done"] += 1
                if ok:
                    state["removed"] += 1
                    state["freed"] += size
                else:
                    state["errors"] += 1
                done, freed = state["done"], state["freed"]
            # Progreso troceado para no saturar la GUI con after(0, ...).
            if on_progress and target_bytes > 0 and done % PROGRESS_DELETE == 0:
                on_progress(min(freed / target_bytes, 1.0))

        _parallel_map(_delete_one, targets)

        # REMOVESELF: eliminar la carpeta de la regla si ha quedado vacia.
        for root in remove_roots:
            try:
                os.rmdir(root)
            except OSError:
                pass

        removed = state["removed"]
        errors = state["errors"]
        freed = state["freed"]
        # No re-escanear aqui: la UI re-analiza todo al terminar la limpieza
        # (analyze_all). Aproximar hasta ese refresh evita un recorrido extra.
        self.size = max(0, self.size - freed)
        self.files = removed
        self.errors = errors
        return removed, errors, freed


def build_categories():
    d = user_dirs()
    cats = []

    cat_temp = CleanCategory(
        "temp", "Archivos temporales del sistema",
        "TEMP de usuario y sistema, Prefetch",
        [d["temp"], d["win_temp"], d["prefetch"]], "\U0001F4DA")
    cat_temp.needs_admin = True
    cats.append(cat_temp)

    browser_locations = []
    for key in ("edge", "chrome", "brave", "vivaldi"):
        base = os.path.expandvars(d[key])
        browser_locations.extend(browser_cache_folders(base))
    # Opera / Opera GX (estructura: perfil/Cache)
    for key in ("opera", "opera_gx"):
        base = os.path.expandvars(d[key])
        if os.path.isdir(base):
            browser_locations.append(os.path.join(base, "Cache"))
            browser_locations.append(os.path.join(base, "GPUCache"))
    for profile in glob_like(os.path.expandvars(os.path.join(d["firefox"], "*"))):
        browser_locations.append(os.path.join(profile, "cache2"))
    cat_browser = CleanCategory(
        "browser", "Cache de navegadores",
        "Edge, Chrome, Brave, Vivaldi, Opera, Opera GX y Firefox",
        browser_locations, "\U0001F310")
    cats.append(cat_browser)

    cat_bin = CleanCategory(
        "recycle", "Papelera de reciclaje",
        "Vacia la papelera del sistema",
        [], "\U0001F5DE")
    cat_bin.recycle_bin = True
    cats.append(cat_bin)

    cat_apps = CleanCategory(
        "apps", "Cache de aplicaciones y logs",
        "Miniaturas, CrashDumps, Windows Update, logs CBS",
        [d["explorer_cache"], d["dump"], d["update_cache"], d["cbs_logs"]],
        "\U00002699")
    cat_apps.needs_admin = True
    cats.append(cat_apps)

    cat_hist = CleanCategory(
        "history", "Historial reciente",
        "Elementos recientes del menu Inicio",
        [d["recent"]], "\U0001F551")
    cats.append(cat_hist)

    rules = (parse_winapp_rules(default_winapp_file())
             if os.path.exists(default_winapp_file()) else [])
    cat_winapp = CleanCategory(
        "winapp", "Aplicaciones (reglas winapp2)",
        ("Base de datos comunitaria winapp2.ini: "
         + (f"{len(rules)} apps detectadas" if rules else "sin reglas cargadas")),
        [], "\U0001F4E6")
    cat_winapp.rules = [r2 for s in rules for r2 in s.rules]
    cat_winapp.needs_admin = True
    cats.append(cat_winapp)

    return cats
