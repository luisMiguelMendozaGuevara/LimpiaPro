"""Page: uninstaller (replica of the legacy uninstall page).

Lists installed programs from the registry, launches their uninstallers
safely (argument lists, never shell=True) and searches for leftover files
and registry keys afterwards."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME
from ...i18n import t
from ...uninstall import (
    delete_registry_path,
    find_leftovers,
    get_installed_apps,
    launch_uninstaller,
)
from ...utils import _delete_path, format_size
from ..widgets import fill_tree, make_tree, readonly_toplevel, run_async, selected_one


class UninstallPage(QWidget):
    """Installed programs list with uninstall and leftover cleanup."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self.apps = []
        self.leftovers = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        title = QLabel(t("uninstall.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("uninstall.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.refresh_btn = QPushButton(t("btn.refresh"))
        self.refresh_btn.clicked.connect(self.refresh)
        self.uninstall_btn = QPushButton(t("btn.uninstall"))
        self.uninstall_btn.setProperty("kind", "warning")
        self.uninstall_btn.clicked.connect(self.uninstall_selected)
        self.search_btn = QPushButton(t("btn.find_leftovers"))
        self.search_btn.clicked.connect(self.search_leftovers)
        self.del_btn = QPushButton(t("btn.delete_leftovers"))
        self.del_btn.setProperty("kind", "danger")
        self.del_btn.clicked.connect(self.delete_leftovers)
        self.info = QLabel("")
        self.info.setObjectName("mutedText")
        bar.addWidget(self.refresh_btn)
        bar.addWidget(self.uninstall_btn)
        bar.addWidget(self.search_btn)
        bar.addWidget(self.del_btn)
        bar.addStretch(1)
        bar.addWidget(self.info)
        lay.addLayout(bar)

        self.tree = make_tree(
            self,
            [
                ("#0", t("col.application"), 360),
                ("publisher", t("col.publisher"), 240),
                ("size", t("col.size"), 100, "e"),
            ],
        )
        lay.addWidget(self.tree, 1)

        self.refresh()

    # ------------------------------------------------------------- state

    def on_busy(self, busy: bool) -> None:
        for b in (self.refresh_btn, self.uninstall_btn,
                  self.search_btn, self.del_btn):
            b.setEnabled(not busy)

    def on_show(self) -> None:
        pass

    # ---------------------------------------------------------- actions

    def refresh(self) -> None:
        if self.host.busy:
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._load_worker, self._load_done,
                  on_error=self._load_error)

    def _load_worker(self):
        return (get_installed_apps(),)

    def _load_error(self, exc) -> None:
        self.host.set_busy(False)
        self.info.setText(t("status.apps_load_error"))
        self.host.log(t("log.apps_load_error", exc=exc))

    def _load_done(self, apps) -> None:
        self.host.set_busy(False)
        self.apps = apps
        specs = [
            (a["name"],
             (a["publisher"],
              format_size(a["size_kb"] * 1024) if a["size_kb"] else ""),
             {"index": i})
            for i, a in enumerate(apps)
        ]
        fill_tree(self.tree, specs)
        self.info.setText(t("uninstall.n_apps", n=len(apps)))
        self.host.log(t("log.apps_loaded", n=len(apps)))

    def uninstall_selected(self) -> None:
        app = selected_one(self.tree, self.apps)
        if not app:
            return
        if not app["uninstall"]:
            QMessageBox.warning(self, APP_NAME, t("msg.no_uninstall_cmd"))
            return
        if QMessageBox.question(
                self, APP_NAME,
                t("msg.run_uninstaller", name=app["name"],
                  cmd=app["uninstall"]),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        # No shell=True: the command is split, the executable is verified
        # and launched with an argument list, off the UI thread.
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._launch_worker, self._launch_done, (app,),
                  on_error=lambda exc: self._launch_error(app, exc))

    def _launch_worker(self, app):
        return app["name"], *launch_uninstaller(app["uninstall"])

    def _launch_done(self, name, ok, msg) -> None:
        self.host.set_busy(False)
        if ok:
            self.host.log(t("log.uninstaller_launched", name=name))
            self.host.set_status(t("status.uninstaller_launched", name=name))
        else:
            self.host.log(t("log.uninstaller_error", name=name, msg=msg))
            QMessageBox.critical(self, APP_NAME,
                                 t("msg.uninstaller_error", msg=msg))

    def _launch_error(self, app, exc) -> None:
        self.host.set_busy(False)
        QMessageBox.critical(self, APP_NAME,
                             t("msg.uninstaller_error", exc=exc))

    def search_leftovers(self) -> None:
        app = selected_one(self.tree, self.apps)
        if not app:
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._leftover_worker, self._leftover_done, (app,),
                  on_error=self._leftover_error)

    def _leftover_worker(self, app):
        results = find_leftovers(app["name"], app.get("location", ""))
        return app["name"], results

    def _leftover_error(self, exc) -> None:
        self.host.set_busy(False)
        self.info.setText("")
        QMessageBox.critical(self, APP_NAME, t("msg.leftover_error", exc=exc))

    def _leftover_done(self, name, results) -> None:
        self.host.set_busy(False)
        self.leftovers = results
        self.info.setText(
            t("uninstall.leftover_count", name=name, n=len(results))
            if results else "")
        if not results:
            QMessageBox.information(self, APP_NAME,
                                    t("msg.no_leftovers", name=name))
            return
        self.host.log(t("log.leftovers_found", name=name, n=len(results)))
        win, box = readonly_toplevel(
            self, t("title.leftovers"), "680x440",
            t("uninstall.leftovers_header", name=name, n=len(results)))
        box.setReadOnly(False)
        box.setPlainText(
            "\n".join(f"[{t('kind.' + kind)}] {p}" for kind, p in results))
        box.setReadOnly(True)
        win.exec()

    def delete_leftovers(self) -> None:
        if not self.leftovers:
            QMessageBox.information(self, APP_NAME,
                                    t("msg.search_first",
                                      btn=t("btn.find_leftovers")))
            return
        msg = (t("msg.delete_generic_header")
               + "\n".join(f"  {p}" for _, p in self.leftovers[:20]))
        if len(self.leftovers) > 20:
            msg += "\n" + t("msg.and_n_more", n=len(self.leftovers) - 20)
        msg += "\n\n" + t("ui.continue_q")
        if QMessageBox.question(self, APP_NAME, msg,
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.host.set_busy(True, mode="indeterminate")
        run_async(self, self._delete_leftovers_worker,
                  self._delete_leftovers_done, on_error=self._leftover_error)

    def _delete_leftovers_worker(self):
        ok = 0
        err = 0
        for kind, p in self.leftovers:
            deleted = delete_registry_path(p) if kind == "registry" \
                else _delete_path(p)
            if deleted:
                ok += 1
            else:
                err += 1
        return ok, err

    def _delete_leftovers_done(self, ok, err) -> None:
        self.host.set_busy(False)
        self.leftovers = []
        self.info.setText("")
        self.host.log(t("log.leftovers_deleted", ok=ok, err=err))
        self.host.set_status(t("status.leftovers_deleted", ok=ok, err=err))
