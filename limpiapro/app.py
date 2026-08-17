"""LimpiaPro main application.

CleanerApp builds the sidebar + lazily constructed pages, owns the global
busy state and drives the two big workflows:

  - analyze_all(): one scan pass, one thread per category, progress
    marshalled to the UI through post_ui; results cached to
    limpiador_cache.json for an instant next start.
  - confirm_clean()/_clean_worker(): parallel deletion per category with a
    cumulative progress bar, followed by a full re-analysis.

Entry point: main() re-elevates through ShellExecuteW when not admin
(the app keeps running without admin if the UAC prompt is declined)."""

import ctypes
import json
import os
import platform
import sys
import threading
import time
import tkinter.ttk as ttk
import traceback
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import APP_NAME, APP_VERSION
from .categories import build_categories
from .i18n import t
from .paths import get_cache_file
from .recycle import empty_recycle_bin, recycle_bin_size
from .ui.clean_page import CleanPage
from .ui.duplicates_page import DuplicatePage
from .ui.log_page import LogPage
from .ui.startup_page import StartupPage
from .ui.theme import ACCENT_FALLBACK
from .ui.uninstall_page import UninstallPage
from .ui.update_page import UpdatePage
from .ui.widgets import post_ui, readonly_toplevel, run_async, start_ui_poller
from .utils import _errlog, format_size, is_admin
from .winapp2 import invalidate_detect_cache, parse_winapp_rules
from .winstyle import apply_mica_backdrop, fluent_font, get_system_accent


class CleanerApp(ctk.CTk):
    """Application window: sidebar navigation, pages and global state."""

    CACHE_FILE = get_cache_file()
    # Cache format version: bump when the schema changes so stale cached
    # results from an older build are ignored instead of misapplied.
    CACHE_SCHEMA = 1

    # Widgets and state created lazily in _build_sidebar: declared here so
    # the type checker (and IDE) know the attributes exist before use.
    theme_mode: ctk.StringVar
    theme_switch: ctk.CTkSwitch | None = None
    _theme_animating: bool
    _theme_target: str | None
    sidebar: ctk.CTkFrame
    content: ctk.CTkFrame
    nav_buttons: dict

    def __init__(self):
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.title(f"{APP_NAME} {APP_VERSION} - {t('app.window_subtitle')}")
        _errlog("init: window created")
        self.geometry("1000x680")
        self.minsize(860, 560)
        self.configure(fg_color=("#e8e8e8", "#17181c"))

        ctk.set_appearance_mode("dark")
        self.accent = get_system_accent()
        # Mica backdrop (Windows 11 22H2+). The window only becomes
        # translucent when the system supports the material.
        self.mica = apply_mica_backdrop(self)
        if not self.mica:
            self.configure(fg_color=("#e8e8e8", "#17181c"))

        self.categories = build_categories()
        self.scanner = None
        self.busy = False
        # Cooperative cancellation for long scans/cleans (P1-13).
        self.cancel_requested = False

        # Resize debounce: avoid one repaint per <Configure> event.
        self._resize_job = None
        self.bind("<Configure>", self._on_configure)

        self._build_sidebar()
        self._pages = {}
        self._restyle_tree()
        self.show_page("clean")

        self.log(t("log.started_admin" if is_admin() else "log.started_no_admin",
                   app=APP_NAME, ver=APP_VERSION))
        start_ui_poller(self)
        self.after(300, self.analyze_all)

    def report_callback_exception(self, exc, val, tb):  # type: ignore[reportIncompatibleMethodOverride]
        """Route Tk callback exceptions to the error log."""
        _errlog("CALLBACK EXCEPTION: " + "".join(traceback.format_exception(exc, val, tb)))
        try:
            super().report_callback_exception(exc, val, tb)
        except Exception:
            pass  # nosec B110 - fallback must never crash the UI thread

    def _on_close(self):
        """WM_DELETE_WINDOW handler: destroy the window."""
        _errlog("closing by user or WM_CLOSE")
        self.destroy()

    def _on_configure(self, event):
        """Debounce window resize events (only the root's own events)."""
        if event.widget is not self:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(200, self._resize_debounced)

    def _resize_debounced(self):
        """Process pending layout once, 200 ms after the last resize."""
        self._resize_job = None
        self.update_idletasks()

    # ------------------------------------------------------------------ layout

    def _build_sidebar(self):
        """Build the navigation sidebar: logo, nav buttons, theme switch."""
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=("#d9d9d9", "#222327"))
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)
        self.sidebar.pack_propagate(False)

        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=16, pady=(18, 10))
        ctk.CTkLabel(logo, text="\U0001F9F9", font=ctk.CTkFont(size=30)).pack(side="left")
        ctk.CTkLabel(logo, text=APP_NAME, font=fluent_font(18, "bold")).pack(side="left", padx=8)

        self.nav_buttons = {}
        nav_items = [
            ("clean", t("nav.clean")),
            ("startup", t("nav.startup")),
            ("dupes", t("nav.dupes")),
            ("update", t("nav.update")),
            ("uninstall", t("nav.uninstall")),
            ("log", t("nav.log")),
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

        # Sidebar footer: light/dark toggle.
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

        sw = ctk.CTkSwitch(footer, text=t("theme.dark"), variable=self.theme_mode,
                           onvalue="dark", offvalue="light", command=_toggle)
        sw.pack(anchor="w")
        self.theme_switch = sw

    def _fade_to(self, target_alpha, ready=None):
        """Animate the window opacity; call ready() when finished."""
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
        """Switch the appearance mode and restyle the ttk trees."""
        m = self.theme_mode.get()
        ctk.set_appearance_mode(m)
        self._restyle_tree()
        self.after(60, self._finish_theme)

    def _finish_theme(self):
        """Restore the switch label and fade back in."""
        m = self.theme_mode.get()
        switch = self.theme_switch
        if switch is None:
            return
        switch.configure(
            text=t("theme.dark") if m == "dark" else t("theme.light"),
            state="normal")
        self._fade_to(1.0)
        self._theme_animating = False

    def _highlight_nav(self, active_key):
        """Accentuate the active nav button and reset the others."""
        accent = getattr(self, "accent", ACCENT_FALLBACK)
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
        """Apply theme colors to the trees (ttk does not follow the
        customtkinter light/dark mode by itself)."""
        style = ttk.Style()
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
            pass  # nosec B110 - theme styling is best-effort

    def _get_page(self, key):
        """Return the page for `key`, constructing it lazily on first use
        and caching it (page state survives navigation)."""
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
        """Swap the visible page and highlight its nav button."""
        page = self._get_page(key)
        if getattr(self, "_current_page", None) is not None and self._current_page is not page:
            self._current_page.pack_forget()
        page.pack(fill="both", expand=True)
        self._current_page = page
        self._highlight_nav(key)

    @property
    def pages_clean(self):
        """The cleanup page (constructing it if needed)."""
        return self._get_page("clean")

    @property
    def pages_dupes(self):
        """The duplicates page (constructing it if needed)."""
        return self._get_page("dupes")

    @property
    def log_page(self):
        """The log page (constructing it if needed)."""
        return self._get_page("log")

    # ------------------------------------------------------------------ log / state

    def log(self, msg):
        """Append a message to the activity log page."""
        self.log_page.log(msg)

    def set_status(self, text):
        """Update the global status label (lives on the cleanup page)."""
        self.pages_clean.status_lbl.configure(text=text)

    def set_busy(self, value, mode="determinate"):
        """Set the global busy flag, drive the progress bar and notify
        every built page (on_busy) so they disable their action buttons."""
        self.busy = value
        self._notify_busy(value)
        self.pages_clean.progress.stop()
        if value:
            self.pages_clean.progress.configure(mode=mode)
            if mode == "indeterminate":
                self.pages_clean.progress.start()
        else:
            self.pages_clean.progress.configure(mode="determinate")
            self.pages_clean.progress.set(1)

    def _notify_busy(self, value):
        """Forward busy state changes to each page's on_busy hook."""
        for page in self._pages.values():
            handler = getattr(page, "on_busy", None)
            if handler:
                try:
                    handler(value)
                except Exception as e:
                    _errlog(f"on_busy failed ({type(page).__name__}): {e!r}")

    # ------------------------------------------------------------------ analyze

    def _load_cache(self):
        """Load the last scan results cache ({} when missing, corrupt or
        written by a different schema/app version)."""
        try:
            with open(self.CACHE_FILE, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        if raw.get("schema") != self.CACHE_SCHEMA:
            return {}
        if raw.get("app_version") != APP_VERSION:
            return {}
        data = raw.get("data")
        return data if isinstance(data, dict) else {}

    def _save_cache(self):
        """Persist per-category size/files to disk (atomic tmp+replace)
        with schema/app provenance metadata so stale caches are never
        mistaken for fresh ones."""
        data = {c.key: {"size": c.size, "files": c.files} for c in self.categories}
        payload = {
            "schema": self.CACHE_SCHEMA,
            "app_version": APP_VERSION,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": platform.platform(),
            "data": data,
        }
        try:
            tmp = self.CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, self.CACHE_FILE)
        except Exception:
            pass  # nosec B110 - cache write is best-effort

    def analyze_all(self):
        """Kick off a full system analysis on a background coordinator
        thread (cached results are shown immediately first)."""
        if self.busy:
            return
        self.cancel_requested = False
        # Show cached results immediately (instant startup).
        self._apply_cache()
        self.set_busy(True)
        self.set_status(t("status.analyzing"))
        threading.Thread(target=self._analyze_worker, daemon=True).start()

    def request_cancel(self):
        """Ask the running analyzer/cleaner to stop as soon as possible."""
        self.cancel_requested = True

    def load_winapp_rules(self):
        """Ask for a winapp2.ini file and load it on a worker thread."""
        path = filedialog.askopenfilename(
            title=t("dialog.winapp_title"),
            filetypes=[("winapp2.ini", "*.ini"),
                       (t("dialog.all_files"), "*.*")])
        if not path:
            return
        self.set_busy(True, mode="indeterminate")
        self.set_status(t("status.parsing_winapp"))
        # A different ini may carry different Detect= conditions: the
        # memoized results from the previous file must not leak in.
        invalidate_detect_cache()
        run_async(self, self._load_winapp_worker, self._load_winapp_done,
                  (path,), on_error=self._load_winapp_error)

    def _load_winapp_worker(self, path):
        """Parse + detect the winapp2.ini off the UI thread.
        Returns (path, rules)."""
        rules = parse_winapp_rules(path)
        return path, rules

    def _load_winapp_apply(self, path, rules):
        """Replace the winapp category rules and refresh the UI."""
        found = False
        for c in self.categories:
            if c.key == "winapp":
                c.rules = [r2 for s in rules for r2 in s.rules]
                c.description = (t("cat.winapp.desc_detected", n=len(rules))
                                 if rules else t("cat.winapp.desc_none"))
                found = True
                break
        if found:
            self.pages_clean._build_rows()
        if rules:
            self.log(t("log.winapp_loaded", n=len(rules), path=path))
            self.set_status(t("status.winapp_loaded", n=len(rules)))
        else:
            self.log(t("log.winapp_none"))
            messagebox.showinfo(APP_NAME, t("msg.winapp_none"))
        self.set_busy(False)
        self.after(100, self.analyze_all)

    def _load_winapp_done(self, path, rules):
        """UI callback for a successful winapp2 load."""
        self._load_winapp_apply(path, rules)

    def _load_winapp_error(self, exc):
        """UI callback for a failed winapp2 load."""
        self.set_busy(False)
        self.set_status(t("status.winapp_error"))
        messagebox.showerror(APP_NAME, t("msg.winapp_error", exc=exc))

    def _apply_cache(self):
        """Copy the cached size/files into the category objects (displayed
        until the fresh scan overwrites them). Entries whose values are not
        numbers are skipped defensively."""
        cached = self._load_cache()
        for cat in self.categories:
            entry = cached.get(cat.key)
            if isinstance(entry, dict) and isinstance(entry.get("size"), (int, float)):
                cat.size = int(entry.get("size", 0))
                cat.files = int(entry.get("files", 0))

    def _analyze_worker(self):
        """Scan coordinator: one thread per category, then save the cache.

        Progress is estimated as scanned files / target total (the previous
        run's counts, or 1 per category when no cache exists). Each
        per-category callback and completion is marshalled to the UI
        through post_ui; the coordinator joins all threads before
        finishing."""
        targets = {c.key: max(c.files, 1) for c in self.categories}
        total_target = sum(targets.values())
        progress = {"done": 0}
        lock = threading.Lock()

        def cb(cat, n):
            with lock:
                # Replace this category's contribution to the running total.
                progress["done"] = (progress["done"] - progress.get(cat.key, 0)
                                    + n)
                progress[cat.key] = n
                frac = progress["done"] / total_target
            post_ui(lambda: self._analyze_progress(cat, frac))

        threads = []

        def should_cancel():
            return self.cancel_requested

        for cat in self.categories:
            def work(c=cat):
                if self.cancel_requested:
                    post_ui(lambda cc=c: self._analyze_one_done(cc))
                    return
                if c.recycle_bin:
                    c.size = recycle_bin_size()
                    c.files = 0
                else:
                    c.scan(on_progress=lambda n, cc=c: cb(cc, n),
                           should_cancel=should_cancel)
                post_ui(lambda cc=c: self._analyze_one_done(cc))
            thread = threading.Thread(target=work, daemon=True)
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()

        if not self.cancel_requested:
            self._save_cache()
        post_ui(self._analyze_all_done)

    def _analyze_progress(self, cat, frac):
        """Update the determinate progress bar during the scan."""
        if self.busy:
            self.pages_clean.progress.configure(mode="determinate")
            self.pages_clean.progress.set(min(frac, 1.0))
            self.set_status(f"{t('status.analyzing')} {cat.label} ...")

    def _analyze_one_done(self, cat):
        """Refresh one category's row as soon as its scan finishes."""
        self.pages_clean.update_after_scan(cat)

    def _analyze_all_done(self):
        """Finish the analysis: clear busy and update the selected total."""
        self.set_busy(False)
        if self.cancel_requested:
            self.set_status(t("status.analyze_cancelled"))
            self.log(t("log.analyze_cancelled"))
            self.cancel_requested = False
            return
        self.set_status(t("status.analysis_done"))
        self.update_total()
        _errlog("analysis complete")

    # ------------------------------------------------------------------ total

    def update_total(self):
        """Sum the sizes of the checked categories onto the total label."""
        total = sum(c.size for c in self.categories if self.pages_clean.vars[c.key].get())
        self.pages_clean.total_lbl.configure(text=t("clean.total",
                                                    size=format_size(total)))

    # ------------------------------------------------------------------ clean

    def confirm_clean(self):
        """Build the confirmation dialog and launch _clean_worker."""
        selected = [c for c in self.categories if self.pages_clean.vars[c.key].get()]
        if not selected:
            messagebox.showinfo(APP_NAME, t("msg.no_categories"))
            return
        total = sum(c.size for c in selected)
        names = "\n".join(f"  \u2022 {c.label}" for c in selected)
        detail = t("msg.clean_detail_base")
        if any(c.recycle_bin for c in selected):
            detail += t("msg.clean_detail_recycle")
        if any(c.needs_admin for c in selected) and not is_admin():
            detail += t("msg.clean_detail_admin")
        msg = t("msg.clean_confirm", names=names, size=format_size(total),
                detail=detail)
        if not messagebox.askyesno(APP_NAME, msg, icon="warning"):
            return
        self.cancel_requested = False
        self.set_busy(True, mode="determinate")
        self.pages_clean.progress.set(0)
        self.set_status(t("status.cleaning"))
        threading.Thread(target=self._clean_worker, args=(selected,),
                         daemon=True).start()

    def _clean_worker(self, selected):
        """Delete the selected categories sequentially; each category
        deletes its targets in parallel internally. The progress bar is
        cumulative across categories (each one's fraction is scaled by its
        share of the pre-clean total)."""
        total_freed = 0
        target_all = sum(c.size for c in selected)
        cumulative = 0

        def should_cancel():
            return self.cancel_requested

        for cat in selected:
            if self.cancel_requested:
                break
            label = cat.label
            post_ui(lambda lab=label: self.log(t("log.cleaning_cat", label=lab)))
            if cat.recycle_bin:
                # Measure BEFORE emptying: afterwards there is nothing left
                # to count. The ok-message comes back in English; the UI
                # translates the success line for display.
                bin_size = recycle_bin_size()
                ok, msg = empty_recycle_bin()
                if ok:
                    total_freed += bin_size
                cumulative += cat.size
                post_ui(lambda ok=ok, m=msg: self.log(t(
                    "log.recycle_line",
                    msg=t("msg.recycle_emptied") if ok else m)))
                continue
            removed, errors, freed = cat.clean(
                target_bytes=cat.size,
                on_progress=lambda frac, cum=cumulative, tot=target_all:
                post_ui(lambda: self._clean_progress(cum, tot, frac)),
                should_cancel=should_cancel)
            cumulative += cat.size
            total_freed += freed
            post_ui(lambda r=removed, e=errors, f=freed:
                    self.log(t("log.cat_cleaned", n=r, e=e,
                               size=format_size(f))))
            if errors:
                summary = cat.error_summary()
                detail = "".join(
                    t("log.error_kind", n=n, kind=t("errk." + k))
                    for k, n in sorted(summary.items()))
                post_ui(lambda d=detail: self.log(d))
        post_ui(lambda: self._clean_done(total_freed, self.cancel_requested))

    def _clean_progress(self, cum_base, target_all, frac_cat):
        """Map one category's 0..1 progress onto the global bar."""
        if target_all > 0 and self.busy:
            value = cum_base / target_all + frac_cat * (target_all - cum_base) / target_all
            self.pages_clean.progress.set(min(value, 1.0))

    def _clean_done(self, total_freed, cancelled=False):
        """Finish the cleanup and trigger a fresh full analysis (or, when
        cancelled, just release busy and report)."""
        self.set_busy(False)
        self.pages_clean.progress.set(1)
        if cancelled:
            self.set_status(t("status.clean_cancelled"))
            self.log(t("log.clean_cancelled"))
            self.cancel_requested = False
            return
        self.set_status(t("status.clean_done", size=format_size(total_freed)))
        self.log(t("log.total_freed", size=format_size(total_freed)))
        self.after(300, self.analyze_all)

    # ------------------------------------------------------------------ preview

    def preview_clean(self):
        """Open the preview window; content is collected on a worker."""
        selected = [c for c in self.categories if self.pages_clean.vars[c.key].get()]
        if not selected:
            messagebox.showinfo(APP_NAME, t("msg.no_categories"))
            return
        if sum(c.files for c in selected) == 0 and not any(c.recycle_bin for c in selected):
            messagebox.showinfo(APP_NAME, t("msg.preview_empty"))
            return
        win, box = readonly_toplevel(
            self, t("title.preview"), "760x520", t("preview.header"))
        self._preview_box = box
        self.set_busy(True, mode="indeterminate")
        run_async(self, self._preview_worker, self._preview_done,
                  (selected,),
                  on_error=lambda e: self._preview_error(box, e))

    def _preview_worker(self, selected):
        """Collect up to 1000 target paths per selected category.
        Returns a list of text chunks for the preview box."""
        out = []
        for cat in selected:
            if cat.recycle_bin:
                out.append(t("preview.recycle_section", label=cat.label) + "\n\n")
                continue
            files, scanned = cat.list_files(1000)
            out.append(t("preview.section", label=cat.label,
                         shown=len(files), total=scanned) + "\n")
            for f in files:
                out.append(f"  {f}\n")
            out.append("\n")
        return out,

    def _preview_done(self, out):
        """Fill the preview box with the collected chunks."""
        self.set_busy(False)
        box = self._preview_box
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", "".join(out))
        box.configure(state="disabled")

    def _preview_error(self, box, exc):
        """Show the collection error inside the preview box."""
        self.set_busy(False)
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", t("msg.preview_error", exc=exc) + "\n")
        box.configure(state="disabled")


def _excepthook(exc_type, exc, tb):
    """sys.excepthook installed by limpiador.py: log uncaught exceptions
    (the packaged app has no console)."""
    _errlog("uncaught exception: "
            + "".join(traceback.format_exception(exc_type, exc, tb)))


def main():
    """Entry point: re-elevate to administrator when possible, then run
    the application (continuing without admin if UAC is declined)."""
    _errlog("--- startup ---")
    if not is_admin():
        try:
            if getattr(sys, "frozen", False):
                exe, args = sys.executable, ""
            else:
                exe, args = sys.executable, f'"{os.path.abspath(sys.argv[0])}"'
            _errlog(f"no admin; elevating: {exe} {args}")
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, args, None, 1)
            _errlog(f"runas returned {result}")
            if result > 32:
                return
        except Exception as e:
            _errlog(f"elevation error: {e}")
    try:
        ctk.set_appearance_mode("dark")
        app = CleanerApp()
        _errlog("app created")
        app.mainloop()
        _errlog("mainloop finished")
    except Exception:
        _errlog("EXCEPTION: " + traceback.format_exc())
