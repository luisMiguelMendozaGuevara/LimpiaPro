"""Parser del formato winapp2.ini con deteccion y exclusiones.

Subconjunto soportado:
  [Aplicacion]
  Detect=HKCU\\Software\\Algo        (condicion singular, por compatibilidad)
  Detect1=HKLM\\...                  (indexadas: TODAS deben cumplirse)
  DetectFile1=%LocalAppData%\\Algo*  (detect por archivo, admite comodines)
  SpecialDetect=DET_XXX              (interno de CCleaner: se descarta)
  FileKey1=ruta|mascara[;mascara...]|RECURSE|REMOVESELF
  ExcludeKey1=ruta|mascara[;mascara...]   (protege archivos del borrado)

La deteccion esta separada del parseo para poder testear el parser sin
tocar el registro ni el disco.
"""

import fnmatch
import os
import re
import winreg

from .utils import app_dir, glob_like

_HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKU": winreg.HKEY_USERS,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
}

_DETECT_RE = re.compile(r"^(detect|detectfile)\d*$", re.IGNORECASE)


def _split_masks(masks):
    """Lista de mascaras separadas por ; o , (vacio = todo)."""
    out = []
    for m in masks.replace(";", ",").split(","):
        m = m.strip()
        if m == "*.*":
            m = "*"  # semantica DOS: cualquier archivo, con o sin extension
        if m:
            out.append(m)
    return out or ["*"]


class ExcludeKey:
    """Exclusion de archivos: lo que casa con (raiz, mascaras) no se borra.

    Una raiz que termina en '\\*' excluye de forma recursiva. La variante
    'FILE|ruta' excluye un archivo exacto; la variante 'REG|...' se ignora
    porque la app no borra registro desde reglas winapp2."""

    __slots__ = ("root", "patterns", "recursive", "exact")

    def __init__(self, root="", patterns=("*",), recursive=False, exact=None):
        self.root = os.path.normcase(os.path.abspath(root)) if root else ""
        self.patterns = tuple(patterns)
        self.recursive = recursive
        self.exact = (os.path.normcase(os.path.abspath(exact))
                      if exact else None)

    @classmethod
    def parse(cls, val):
        parts = [p.strip() for p in val.split("|")]
        if not parts or not parts[0]:
            return None
        head = parts[0]
        if head.upper() == "REG":
            return None
        if head.upper() == "FILE" and len(parts) >= 2:
            exact = os.path.expandvars(parts[1])
            return cls(exact=exact) if exact else None
        root = os.path.expandvars(head)
        masks = parts[1] if len(parts) > 1 else ""
        recursive = root.endswith("\\*") or root.endswith("/*")
        if recursive:
            root = root[:-2]
        return cls(root=root, patterns=_split_masks(masks), recursive=recursive)

    def matches(self, path):
        """True si `path` (ya normalizado con normcase+abspath) queda protegido."""
        if self.exact is not None:
            return path == self.exact
        if not self.root:
            return False
        parent = os.path.dirname(path)
        name = os.path.basename(path)
        if self.recursive:
            inside = parent == self.root or parent.startswith(self.root + os.sep)
        else:
            inside = parent == self.root
        if not inside:
            return False
        return any(fnmatch.fnmatch(name, p) for p in self.patterns)


class WinAppRule:
    __slots__ = ("root", "recurse", "patterns", "remove_self", "excludes")

    def __init__(self, root, recurse=False, patterns=("*",),
                 remove_self=False, excludes=()):
        self.root = root
        self.recurse = recurse
        self.patterns = tuple(patterns)
        self.remove_self = remove_self
        self.excludes = tuple(excludes)

    def is_excluded(self, path):
        if not self.excludes:
            return False
        norm = os.path.normcase(os.path.abspath(path))
        return any(ex.matches(norm) for ex in self.excludes)


def _parse_filekey(val, excludes):
    """Parsea 'ruta|mascaras|OPCION' (OPCION: RECURSE o REMOVESELF).

    Una ruta terminada en '\\*' tambien marca recursion (el '*' no puede
    formar parte de un nombre real de carpeta en Windows)."""
    parts = [p.strip() for p in val.split("|")]
    root = parts[0] if parts else ""
    if not root:
        return None
    star_tail = root.endswith("\\*") or root.endswith("/*")
    if star_tail:
        root = root[:-2]
    masks = parts[1] if len(parts) > 1 else ""
    option = parts[2] if len(parts) > 2 else ""
    # tolerar 'ruta|RECURSE' sin mascaras
    if masks.upper() in ("RECURSE", "REMOVESELF") and not option:
        option = masks
        masks = ""
    recurse = option.lower() == "recurse" or star_tail
    remove_self = option.lower() == "removeself"
    return WinAppRule(root, recurse=recurse, patterns=_split_masks(masks),
                      remove_self=remove_self, excludes=excludes)


def parse_sections(text):
    """Parsea el texto de un winapp2.ini a secciones (sin comprobar
    deteccion). Devuelve una lista de {'name','detects','special','rules'}
    donde las reglas llevan aplicadas las ExcludeKey de su seccion."""
    sections = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            if name:
                current = {"name": name, "detects": [], "special": False,
                           "filekeys": [], "excludes": []}
                sections.append(current)
            continue
        if current is None or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if not key or not val:
            continue
        low = key.lower()
        if low.startswith("filekey"):
            current["filekeys"].append(val)
        elif low.startswith("excludekey"):
            ex = ExcludeKey.parse(val)
            if ex is not None:
                current["excludes"].append(ex)
        elif _DETECT_RE.match(low):
            current["detects"].append(val)
        elif low == "specialdetect":
            current["special"] = True
    for s in sections:
        rules = []
        for fk in s["filekeys"]:
            rule = _parse_filekey(fk, s["excludes"])
            if rule is not None:
                rules.append(rule)
        s["rules"] = rules
        del s["filekeys"]
        del s["excludes"]
    return sections


def detect_true(condition):
    """Comprueba una condicion Detect=/DetectFile= del formato winapp2."""
    d = (condition or "").strip()
    if not d:
        return True
    try:
        low = d.lower()
        if low.startswith("file"):
            d = d[len("file"):].strip()
        if "\\" in d:
            hive_name, sub = d.split("\\", 1)
            hive = _HIVES.get(hive_name.upper())
            if hive is not None:
                try:
                    with winreg.OpenKey(hive, os.path.expandvars(sub)):
                        return True
                    return False
                except OSError:
                    return False
        d = os.path.expandvars(d)
        return any(os.path.exists(h) for h in glob_like(d))
    except Exception:
        return False


def active_sections(sections):
    """Filtra las secciones cuya deteccion se cumple.

    Varias Detect/Detect1..N se combinan con AND (formato winapp2): la
    seccion solo aplica si TODAS se cumplen. Las secciones con solo
    SpecialDetect (interno de CCleaner) se descartan."""
    out = []
    for s in sections:
        if not s["rules"]:
            continue
        if s["special"] and not s["detects"]:
            continue
        if all(detect_true(d) for d in s["detects"]):
            out.append(s)
    return out


def default_winapp_file():
    return os.path.join(app_dir(), "winapp2.ini")


def parse_winapp_rules(path):
    """Parsea un archivo winapp2.ini y devuelve las secciones activas
    (apps detectadas como instaladas): [{'name','detects','rules'}]."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    return active_sections(parse_sections(text))
