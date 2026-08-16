# LimpiaPro

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A modern, open-source system cleaner for Windows, inspired by CCleaner — with a native-feeling dark UI built on [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (Windows 11 Mica backdrop, system accent color, Fluent fonts).

> [!WARNING]
> LimpiaPro deletes **real files** from your system: temp files, caches, history, and anything matching the bundled `winapp2.ini` rules. It automatically requests administrator privileges on launch. Always review what will be deleted before confirming, and use it at your own risk.

<!-- TODO: add a screenshot here, e.g. <p align="center"><img src="docs/screenshot.png" width="700"></p> -->

## Features

- **System cleanup** — scans and cleans Windows temp files, browser caches, recycle bin, app data and more, driven by the bundled community-maintained [winapp2.ini](https://github.com/MoscaDotTo/Winapp2) database (4,000+ entries, with full `Detect`/`ExcludeKey`/`RECURSE`/`REMOVESELF` support).
- **Duplicate finder** — multithreaded duplicate file scanner using BLAKE2b hashing.
- **Startup manager** — view, enable and disable `Run`/`RunOnce` registry entries and startup-folder items.
- **Scheduled tasks & processes** — list and toggle scheduled tasks; inspect and kill running processes.
- **Windows Update cleanup** — DISM component-store cleanup to reclaim disk space.
- **Advanced uninstaller** — lists installed apps, launches their uninstallers safely (argument lists, no shell), and searches for leftover files and registry keys afterwards.
- **Activity log** — a built-in log page, plus `limpiapro_error.log` next to the executable for diagnostics.
- **Optional desktop pet** — `mascota.py`, a small animated companion with motivational messages (in Spanish).

The UI, code comments and docstrings are in Spanish.

## Requirements

- Windows 10 or 11
- Python 3.12+

## Getting started

### From a release (no Python needed)

Download `LimpiaPro.exe` from the [Releases](../../releases) page and run it. Accept the UAC prompt — the app needs administrator privileges to clean system locations.

### From source

```bash
git clone https://github.com/luisMiguelMendozaGuevara/LimpiaPro.git
cd LimpiaPro
pip install -r requirements.txt
python limpiador.py
```

On Windows you can also just double-click `LimpiaPro.bat`.

## Building the executable

```bash
pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm LimpiaPro.spec
```

This produces `dist/LimpiaPro.exe` (one-file build, no console window, icon included).

## Running tests

```bash
python -m pytest tests/ -v
```

## Project structure

| Path | Role |
| --- | --- |
| `limpiador.py` | Entry point |
| `limpiapro/` | Core package: categories, winapp2 parser, duplicates, startup, tasks, processes, uninstaller, utils |
| `limpiapro/ui/` | GUI pages: clean, duplicates, startup, update, uninstall, log |
| `mascota.py` | Optional desktop pet |
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
