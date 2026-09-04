"""Page: Startup manager (startup apps, scheduled tasks, processes)


This module implements the comprehensive startup and process management
UI for PySide6. It replicates the behavior of the legacy CustomTkinter
startup page while providing a modern, native Windows experience.

Architecture:
    Three sub-tabs in a QTabWidget, each following the same pattern:
    1. A worker gathers data off the UI thread via run_async.
    2. The done-callback fills the tree in batches.
    3. Every entry point respects the global host.busy guard.
    4. Startup app icons come from the native QFileIconProvider
       (the legacy extracted them with GDI+ on a worker).

Design Principles:
1. Safety: Protected processes cannot be killed.
2. Non-Destructive: Startup entries are moved to disabled keys, not deleted.
3. Thread Safety: All system queries happen on background threads.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QFileInfo, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME
from ...i18n import t
from ...processes import get_processes, is_protected, kill_process
from ...startup import get_disabled_startup, get_startup_apps, is_runonce_entry, set_startup
from ...tasks import get_scheduled_tasks, get_task_states, set_task_enabled
from .. import icons
from ..dialogs import app_confirm, app_info
from ..theme import GREEN_TEXT, ORANGE
from ..tree_helpers import fill_tree, make_tree, selected_many, selected_one
from ..workers import run_async

_ICON_PROVIDER = QFileIconProvider()


def _command_exe(command: str) -> str:
    """Best-effort executable path from a command line (for the icon).

    Args:
        command: The startup command string.

    Returns:
        str: The executable path, or empty string if unparseable.
    """
    cmd = (command or "").strip()
    if not cmd:
        return ""
    if cmd.startswith('"'):
        return cmd.split('"')[1]
    return cmd.split()[0]


_SOURCE_KEYS = {
    # O4 (Lote F3): the core returns stable English source tags; the UI
    # translates them. Unknown tags fall through untranslated.
    "User (HKCU Run)": "startup.src.user_run",
    "User (HKCU RunOnce)": "startup.src.user_runonce",
    "System (HKLM Run)": "startup.src.system_run",
    "System (HKLM RunOnce)": "startup.src.system_runonce",
    "User (disabled)": "startup.src.user_disabled",
}


def _source_label(source: str) -> str:
    """Translate a stable core source tag for display (O4, Lote F3)."""
    key = _SOURCE_KEYS.get(source)
    return t(key) if key else source


class StartupPage(QWidget):
    """Startup apps, scheduled tasks and running processes manager.

    Attributes:
        host: The main window host.
        tabs: The QTabWidget containing the three sub-tabs.
        startup_data: List of startup app entries.
        tasks_data: List of scheduled task entries.
        proc_data: List of running process entries.
    """

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        title = QLabel(t("startup.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("startup.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_startup_tab(), t("tab.startup_apps"))
        self.tabs.addTab(self._build_tasks_tab(), t("tab.tasks"))
        self.tabs.addTab(self._build_processes_tab(), t("tab.processes"))
        lay.addWidget(self.tabs, 1)
        self._apply_button_icons()

    # ------------------------------------------------------ startup apps

    def _apply_button_icons(self) -> None:
        """Attach themed icons to every tab's buttons."""
        icons.apply(self.startup_refresh_btn, "refresh")
        icons.apply(self.startup_disable_btn, "disable", role="warning")
        icons.apply(self.startup_reenable_btn, "enable", role="success")
        icons.apply(self.tasks_refresh_btn, "refresh")
        icons.apply(self.tasks_disable_btn, "disable", role="warning")
        icons.apply(self.tasks_enable_btn, "enable", role="success")
        icons.apply(self.proc_refresh_btn, "refresh")
        icons.apply(self.kill_btn, "cancel", role="error")

    def refresh_icons(self) -> None:
        """Re-apply every icon after a dark/light theme switch."""
        self._apply_button_icons()

    def _build_startup_tab(self) -> QWidget:
        """Build the startup apps sub-tab."""
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.startup_refresh_btn = QPushButton(t("btn.refresh"))
        self.startup_refresh_btn.clicked.connect(self.refresh_startup)
        self.startup_disable_btn = QPushButton(t("btn.disable_selected"))
        self.startup_disable_btn.setProperty("kind", "warning")
        self.startup_disable_btn.clicked.connect(self.disable_startup_selected)
        reenable_btn = QPushButton(t("btn.reenable"))
        reenable_btn.clicked.connect(self.show_disabled_startup)
        self.startup_reenable_btn = reenable_btn
        toolbar.addWidget(self.startup_refresh_btn)
        toolbar.addWidget(self.startup_disable_btn)
        toolbar.addWidget(reenable_btn)
        toolbar.addStretch(1)
        lay.addLayout(toolbar)

        self.startup_tree = make_tree(
            self,
            [
                ("#0", t("col.name"), 260),
                ("src", t("col.source"), 160),
                ("cmd", t("col.command"), 420),
            ],
        )
        lay.addWidget(self.startup_tree, 1)
        self.startup_data = []
        # P4 (Lote F2): shell-icon extraction cache, keyed by exe path.
        self._icon_cache = {}
        self._icon_queue = []
        return tab

    def refresh_startup(self) -> None:
        """Refresh the startup apps list."""
        if self.host.busy:
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._startup_worker, self._startup_done,
                  on_error=lambda exc: self._generic_error(
                      t("area.startup"), exc))

    def _startup_worker(self):
        """Gather startup entries off the UI thread."""
        return (get_startup_apps(),)

    def _startup_done(self, data) -> None:
        """Handle startup data load completion.

        Rows paint IMMEDIATELY; icons come afterwards (P4, Lote F2):
        shell-icon extraction costs ~10-50 ms per entry cold and used to
        block the UI thread before the table even appeared. Extraction
        runs one entry per event-loop tick after the render and is
        cached per exe path, so later refreshes are instant."""
        self.host.set_busy(False)
        self.startup_data = data
        specs = [
            (e["name"], (_source_label(e["source"]), e["command"]),
             {"index": i})
            for i, e in enumerate(data)
        ]
        fill_tree(self.startup_tree, specs)
        self.host.log(t("log.startup_loaded", n=len(self.startup_data)))
        self._icon_queue = list(data)
        QTimer.singleShot(0, self._extract_next_icon)

    def _extract_next_icon(self) -> None:
        """Attach icons one entry per event-loop tick (P4, Lote F2)."""
        if not self._icon_queue:
            return
        entry = self._icon_queue.pop(0)
        exe = _command_exe(entry["command"])
        if exe:
            icon = self._icon_cache.get(exe)
            if icon is None and exe not in self._icon_cache:
                if os.path.exists(exe):
                    icon = _ICON_PROVIDER.icon(QFileInfo(exe))
                self._icon_cache[exe] = icon
            if icon is not None:
                index = next((i for i, d in enumerate(self.startup_data)
                              if d is entry), None)
                if index is not None:
                    item = self.startup_tree.topLevelItem(index)
                    if item is not None:
                        item.setIcon(0, icon)
        QTimer.singleShot(0, self._extract_next_icon)

    def disable_startup_selected(self) -> None:
        """Disable the selected startup entry."""
        entry = selected_one(self.startup_tree, self.startup_data)
        if entry is None:
            return
        if is_runonce_entry(entry):
            msg = (f"{t('startup.runonce_warning')}\n\n"
                   f"{t('startup.runonce_confirm', name=entry['name'])}")
            if not app_confirm(self, "warning", APP_NAME, msg):
                return
        else:
            if not app_confirm(self, "warning", APP_NAME,
                               t("msg.disable_startup", name=entry["name"])):
                return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._disable_startup_worker, self._disable_startup_done,
                  (entry,))

    def _disable_startup_worker(self, entry):
        ok, msg = set_startup(entry, False)
        return ok, msg, entry

    def _disable_startup_done(self, ok, msg, entry) -> None:
        self.host.set_busy(False)
        if ok:
            self.host.log(t("log.startup_disabled", name=entry["name"]))
            self.host.set_status(t("status.startup_disabled", name=entry["name"]))
        else:
            self.host.set_status(t("status.startup_disable_error"))
            self.host.log(t("log.startup_disable_error",
                            name=entry["name"], msg=msg))
            app_info(self, "critical", APP_NAME,
                     t("msg.startup_disable_error", msg=msg))
        self.refresh_startup()

    def show_disabled_startup(self) -> None:
        """Show the dialog to re-enable disabled startup entries."""
        if self.host.busy:
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._disabled_worker, self._disabled_done,
                  on_error=lambda exc: self._generic_error(
                      t("area.disabled"), exc))

    def _disabled_worker(self):
        return (get_disabled_startup(),)

    def _disabled_done(self, disabled) -> None:
        self.host.set_busy(False)
        if not disabled:
            app_info(self, "info", APP_NAME, t("msg.no_disabled"))
            return
        win = QDialog(self)
        win.setWindowTitle(t("title.reattach"))
        win.resize(640, 420)
        lay = QVBoxLayout(win)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        lbl = QLabel(t("startup.reattach_label"))
        lbl.setObjectName("pageTitle")
        lay.addWidget(lbl)
        tree = make_tree(win, [("#0", t("col.name"), 240),
                               ("cmd", t("col.cmd_file"), 360)])
        specs = [
            (e["name"], (e["command"] or e.get("filename", "")), {"index": i})
            for i, e in enumerate(disabled)
        ]
        fill_tree(tree, specs)
        lay.addWidget(tree, 1)

        def _re() -> None:
            sel = selected_many(tree, disabled)
            if not sel:
                return
            self.host.set_busy(True, mode="indeterminate")
            run_async(self, self._reenable_worker, self._reenable_done,
                      (sel, win))

        btn = QPushButton(t("btn.reenable_selected"))
        btn.setProperty("kind", "success")
        btn.clicked.connect(_re)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(btn)
        lay.addLayout(h)
        win.exec()

    def _reenable_worker(self, entries, win):
        results = []
        for entry in entries:
            ok, msg = set_startup(entry, True)
            results.append((entry["name"], ok, msg))
        return results, win

    def _reenable_done(self, results, win) -> None:
        self.host.set_busy(False)
        for name, ok, msg in results:
            if ok:
                self.host.log(t("log.startup_enabled", name=name))
            else:
                self.host.log(t("log.startup_enable_error", name=name, msg=msg))
        win.accept()
        self.refresh_startup()

    def on_busy(self, busy: bool) -> None:
        """Disable action buttons while an operation is running."""
        for b in (self.startup_refresh_btn, self.startup_disable_btn,
                  self.tasks_refresh_btn, self.tasks_disable_btn,
                  self.tasks_enable_btn, self.proc_refresh_btn, self.kill_btn):
            b.setEnabled(not busy)

    # -------------------------------------------------- scheduled tasks

    def _build_tasks_tab(self) -> QWidget:
        """Build the scheduled tasks sub-tab."""
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.tasks_refresh_btn = QPushButton(t("btn.refresh"))
        self.tasks_refresh_btn.clicked.connect(self.refresh_tasks)
        self.tasks_disable_btn = QPushButton(t("btn.disable"))
        self.tasks_disable_btn.setProperty("kind", "warning")
        self.tasks_disable_btn.clicked.connect(lambda: self._toggle_task(False))
        self.tasks_enable_btn = QPushButton(t("btn.enable"))
        self.tasks_enable_btn.setProperty("kind", "success")
        self.tasks_enable_btn.clicked.connect(lambda: self._toggle_task(True))
        self.tasks_info = QLabel("")
        self.tasks_info.setObjectName("mutedText")
        toolbar.addWidget(self.tasks_refresh_btn)
        toolbar.addWidget(self.tasks_disable_btn)
        toolbar.addWidget(self.tasks_enable_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.tasks_info)
        lay.addLayout(toolbar)

        self.tasks_tree = make_tree(
            self,
            [
                ("#0", t("col.task"), 300),
                ("status", t("col.status"), 90, "center"),
                ("sched", t("col.schedule"), 130, "center"),
                ("next", t("col.next_run"), 180),
            ],
        )
        lay.addWidget(self.tasks_tree, 1)
        self.tasks_data = []
        # E2.3: sequence token for the async disabled-state merge (a stale
        # verbose result from an older refresh must not touch newer data).
        self._tasks_seq = 0
        return tab

    def refresh_tasks(self) -> None:
        """Refresh the scheduled tasks list."""
        if self.host.busy:
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._refresh_tasks_worker, self._refresh_tasks_done,
                  on_error=lambda exc: self._generic_error(
                      t("area.tasks"), exc))

    def _refresh_tasks_worker(self):
        return (get_scheduled_tasks(),)

    def _refresh_tasks_done(self, tasks) -> None:
        self.host.set_busy(False)
        self.tasks_data = tasks
        self._tasks_seq += 1
        self._render_tasks()
        self.host.log(t("log.tasks_loaded", n=len(tasks)))
        # E2.3: the exact disabled state only exists in the verbose query
        # (3-15 s); the table is already rendered, so refine it in the
        # background instead of making the user wait for it.
        run_async(self, self._states_worker, self._states_done,
                  (self._tasks_seq,),
                  on_error=lambda exc: self._generic_error(
                      t("area.tasks"), exc))

    def _states_worker(self, seq):
        return seq, get_task_states()

    def _states_done(self, result) -> None:
        seq, states = result
        if seq != self._tasks_seq or not states:
            return
        for task in self.tasks_data:
            state = states.get(task.get("name", ""))
            if state:
                task["scheduled"] = state
        self._render_tasks()

    def _render_tasks(self) -> None:
        enabled = 0
        disabled = 0
        specs = []
        for i, task in enumerate(self.tasks_data):
            state = task.get("scheduled") or task.get("status", "")
            is_disabled = "disabled" in state.lower()
            if is_disabled:
                disabled += 1
            else:
                enabled += 1
            specs.append(
                (task["name"],
                 (state, task.get("status", ""), task.get("next", "")),
                 {"index": i,
                  "fg": ORANGE if is_disabled else GREEN_TEXT}))
        # Preserve the user's selection across re-renders (row order is
        # stable: only the scheduled field changes between passes).
        current = self.tasks_tree.currentItem()
        current_index = current.data(0, Qt.UserRole) if current else None
        fill_tree(self.tasks_tree, specs)
        if isinstance(current_index, int) and 0 <= current_index < len(specs):
            it = self.tasks_tree.topLevelItem(current_index)
            if it is not None:
                self.tasks_tree.setCurrentItem(it)
        self.tasks_info.setText(
            t("startup.tasks_count", n=enabled, m=disabled))

    def _toggle_task(self, enable: bool) -> None:
        """Enable or disable the selected scheduled task."""
        task = selected_one(self.tasks_tree, self.tasks_data)
        if task is None:
            return
        key = "msg.task_enable_q" if enable else "msg.task_disable_q"
        if not app_confirm(self, "warning", APP_NAME,
                           t(key, name=task["name"])):
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._toggle_task_worker, self._toggle_task_done,
                  (task["name"], enable))

    def _toggle_task_worker(self, name, enable):
        ok, msg = set_task_enabled(name, enable)
        return ok, msg, name, enable

    def _toggle_task_done(self, ok, msg, name, enable) -> None:
        self.host.set_busy(False)
        key = "status.task_enabled" if enable else "status.task_disabled"
        logkey = "log.task_enabled" if enable else "log.task_disabled"
        if ok:
            self.host.log(t(logkey, name=name))
            self.host.set_status(t(key, name=name))
        else:
            self.host.set_status(t("status.task_error"))
            self.host.log(t("log.task_error", name=name, msg=msg))
            app_info(self, "critical", APP_NAME,
                     t("msg.task_error", msg=msg))
        self.refresh_tasks()

    # --------------------------------------------------------- processes

    def _build_processes_tab(self) -> QWidget:
        """Build the running processes sub-tab."""
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.proc_refresh_btn = QPushButton(t("btn.refresh"))
        self.proc_refresh_btn.clicked.connect(self.refresh_processes)
        self.kill_btn = QPushButton(t("btn.end_process"))
        self.kill_btn.setProperty("kind", "danger")
        self.kill_btn.clicked.connect(self.kill_selected)
        self.proc_search = QLineEdit()
        self.proc_search.setPlaceholderText(t("startup.search_placeholder"))
        self.proc_search.setMaximumWidth(220)
        filter_btn = QPushButton(t("btn.filter"))
        filter_btn.clicked.connect(self.refresh_processes)
        toolbar.addWidget(self.proc_refresh_btn)
        toolbar.addWidget(self.kill_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(filter_btn)
        toolbar.addWidget(self.proc_search)
        lay.addLayout(toolbar)

        self.proc_tree = make_tree(
            self,
            [
                ("#0", t("col.process"), 260),
                ("pid", "PID", 90, "center"),
                ("session", t("col.session"), 100, "center"),
                ("mem", t("col.memory"), 110, "e"),
            ],
        )
        lay.addWidget(self.proc_tree, 1)
        self.proc_data = []
        return tab

    def refresh_processes(self) -> None:
        """Refresh the running processes list."""
        if self.host.busy:
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._refresh_processes_worker,
                  self._refresh_processes_done,
                  on_error=lambda exc: self._generic_error(
                      t("area.processes"), exc))

    def _refresh_processes_worker(self):
        return (get_processes(),)

    def _refresh_processes_done(self, procs) -> None:
        self.host.set_busy(False)
        self.proc_data = procs
        search = self.proc_search.text().strip().lower()
        specs = []
        count = 0
        for i, p in enumerate(procs):
            if search and search not in p["name"].lower():
                continue
            count += 1
            # NOTE: no "user" column anymore - tasklist runs without /v
            # (several seconds faster, cannot hang on a hung process).
            specs.append((p["name"],
                          (p["pid"], p["session"], p["mem"]),
                          {"index": i}))
        fill_tree(self.proc_tree, specs)
        self.host.log(t("log.processes_shown", n=count))

    def _generic_error(self, area, exc) -> None:
        """Handle generic load errors."""
        self.host.set_busy(False)
        self.host.set_status(t("status.load_error", area=area))
        self.host.log(t("log.load_error", area=area, exc=exc))
        app_info(self, "critical", APP_NAME,
                 t("msg.load_error", area=area, exc=exc))

    def kill_selected(self) -> None:
        """Kill the selected process after confirmation."""
        items = self.proc_tree.selectedItems()
        if not items:
            app_info(self, "info", APP_NAME, t("msg.select_process"))
            return
        item = items[0]
        pid = item.text(1)
        name = item.text(0)
        if is_protected(name):
            app_info(self, "warning", APP_NAME,
                     t("msg.process_protected", name=name))
            return
        if not app_confirm(self, "danger", APP_NAME,
                           t("msg.kill_process", name=name, pid=pid)):
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._kill_worker, self._kill_done, (pid, name))

    def _kill_worker(self, pid, name):
        ok, msg = kill_process(pid, name=name)
        return ok, msg, name

    def _kill_done(self, ok, msg, name) -> None:
        self.host.set_busy(False)
        if ok:
            self.host.log(t("log.process_killed", name=name))
            self.host.set_status(t("status.process_killed", name=name))
        else:
            self.host.set_status(t("status.process_error"))
            self.host.log(t("log.process_error", name=name, msg=msg))
            app_info(self, "critical", APP_NAME,
                     t("msg.process_error", msg=msg))
        self.refresh_processes()

    def on_show(self) -> None:
        """Called when the page becomes visible."""
        pass
