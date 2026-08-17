"""
LimpiaPro Release Tool v2.2
===========================

Automatiza el proceso completo de release:
  1. Commit + tag de git
  2. Build del .exe (release y debug)
  3. Creación/actualización del acceso directo en el escritorio
  4. (Opcional) Subida del release a GitHub

Uso:
    py -3.12 release_tool.py              # Release completo
    py -3.12 release_tool.py --no-github  # Solo build + shortcut (sin GitHub)
    py -3.12 release_tool.py --shortcut   # Solo actualizar el acceso directo
    py -3.12 release_tool.py --exe        # Solo build del .exe + shortcut

El script debe ejecutarse desde el directorio raíz del proyecto.
"""

import os
import sys
import time
import json
import shutil
import subprocess
import datetime
import struct
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

APP_NAME = "LimpiaPro"
VERSION = "2.2"
PROJECT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
ICON_PATH = PROJECT_ROOT / "assets" / "limpiadora.ico"
EXE_PATH = DIST_DIR / f"{APP_NAME}.exe"
DEBUG_EXE_PATH = DIST_DIR / f"{APP_NAME}Debug.exe"

# Python launcher: preferir 'py -3.12' si existe, si no 'python'
PYTHON_CMD = None


def _detect_python():
    global PYTHON_CMD
    if PYTHON_CMD:
        return PYTHON_CMD
    try:
        r = subprocess.run("where py", shell=True, capture_output=True)
        if r.returncode == 0:
            PYTHON_CMD = "py -3.12"
            return PYTHON_CMD
    except Exception:
        pass
    PYTHON_CMD = "python"
    return PYTHON_CMD


def _run(cmd: str, *, cwd: Optional[Path] = None, check: bool = True,
         capture: bool = False) -> subprocess.CompletedProcess:
    print(f"  > {cmd}")
    return subprocess.run(
        cmd, shell=True, cwd=str(cwd or PROJECT_ROOT),
        check=check, capture_output=capture, text=True
    )


# ---------------------------------------------------------------------------
# Paso 1: Git commit + tag
# ---------------------------------------------------------------------------

def git_commit_and_tag() -> str:
    """Hace commit de todos los cambios y crea un tag v{VERSION}."""
    print("\n" + "=" * 60)
    print("PASO 1/3: Git commit + tag")
    print("=" * 60)

    # Verificar que estamos en un repo git
    r = _run("git status", capture=True, check=False)
    if r.returncode != 0:
        print("  ERROR: No se encontró un repositorio git en este directorio.")
        sys.exit(1)

    # Mostrar estado actual
    r = _run("git status --short", capture=True)
    status = r.stdout.strip()
    if not status:
        print("  Working tree limpio. Nada que commitear.")
    else:
        print(f"  Cambios detectados:\n{status}")
        _run("git add -A")
        tag_msg = f"v{VERSION}: Capa de seguridad, audit logging, CI/CD completo, RunOnce"
        commit_msg = (
            f"release v{VERSION}: auditoría completa aplicada\n\n"
            "Resumen de cambios:\n"
            "- Capa central de seguridad para borrado (is_safe_delete_target)\n"
            "- Snapshot inmutable entre Preview y Clean\n"
            "- Clasificación detallada de errores de eliminación\n"
            "- Protección de procesos críticos\n"
            "- Gestión transaccional de startup con rollback\n"
            "- Validación de snapshot de duplicados\n"
            "- Protección de RunOnce\n"
            "- Sistema de audit logging estructurado (JSONL)\n"
            "- CI/CD con Ruff + Pyright + Bandit + PyInstaller\n"
            "- Caché/logs en %LOCALAPPDATA%\n"
        )
        _run(f'git commit -m "{commit_msg}"')

    # Crear tag (puede fallar si ya existe, lo manejamos)
    tag_name = f"v{VERSION}"
    r = _run(f"git tag {tag_name}", check=False, capture=True)
    if r.returncode != 0:
        print(f"  El tag {tag_name} ya existe. Lo actualizo forzado.")
        _run(f"git tag -f {tag_name}")
    else:
        print(f"  Tag {tag_name} creado.")

    # Push
    print("  Intentando push a origin...")
    r = _run("git push", check=False)
    if r.returncode != 0:
        print("  Push falló (¿no hay remote configurado?). Continuando localmente.")
    r = _run(f"git push origin {tag_name}", check=False)
    if r.returncode != 0:
        print(f"  Push del tag {tag_name} falló. Continuando localmente.")

    return tag_name


# ---------------------------------------------------------------------------
# Paso 2: Build del .exe
# ---------------------------------------------------------------------------

def build_executables():
    """Construye LimpiaPro.exe y LimpiaProDebug.exe."""
    print("\n" + "=" * 60)
    print("PASO 2/3: Build de ejecutables")
    print("=" * 60)

    py = _detect_python()

    # Verificar PyInstaller
    r = _run(f"{py} -m PyInstaller --version", check=False, capture=True)
    if r.returncode != 0:
        print("  PyInstaller no está instalado. Instalando...")
        _run(f"{py} -m pip install pyinstaller")

    # Limpiar build anterior
    for p in (PROJECT_ROOT / "build", DIST_DIR):
        if p.exists():
            try:
                shutil.rmtree(p)
                print(f"  Limpiado: {p}")
            except Exception as e:
                print(f"  WARNING: No se pudo limpiar {p}: {e}")

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Build release
    print("\n  [Release] Construyendo LimpiaPro.exe...")
    t0 = time.time()
    _run(f"{py} -m PyInstaller --noconfirm --clean LimpiaPro.spec")
    print(f"  LimpiaPro.exe construido en {time.time() - t0:.1f}s")

    # Build debug
    print("\n  [Debug] Construyendo LimpiaProDebug.exe...")
    t0 = time.time()
    _run(f"{py} -m PyInstaller --noconfirm --clean LimpiaProDebug.spec")
    print(f"  LimpiaProDebug.exe construido en {time.time() - t0:.1f}s")

    # Verificar
    if not EXE_PATH.exists():
        print(f"  ERROR: No se generó {EXE_PATH}")
        sys.exit(1)
    if not DEBUG_EXE_PATH.exists():
        print(f"  ERROR: No se generó {DEBUG_EXE_PATH}")
        sys.exit(1)

    print(f"\n  ✅ LimpiaPro.exe:       {EXE_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  ✅ LimpiaProDebug.exe:  {DEBUG_EXE_PATH.stat().st_size / 1024 / 1024:.1f} MB")


# ---------------------------------------------------------------------------
# Paso 3: Actualizar acceso directo del escritorio
# ---------------------------------------------------------------------------

def create_shortcut(target: Path, shortcut_path: Path,
                    icon_path: Optional[Path] = None,
                    description: str = ""):
    """
    Crea un acceso directo de Windows (.lnk) usando PowerShell.
    """
    target_str = str(target).replace("'", "''")
    shortcut_str = str(shortcut_path).replace("'", "''")
    icon_str = str(icon_path).replace("'", "''") if icon_path else ""
    desc_str = description.replace("'", "''")

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_str}')
$Shortcut.TargetPath = '{target_str}'
$Shortcut.WorkingDirectory = '{str(target.parent).replace("'", "''")}'
"""
    if icon_str:
        ps_script += f"$Shortcut.IconLocation = '{icon_str},0'\n"
    if desc_str:
        ps_script += f"$Shortcut.Description = '{desc_str}'\n"
    ps_script += "$Shortcut.Save()\n"

    # Ejecutar PowerShell
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR al crear acceso directo: {result.stderr}")
        return False
    return True


def update_desktop_shortcut():
    """Crea o actualiza el acceso directo en el escritorio del usuario."""
    print("\n" + "=" * 60)
    print("PASO 3/3: Acceso directo del escritorio")
    print("=" * 60)

    if not EXE_PATH.exists():
        print(f"  ERROR: {EXE_PATH} no existe. Ejecuta primero el build.")
        sys.exit(1)

    # Escritorio del usuario actual
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if not desktop.exists():
        desktop = Path(os.environ.get("ONEDRIVE", "")) / "Desktop"

    if not desktop.exists():
        print(f"  ERROR: No se pudo encontrar el escritorio del usuario.")
        sys.exit(1)

    shortcut_path = desktop / f"{APP_NAME}.lnk"
    icon_path = ICON_PATH if ICON_PATH.exists() else None

    print(f"  Target:   {EXE_PATH}")
    print(f"  Shortcut: {shortcut_path}")
    if icon_path:
        print(f"  Icon:     {icon_path}")

    ok = create_shortcut(
        target=EXE_PATH,
        shortcut_path=shortcut_path,
        icon_path=icon_path,
        description=f"{APP_NAME} v{VERSION} - Limpiador del sistema"
    )

    if ok and shortcut_path.exists():
        print(f"  ✅ Acceso directo creado: {shortcut_path}")
        # Verificar tamaño del .lnk (mínimo razonable)
        size = shortcut_path.stat().st_size
        print(f"     Tamaño: {size} bytes")
    else:
        print("  ERROR: No se pudo crear el acceso directo.")


# ---------------------------------------------------------------------------
# Paso opcional: Subir a GitHub
# ---------------------------------------------------------------------------

def upload_to_github(tag_name: str):
    """Sube los .exe como release a GitHub (requiere GITHUB_TOKEN)."""
    print("\n" + "=" * 60)
    print("PASO EXTRA: Subida a GitHub")
    print("=" * 60)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  No se encontró GITHUB_TOKEN. Saltando subida a GitHub.")
        print("  Para habilitar: establece la variable de entorno GITHUB_TOKEN")
        print("  (Personal Access Token con scope 'repo')")
        return

    # Delegamos al script existente upload_release.py que ya maneja esto
    print("  Delegando a upload_release.py...")
    py = _detect_python()
    _run(f"{py} upload_release.py", check=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"  LimpiaPro Release Tool v{VERSION}")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"  Directorio: {PROJECT_ROOT}")

    args = sys.argv[1:]
    only_shortcut = "--shortcut" in args
    only_exe = "--exe" in args
    skip_github = "--no-github" in args or only_shortcut or only_exe

    if only_shortcut:
        update_desktop_shortcut()
        print("\n✅ Completado.")
        return

    # Paso 1: Git
    if not only_exe:
        tag_name = git_commit_and_tag()
    else:
        tag_name = f"v{VERSION}"

    # Paso 2: Build
    build_executables()

    # Paso 3: Shortcut
    update_desktop_shortcut()

    # Paso extra: GitHub
    if not skip_github:
        upload_to_github(tag_name)

    # Resumen final
    print("\n" + "=" * 60)
    print("  ✅ RELEASE COMPLETADO")
    print("=" * 60)
    print(f"  Versión:         v{VERSION}")
    print(f"  Ejecutable:      {EXE_PATH}")
    print(f"  Debug:           {DEBUG_EXE_PATH}")
    print(f"  Tamaño:          {EXE_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  Acceso directo:  {Path.home() / 'Desktop' / f'{APP_NAME}.lnk'}")
    print("\n  Para ejecutar: doble clic en el acceso directo del escritorio.")
    print("=" * 60)


if __name__ == "__main__":
    main()
