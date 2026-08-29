"""Build and publish the versioned LimpiaPro GitHub release.

Usage:
    py -3.12 upload_release.py
    GITHUB_TOKEN=... py -3.12 upload_release.py

The script is deliberately idempotent: it uses the application version/tag,
updates an existing release when present, replaces assets with the same names,
and never asks for a token interactively.
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from limpiapro import APP_NAME, APP_VERSION

REPO_OWNER = "luisMiguelMendozaGuevara"
REPO_NAME = "LimpiaPro"
PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
TAG_NAME = f"v{APP_VERSION}"
ASSETS = (DIST_DIR / f"{APP_NAME}.exe", DIST_DIR / f"{APP_NAME}Debug.exe")
PORTABLE_DIR = DIST_DIR / f"{APP_NAME}Portable"
PORTABLE_ZIP = DIST_DIR / f"{APP_NAME}Portable.zip"


def _zip_portable() -> Path:
    """Zip the OneDir build (fast-start portable variant) for upload."""
    import zipfile

    if PORTABLE_ZIP.exists():
        PORTABLE_ZIP.unlink()
    with zipfile.ZipFile(PORTABLE_ZIP, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        for base, _dirs, files in os.walk(PORTABLE_DIR):
            for name in files:
                full = Path(base) / name
                zf.write(full, full.relative_to(PORTABLE_DIR.parent))
    return PORTABLE_ZIP


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("  >", " ".join(args))
    return subprocess.run(args, cwd=PROJECT_ROOT, check=check, text=True)


def build_executables() -> None:
    """Build the three binaries and run their non-interactive smoke tests.

    - LimpiaPro.spec        one-file exe (single-download asset)
    - LimpiaProDebug.spec   console variant for troubleshooting
    - LimpiaProPortable.spec OneDir folder zipped as the portable asset
                            (starts instantly: no %TEMP% unpacking)
    """
    for spec, exe in (("LimpiaPro.spec", ASSETS[0]),
                      ("LimpiaProDebug.spec", ASSETS[1]),
                      ("LimpiaProPortable.spec", PORTABLE_DIR / f"{APP_NAME}.exe")):
        _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec])
        if not exe.exists():
            raise RuntimeError(f"PyInstaller did not create {exe}")
        _run([str(exe), "--smoke-test"])
    portable_zip = _zip_portable()
    print(f"Portable zipped: {portable_zip} "
          f"({portable_zip.stat().st_size} bytes)")


def _api_request(
    method: str,
    endpoint: str,
    token: str,
    data: dict | None = None,
    *,
    upload_url: str | None = None,
    raw: bytes | None = None,
    content_type: str = "application/json",
    allow_404: bool = False,
):
    url = upload_url or f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}{endpoint}"
    body = raw
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "LimpiaPro-release-tool",
    }
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    if body is not None:
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(body))
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            return json.loads(payload.decode("utf-8")) if payload else {}
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url}: {exc.code} {detail}") from exc


def _release_notes() -> str:
    notes = PROJECT_ROOT / "docs" / "releases" / f"RELEASE_NOTES_v{APP_VERSION}.md"
    if notes.exists():
        return notes.read_text(encoding="utf-8")
    return f"{APP_NAME} {TAG_NAME}\n\nAutomated Windows release."


def publish_release(token: str) -> str:
    """Create/update the release and replace its two binary assets."""
    release = _api_request("GET", f"/releases/tags/{TAG_NAME}", token, allow_404=True)
    payload = {
        "tag_name": TAG_NAME,
        "target_commitish": "main",
        "name": f"{APP_NAME} {TAG_NAME}",
        "body": _release_notes(),
        "draft": False,
        "prerelease": False,
    }
    if release is None:
        release = _api_request("POST", "/releases", token, data=payload)
        print(f"Release creado: {release['html_url']}")
    else:
        release = _api_request("PATCH", f"/releases/{release['id']}", token, data=payload)
        print(f"Release actualizado: {release['html_url']}")
    if release is None:
        raise RuntimeError("GitHub returned no release payload")

    assets = _api_request("GET", f"/releases/{release['id']}/assets", token)
    if assets is None:
        assets = []
    existing = {asset["name"]: asset["id"] for asset in assets}
    upload_assets = list(ASSETS) + [PORTABLE_ZIP]
    for asset_path in upload_assets:
        if asset_path.name in existing:
            _api_request("DELETE", f"/releases/assets/{existing[asset_path.name]}", token)
            print(f"Asset anterior eliminado: {asset_path.name}")
        raw = asset_path.read_bytes()
        upload = release["upload_url"].split("{")[0]
        upload += "?" + urllib.parse.urlencode({"name": asset_path.name})
        _api_request(
            "POST",
            "",
            token,
            upload_url=upload,
            raw=raw,
            content_type=mimetypes.guess_type(asset_path.name)[0]
            or "application/octet-stream",
        )
        print(f"Asset subido: {asset_path.name} ({len(raw)} bytes)")
    return release["html_url"]


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: define GITHUB_TOKEN antes de publicar el release.", file=sys.stderr)
        return 2
    print(f"=== {APP_NAME} {TAG_NAME} release ===")
    build_executables()
    url = publish_release(token)
    print(f"Release publicado: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
