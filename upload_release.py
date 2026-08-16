"""
Script para actualizar el ejecutable de depuracion y subir un release a GitHub.
Ejecutar con: py -3.12 upload_release.py
"""
import os
import sys
import json
import subprocess
import datetime
import urllib.request
import urllib.error
import mimetypes

REPO_OWNER = "luisMiguelMendozaGuevara"
REPO_NAME = "LimpiaPro"

def get_latest_source_mtime():
    """Obtiene la fecha de modificacion mas reciente de los archivos fuente."""
    latest = 0
    for root, dirs, files in os.walk('.'):
        # Ignorar directorios que no son codigo fuente
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'build', 'dist', 'assets', '.opencode']]
        for file in files:
            if file.endswith('.py') or file == 'winapp2.ini':
                p = os.path.join(root, file)
                mtime = os.path.getmtime(p)
                if mtime > latest:
                    latest = mtime
    return latest

def check_exe_up_to_date(exe_path):
    """Comprueba si un exe esta actualizado respecto al codigo fuente."""
    if not os.path.exists(exe_path):
        return False
    src_mtime = get_latest_source_mtime()
    exe_mtime = os.path.getmtime(exe_path)
    return exe_mtime >= src_mtime

def build_debug_exe():
    """Construye el ejecutable de depuracion usando LimpiaProDebug.spec."""
    print("\n[1/3] Construyendo LimpiaProDebug.exe...")
    # El SKILL.md indica usar python 3.12
    python_cmd = "py -3.12" if subprocess.run("where py", shell=True, capture_output=True).returncode == 0 else "python"
    cmd = f"{python_cmd} -m PyInstaller --noconfirm --clean LimpiaProDebug.spec"
    print(f"Ejecutando: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Error: PyInstaller fallo al compilar LimpiaProDebug.exe")
        sys.exit(1)
    print("LimpiaProDebug.exe construido exitosamente.")

def build_release_exe():
    """Construye el ejecutable de release usando LimpiaPro.spec."""
    print("\n[1/3] Construyendo LimpiaPro.exe...")
    python_cmd = "py -3.12" if subprocess.run("where py", shell=True, capture_output=True).returncode == 0 else "python"
    cmd = f"{python_cmd} -m PyInstaller --noconfirm --clean LimpiaPro.spec"
    print(f"Ejecutando: {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Error: PyInstaller fallo al compilar LimpiaPro.exe")
        sys.exit(1)
    print("LimpiaPro.exe construido exitosamente.")

def github_api_request(method, endpoint, data=None, headers=None, file_path=None):
    """Hace una peticion a la API de GitHub."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}{endpoint}"
    if headers is None:
        headers = {}
    
    if file_path:
        # Para subir assets, la URL es diferente y el content-type es el del archivo
        headers['Content-Type'] = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        with open(file_path, 'rb') as f:
            data = f.read()
    elif data and not isinstance(data, bytes):
        data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"Error en la API de GitHub: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
        sys.exit(1)

def create_release(token, tag_name, name, body):
    """Crea un nuevo release en GitHub."""
    print("\n[2/3] Creando release en GitHub...")
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    data = {
        "tag_name": tag_name,
        "target_commitish": "main",
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": False
    }
    release = github_api_request('POST', '/releases', data=data, headers=headers)
    print(f"Release creado: {release['html_url']}")
    return release

def upload_asset(token, upload_url, file_path):
    """Sube un archivo al release."""
    print(f"Subiendo {os.path.basename(file_path)}...")
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    # La URL de subida viene con { ?name,label } al final, hay que reemplazarla
    upload_url = upload_url.split('{')[0] + f"?name={os.path.basename(file_path)}"
    url = upload_url
    
    with open(file_path, 'rb') as f:
        data = f.read()
    
    headers['Content-Type'] = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    headers['Content-Length'] = str(len(data))
    
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Subido: {os.path.basename(file_path)} ({len(data)} bytes)")
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"Error al subir asset: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
        sys.exit(1)

def main():
    print("=== LimpiaPro Release Tool ===")
    
    # Verificar y compilar exes si es necesario
    exe_path = os.path.join('dist', 'LimpiaPro.exe')
    debug_path = os.path.join('dist', 'LimpiaProDebug.exe')
    
    if not check_exe_up_to_date(exe_path):
        build_release_exe()
    else:
        print("LimpiaPro.exe ya esta actualizado.")
        
    if not check_exe_up_to_date(debug_path):
        build_debug_exe()
    else:
        print("LimpiaProDebug.exe ya esta actualizado.")

    # Pedir token de GitHub
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("\nNo se encontro la variable de entorno GITHUB_TOKEN.")
        token = input("Introduce tu GitHub Personal Access Token (scope 'repo'): ").strip()
        if not token:
            print("Token vacio. Abortando.")
            sys.exit(1)

    # Datos del release
    today = datetime.date.today()
    tag_name = f"v{today.strftime('%Y.%m.%d')}"
    name = f"LimpiaPro Release {today.strftime('%Y-%m-%d')}"
    body = f"Release automatizado del {today.strftime('%d/%m/%Y')}.\n\n" \
           f"- `LimpiaPro.exe`: Version de produccion (sin consola).\n" \
           f"- `LimpiaProDebug.exe`: Version de depuracion (con consola y traces)."
           
    # Crear release y subir assets
    release = create_release(token, tag_name, name, body)
    upload_url = release['upload_url']
    
    upload_asset(token, upload_url, exe_path)
    upload_asset(token, upload_url, debug_path)
    
    print("\n=== Proceso completado con exito! ===")
    print(f"Puedes ver tu release aqui: {release['html_url']}")

if __name__ == "__main__":
    main()
