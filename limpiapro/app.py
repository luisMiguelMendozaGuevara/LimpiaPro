"""Aplicacion principal de LimpiaPro."""

import ctypes
import json
import os
import sys
import threading
import traceback
import tkinter as tk

import customtkinter as ctk
from tkinter import filedialog, messagebox

from . import APP_NAME, APP_VERSION
from .categories import build_categories
from .recycle import empty_recycle_bin, recycle_bin_size
from .utils import _errlog, app_dir, format_size, is_admin
from .winapp2 import default_winapp_file, parse_winapp_rules
from .winstyle import apply_mica_backdrop, fluent_font, get_system_accent
from .ui.clean_page import CleanPage
from .ui.duplicates_page import DuplicatePage
from .ui.log_page import LogPage
from .ui.startup_page import StartupPage
from .ui.uninstall_page import UninstallPage
from .ui.update_page import UpdatePage


class CleanerApp(ctk.CTk):
    CACHE_FILE = os.path.join(app_dir(), "limpiador_cache.json")

    def __init__(self):
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.title(f"{APP_NAME} {APP_VERSION} - Limpiador de sistema")
        _errlog("init: window creada")
        self.geometry("1000x680")
        self.minsize(860, 560)
        self.configure(fg_color=("#e8e8e8", "#17181c"))

        ctk.set_appearance_mode("dark")
        self.accent = get_system_accent()
        # Fondo Mica (Windows 11 22H2+). Solo se vuelve transparente la
        # ventana cuando el sistema soporta el material translucido.
        self.mica = apply_mica_backdrop(self)
        if not self.mica:
            self.configure(fg_color=("#e8e8e8", "#17181c"))

        self.categories = build_categories()
        self.scanner = None
        self.busy = False
        self.clean_page_active = False

        # Debounce de redimension: no forzar un repintado por cada evento <Configure>
        self._resize_job = None
        self.bind("<Configure>", self._on_configure)

        self._build_sidebar()
        self._pages = {}
        self.show_page("clean")

        self.log(f"{APP_NAME} {APP_VERSION} iniciado. " +
                 ("(administrador)" if is_admin() else "(sin admin)"))
        self.after(300, self.analyze_all)

    def report_callback_exception(self, exc, val, tb):
        _errlog("CALLBACK EXCEPTION: " + "".join(traceback.format_exception(exc, val, tb)))
        try:
            super().report_callback_exception(exc, val, tb)
        except Exception:
            pass

    def _on_close(self):
        _errlog("cerrando por usuario o WM_CLOSE")
        self.destroy()

    def _on_configure(self, event):
        if event.widget is not self:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(200, self._resize_debounced)

    def _resize_debounced(self):
        self._resize_job = None
        self.update_idletasks()

    # ------------------------------------------------------------------ layout

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=("#d9d9d9", "#222327"))
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)
        self.sidebar.pack_propagate(False)

        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=16, pady=(18, 10))
        ctk.CTkLabel(logo, text="\U0001F9F9", font=ctk.CTkFont(size=30)).pack(side="left")
        ctk.CTkLabel(logo, text=APP_NAME, font=fluent_font(18, "bold")).pack(side="left", padx=8)

        self.nav_buttons = {}
        nav_items = [
            ("clean", "\U0001F9F9  Limpieza"),
            ("startup", "\U0001F4C8  Inicio"),
            ("dupes", "\U0001F50D  Duplicados"),
            ("update", "\U0001F504  Windows Update"),
            ("uninstall", "\U0001F5D1  Desinstalar"),
            ("log", "\U0001F4DD  Registro"),
        ]
        for key, text in nav_items:
            btn = ctk.CTkButton(self.sidebar, text=text, anchor="w", height=38,
                                corner_radius=8, font=fluent_font(13),
                                fg_color="transparent", hover_color=("#c3c3c3", "#2e2f35"),
                                command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = btn

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True)

        # pie de barra lateral: modo claro/oscuro
        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=14, pady=14)
        self.theme_mode = ctk.StringVar(value=ctk.get_appearance_mode().lower())
        self._theme_animating = False

        def _toggle():
            if self._theme_animating:
                return
            self._theme_target = self.theme_mode.get()
            sw.configure(state="disabled")
            self._theme_animating = True
            self._fade_to(0.08, ready=self._apply_theme)

        self.theme_switch = None

        sw = ctk.CTkSwitch(footer, text="Modo oscuro", variable=self.theme_mode,
                           onvalue="dark", offvalue="light", command=_toggle)
        sw.pack(anchor="w")
        self.theme_switch = sw

    def _fade_to(self, target_alpha, ready=None):
        """Anima la opacidad de la ventana. Al terminar llama a ready()."""
        steps = 10
        step_ms = 20
        start = float(self.attributes("-alpha"))
        delta = (target_alpha - start) / steps

        def step(i):
            if i >= steps:
                if ready:
                    ready()
                else:
                    self.attributes("-alpha", 1.0)
                return
            self.attributes("-alpha", start + delta * i)
            self.after(step_ms, lambda: step(i + 1))

        step(0)

    def _apply_theme(self):
        m = self.theme_mode.get()
        ctk.set_appearance_mode(m)
        self._restyle_tree()
        self.after(60, self._finish_theme)

    def _finish_theme(self):
        m = self.theme_mode.get()
        self.theme_switch.configure(text="Modo oscuro" if m == "dark" else "Modo claro",
                                    state="normal")
        self._fade_to(1.0)
        self._theme_animating = False

    def _highlight_nav(self, active_key):
        accent = getattr(self, "accent", "#0067c0")
        for key, btn in self.nav_buttons.items():
            if key == active_key:
                btn.configure(fg_color=accent, hover_color=accent, text_color="white")
            else:
                btn.configure(fg_color="transparent", hover_color=("#c3c3c3", "#2e2f35"))
                if ctk.get_appearance_mode().lower() == "dark":
                    btn.configure(text_color="white")
                else:
                    btn.configure(text_color="black")

    def _restyle_tree(self):
        """Aplica colores del tema a los arboles (ttk no sigue
        automaticamente el modo claro/oscuro)."""
        style = tk.ttk.Style()
        dark = ctk.get_appearance_mode().lower() == "dark"
        bg = "#1c1c1e" if dark else "#f5f5f5"
        fg = "white" if dark else "black"
        try:
            style.theme_use("clam")
            style.configure("Dup.Treeview", background=bg, fieldbackground=bg,
                            foreground=fg, borderwidth=0, rowheight=22)
            style.configure("Dup.Treeview.Heading", background="#33363a" if dark else "#e5e5e5",
                            foreground="white" if dark else "black",
                            relief="flat", font=("Segoe UI", 10, "bold"))
            style.map("Dup.Treeview", background=[("selected", "#2e7d32")])
        except Exception:
            pass

    def _get_page(self, key):
        if key not in self._pages:
            if key == "clean":
                self._pages["clean"] = CleanPage(self.content, self)
            elif key == "startup":
                self._pages["startup"] = StartupPage(self.content, self)
            elif key == "dupes":
                self._pages["dupes"] = DuplicatePage(self.content, self)
            elif key == "update":
                self._pages["update"] = UpdatePage(self.content, self)
            elif key == "uninstall":
                self._pages["uninstall"] = UninstallPage(self.content, self)
            else:
                self._pages["log"] = LogPage(self.content, self)
            self._pages[key].pack_forget()
        return self._pages[key]

    def show_page(self, key):
        page = self._get_page(key)
        if getattr(self, "_current_page", None) is not None and self._current_page is not page:
            self._current_page.pack_forget()
        page.pack(fill="both", expand=True)
        self._current_page = page
        self._highlight_nav(key)

    @property
    def pages_clean(self):
        return self._get_page("clean")

    @property
    def pages_dupes(self):
        return self._get_page("dupes")

    @property
    def log_page(self):
        return self._get_page("log")

    # ------------------------------------------------------------------ log / estado

    def log(self, msg):
        self.log_page.log(msg)

    def set_status(self, text):
        self.pages_clean.status_lbl.configure(text=text)

    def set_busy(self, value, mode="determinate"):
        self.busy = value
        state = "disabled" if value else "normal"
        self.pages_clean.clean_btn.configure(state=state)
        self.pages_clean.progress.stop()
        if value:
            self.pages_clean.progress.configure(mode=mode)
            if mode == "indeterminate":
                self.pages_clean.progress.start()
        else:
            self.pages_clean.progress.configure(mode="determinate")
            self.pages_clean.progress.set(1)

    # ------------------------------------------------------------------ analizar

    def _load_cache(self):
        try:
            with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cache(self):
        data = {c.key: {"size": c.size, "files": c.files} for c in self.categories}
        try:
            tmp = self.CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.CACHE_FILE)
        except Exception:
            pass

    def analyze_all(self):
        if self.busy:
            return
        # Mostrar resultados en cache inmediatamente (inicio instantaneo)
        self._apply_cache()
        self.set_busy(True)
        self.set_status("Analizando sistema...")
        threading.Thread(target=self._analyze_worker, daemon=True).start()

    def load_winapp_rules(self):
        path = filedialog.askopenfilename(
            title="Seleccionar archivo de reglas winapp2",
            filetypes=[("winapp2.ini", "*.ini"), ("Todos los archivos", "*.*")])
        if not path:
            return
        rules = parse_winapp_rules(path)
        found = False
        for c in self.categories:
            if c.key == "winapp":
                c.rules = [r2 for s in rules for r2 in s["rules"]]
                c.description = ("Base de datos comunitaria winapp2.ini: "
                                 + (f"{len(rules)} apps detectadas"
                                    if rules else "sin reglas detectadas"))
                found = True
                break
        if found:
            self.pages_clean._build_rows()
        if rules:
            self.log(f"Reglas winapp2 cargadas: {len(rules)} aplicaciones de {path}")
            self.set_status(f"{len(rules)} aplicaciones con reglas cargadas")
        else:
            self.log("No se detectaron reglas validas en el archivo seleccionado.")
            messagebox.showinfo(APP_NAME,
                                "No se detectaron reglas validas (o ningun programa "
                                "coincide con las condiciones Detect=).")
        self.after(100, self.analyze_all)

    def _apply_cache(self):
        cached = self._load_cache()
        for cat in self.categories:
            entry = cached.get(cat.key)
            if entry:
                cat.size = entry.get("size", 0)
                cat.files = entry.get("files", 0)
                self.after(0, self._analyze_one_done, cat)

    def _analyze_worker(self):
        # Un solo pase de escaneo, categorias en paralelo (hilos).
        # El progreso se calcula con los archivos escaneados / objetivo estimado
        # (cache anterior si existe; si no, indeterminada).
        targets = {c.key: max(c.files, 1) for c in self.categories}
        total_target = sum(targets.values())
        progress = {"done": 0}
        lock = threading.Lock()

        def cb(cat, n):
            with lock:
                progress["done"] = (progress["done"] - progress.get(cat.key, 0)
                                    + n)
                progress[cat.key] = n
                frac = progress["done"] / total_target
            self.after(0, self._analyze_progress, cat, frac)

        threads = []
        for cat in self.categories:
            def work(c=cat):
                if c.recycle_bin:
                    c.size = recycle_bin_size()
                    c.files = 0
                else:
                    c.scan(on_progress=lambda n, cc=c: cb(cc, n))
                self.after(0, self._analyze_one_done, c)
            t = threading.Thread(target=work, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        self._save_cache()
        self.after(0, self._analyze_all_done)

    def _analyze_progress(self, cat, frac):
        if self.busy:
            self.pages_clean.progress.configure(mode="determinate")
            self.pages_clean.progress.set(min(frac, 1.0))
            self.set_status(f"Analizando: {cat.label} ...")

    def _analyze_one_done(self, cat):
        self.pages_clean.update_after_scan(cat)

    def _analyze_all_done(self):
        self.set_busy(False)
        self.clean_page_active = False
        self.set_status("Analisis completado")
        self.update_total()
        _errlog("analisis completado")

    # ------------------------------------------------------------------ total

    def update_total(self):
        total = sum(c.size for c in self.categories if self.pages_clean.vars[c.key].get())
        self.pages_clean.total_lbl.configure(
            text=f"Total seleccionado: {format_size(total)}")

    # ------------------------------------------------------------------ limpiar

    def confirm_clean(self):
        selected = [c for c in self.categories if self.pages_clean.vars[c.key].get()]
        if not selected:
            messagebox.showinfo(APP_NAME, "No hay ninguna categoria seleccionada.")
            return
        total = sum(c.size for c in selected)
        names = "\n".join(f"  \u2022 {c.label}" for c in selected)
        detail = "Se eliminaran definitivamente los archivos temporales, la cache y el historial.\n"
        if any(c.recycle_bin for c in selected):
            detail += "\nATENCION: se vaciara la PAPELERA DE RECICLAJE.\n"
        if any(c.needs_admin for c in selected) and not is_admin():
            detail += "\nAVISO: se requiere ejecutar como administrador para limpiar archivos del sistema.\n"
        msg = f"Se limpiaran:\n{names}\n\nTamano estimado: {format_size(total)}\n\n{detail}\nContinuar?"
        if not messagebox.askyesno(APP_NAME, msg, icon="warning"):
            return
        self.set_busy(True, mode="determinate")
        self.pages_clean.progress.set(0)
        self.set_status("Limpiando...")
        threading.Thread(target=self._clean_worker, args=(selected,), daemon=True).start()

    def _clean_worker(self, selected):
        total_freed = 0
        target_all = sum(c.size for c in selected)
        cumulative = 0
        for cat in selected:
            if self.busy is False:
                break
            self.log(f"Limpiando: {cat.label} ...")
            if cat.recycle_bin:
                # Medir ANTES de vaciar: despues ya no queda nada que contar.
                bin_size = recycle_bin_size()
                ok, msg = empty_recycle_bin()
                if ok:
                    total_freed += bin_size
                cumulative += cat.size
                self.log(f"  Papelera: {msg}")
                continue
            removed, errors, freed = cat.clean(
                on_progress=lambda frac, cum=cumulative, t=target_all:
                self.after(0, self._clean_progress, cum, t, frac))
            cumulative += cat.size
            total_freed += freed
            self.log(f"  Eliminados {removed} elementos, {errors} errores "
                     f"({format_size(freed)} liberados).")
        self.after(0, self._clean_done, total_freed)

    def _clean_progress(self, cum_base, target_all, frac_cat):
        if target_all > 0 and self.busy:
            value = cum_base / target_all + frac_cat * (target_all - cum_base) / target_all
            self.pages_clean.progress.set(min(value, 1.0))

    def _clean_done(self, total_freed):
        self.set_busy(False)
        self.pages_clean.progress.set(1)
        self.set_status(f"Limpieza completada - {format_size(total_freed)} liberados")
        self.log(f"Total liberado: {format_size(total_freed)}")
        self.after(300, self.analyze_all)

    # ------------------------------------------------------------------ vista previa

    def preview_clean(self):
        selected = [c for c in self.categories if self.pages_clean.vars[c.key].get()]
        if not selected:
            messagebox.showinfo(APP_NAME, "No hay categorias seleccionadas.")
            return
        if sum(c.files for c in selected) == 0 and not any(c.recycle_bin for c in selected):
            messagebox.showinfo(APP_NAME, "No hay archivos que mostrar (todo parece limpio).")
            return
        win = ctk.CTkToplevel(self)
        win.title("Vista previa de limpieza")
        win.geometry("760x520")
        ctk.CTkLabel(win, text="Archivos que se eliminaran (primeras 1000 entradas)",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))
        box = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=11))
        box.pack(fill="both", expand=True, padx=16, pady=6)
        box.configure(state="normal")
        for cat in selected:
            if cat.recycle_bin:
                box.insert("end", f"== {cat.label}: se vaciara la papelera ==\n\n")
                continue
            files, scanned = cat.list_files(1000)
            box.insert("end", f"== {cat.label} ({len(files)} mostradas de {scanned:,} detectadas) ==\n")
            for f in files:
                box.insert("end", f"  {f}\n")
            box.insert("end", "\n")
        box.configure(state="disabled")


def _excepthook(exc_type, exc, tb):
    _errlog("excepcion no capturada: "
            + "".join(traceback.format_exception(exc_type, exc, tb)))


def main():
    _errlog("--- arranque ---")
    if not is_admin():
        try:
            if getattr(sys, "frozen", False):
                exe, args = sys.executable, ""
            else:
                exe, args = sys.executable, f'"{os.path.abspath(sys.argv[0])}"'
            _errlog(f"no admin; elevando: {exe} {args}")
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, args, None, 1)
            _errlog(f"runas devolvio {result}")
            if result > 32:
                return
        except Exception as e:
            _errlog(f"error al elevar: {e}")
    try:
        ctk.set_appearance_mode("dark")
        app = CleanerApp()
        _errlog("app creada")
        app.mainloop()
        _errlog("mainloop terminado")
    except Exception:
        _errlog("EXCEPTION: " + traceback.format_exc())
