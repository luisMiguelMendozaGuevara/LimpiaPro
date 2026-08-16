# LimpiaPro

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

LimpiaPro is a free, open-source cleaner for Windows, inspired by CCleaner — with a native-feeling dark UI built on [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (Windows 11 Mica backdrop, system accent color, Fluent fonts). It frees up disk space by removing temporary files and caches, and adds tools to manage startup programs, find duplicate files and uninstall apps cleanly.

> [!WARNING]
> LimpiaPro deletes **real files** from your system: temp files, caches, history, and anything matching the bundled `winapp2.ini` rules. It automatically requests administrator privileges on launch. Always review what will be deleted before confirming, and use it at your own risk.

<!-- TODO: add a screenshot here, e.g. <p align="center"><img src="docs/screenshot.png" width="700"></p> -->

## How to use it (no coding needed)

You don't need any technical knowledge. The app automatically displays in **Spanish or English, following your Windows display language**, and every action is just buttons, lists and confirmations — **nothing is ever deleted until you review and confirm it**.

### 1. Start the app

- If you downloaded `LimpiaPro.exe` from the [Releases](../../releases) page: double-click it.
- If you have the source code: double-click `LimpiaPro.bat`.
- Windows will show a permission prompt (User Account Control). Click **Yes** — cleaning system files requires administrator rights.

### 2. Clean your PC — "Limpieza" tab

1. Wait a few seconds while the app analyzes your PC; the sizes update as it goes.
2. Each row is a category (temp files, browser caches, recycle bin, ...) with a checkbox. Uncheck anything you don't want to touch.
3. Click **Vista previa** / *Preview* to see the exact list of files that would be deleted (first 1,000 entries).
4. Click **Limpiar seleccionado** / *Clean selected*, review the summary and confirm. The app shows how much space was freed.

### 3. Speed up startup — "Inicio" tab

Three sub-tabs:

- **Apps de inicio** — programs that launch with Windows. Select one and click *Desactivar seleccionada* / *Disable selected* to stop it. You can undo this later from *Reactivar desactivadas...* / *Re-enable disabled...*.
- **Tareas programadas** — Windows scheduled tasks, with activate/deactivate buttons.
- **Procesos activos** — running processes. Select one and *Terminar proceso* / *End process* closes it. Be careful: force-closing a program can lose unsaved work.

### 4. Find duplicate files — "Duplicados" tab

1. Click the folder box to choose where to search (for example, your Documents folder).
2. Click **Buscar duplicados** / *Find duplicates* and wait for the scan.
3. Results come in groups: an "original" file and its duplicates. Check the copies you want to remove and click *Eliminar seleccionados* / *Delete selected*. Keep at least one copy per group.

### 5. Windows Update cleanup — "Windows Update" tab

Removes old update leftovers that Windows keeps "just in case". Click **Analizar** / *Analyze* to measure, then **Limpiar** / *Clean* to clean. It can take several minutes and requires administrator.

### 6. Uninstall apps — "Desinstalar" tab

- Lists the programs installed on your PC. Select one and click *Desinstalar* / *Uninstall* to run its normal uninstaller.
- After uninstalling, *Buscar restos* / *Find leftovers* finds leftover files and registry entries the uninstaller missed, and can delete them.

### 7. See what the app did — "Registro" tab

A log of everything LimpiaPro has done in this session.

### Frequently asked questions

- **Is it safe?** LimpiaPro always shows a preview and asks for confirmation before deleting anything. It only removes temp files, caches and similar junk — never your documents or photos. The one to watch: the *Papelera* option really empties the Recycle Bin.
- **Why does it ask for administrator?** System locations (Windows temp, update cache, ...) are protected; without admin rights those categories cannot be cleaned.
- **Something looks wrong. Where do I report it?** Look for `limpiapro_error.log` in the same folder as the app — it records any errors and is useful when opening a GitHub issue.

---

## For developers

### Features

- **System cleanup** — scans and cleans Windows temp files, browser caches, recycle bin, app data and more, driven by the bundled community-maintained [winapp2.ini](https://github.com/MoscaDotTo/Winapp2) database (4,000+ entries, with full `Detect`/`ExcludeKey`/`RECURSE`/`REMOVESELF` support).
- **Duplicate finder** — multithreaded duplicate file scanner using BLAKE2b hashing.
- **Startup manager** — view, enable and disable `Run`/`RunOnce` registry entries and startup-folder items.
- **Scheduled tasks & processes** — list and toggle scheduled tasks; inspect and kill running processes.
- **Windows Update cleanup** — DISM component-store cleanup to reclaim disk space.
- **Advanced uninstaller** — lists installed apps, launches their uninstallers safely (argument lists, no shell), and searches for leftover files and registry keys afterwards.
- **Activity log** — a built-in log page, plus `limpiapro_error.log` next to the executable for diagnostics.

### Requirements

- Windows 10 or 11
- Python 3.12+

### Getting started

#### From a release (no Python needed)

Download `LimpiaPro.exe` from the [Releases](../../releases) page and run it. Accept the UAC prompt — the app needs administrator privileges to clean system locations.

#### From source

```bash
git clone https://github.com/luisMiguelMendozaGuevara/LimpiaPro.git
cd LimpiaPro
pip install -r requirements.txt
python limpiador.py
```

On Windows you can also just double-click `LimpiaPro.bat`.

### Building the executable

```bash
pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm LimpiaPro.spec
```

This produces `dist/LimpiaPro.exe` (one-file build, no console window, icon included).

### Running tests

```bash
python -m pytest tests/ -v
```

### Technical debt

Known limitations, tracked to fix in future iterations:

- **CI / tooling** — the CI workflow only runs pytest on `windows-latest`. No linter, type checker (mypy/pyright) or automated executable build is wired up yet.
- **UI layer typing** — the core package (`limpiapro/`, `ui/widgets.py`, `ui/theme.py`) is typed; the UI pages still rely mostly on runtime attribute access without static annotations.
- **UI tests** — `tests/` cover the core logic, the winapp2 parser and the `run_async`/`post_ui` contract, but there are no end-to-end tests driving a real Tk window.
- **Startup manager mutation** — toggling a startup entry is not transactional: if one registry key fails mid-way, the earlier ones are already applied and are not rolled back.

### Project structure

| Path | Role |
| --- | --- |
| `limpiador.py` | Entry point |
| `limpiapro/` | Core package: categories, winapp2 parser, duplicates, startup, tasks, processes, uninstaller, utils |
| `limpiapro/ui/` | GUI pages: clean, duplicates, startup, update, uninstall, log |
| `winapp2.ini` | Community cleaning-rules database |
| `tests/` | pytest suite |
| `LimpiaPro.spec` | PyInstaller build spec |

## Support / Donate

LimpiaPro is developed and maintained in my free time, for free. If it has been useful to you and you'd like to support its development, you can make a donation. Any amount helps and is greatly appreciated:

👉 [Donate via PayPal](https://paypal.me/BLACWARG)

Thank you for your support!

---

## Credits

- **[Winapp2](https://github.com/MoscaDotTo/Winapp2)** — the bundled `winapp2.ini` cleaning-rules database, licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) by its contributors. It is redistributed unmodified, with its original attribution header intact.
- Built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter).

## License

The code of this project is licensed under the [MIT License](LICENSE).

`winapp2.ini` is a third-party work distributed under its own CC BY-SA 4.0 license; that file is not covered by the MIT license.
