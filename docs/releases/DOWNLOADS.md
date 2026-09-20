<!--
Guia de descargas compartida por todas las releases.
upload_release.py la añade al final de las notas de cada version.
-->

# Que descargar

Elige **una** opcion segun como quieras usar LimpiaPro. Todas contienen la
misma aplicacion; solo cambia la forma de instalarla o ejecutarla.

## Recomendado: instalador

**`LimpiaProSetup.exe`** (~34 MB)

- **Que es**: instalador con asistente en espanol o ingles.
- **Que hace**: instala el programa, crea el acceso directo (opcional) y lo
  registra en *Aplicaciones instaladas* con su propio desinstalador.
- **Ventajas**: arranque instantaneo, se actualiza sobre la version anterior
  sin dejar restos, puedes elegir la carpeta y **no pide administrador para
  instalar** (se instala por usuario en `%LOCALAPPDATA%\Programs\LimpiaPro`).
- **Elige esta si**: quieres tenerlo instalado como cualquier otro programa.

## Portable (sin instalar)

**`LimpiaProPortable.zip`** (~47 MB)

- **Que es**: la carpeta completa del programa comprimida (formato "OneDir").
- **Como se usa**: descomprime donde quieras y ejecuta `LimpiaPro.exe`.
- **Ventajas**: no instala nada ni toca el registro, arranque instantaneo y
  es la que menos falsos positivos genera en los antivirus.
- **Elige esta si**: lo quieres llevar en un pendrive, probarlo sin instalar
  o evitar que el antivirus se queje.

## Un solo archivo

**`LimpiaPro.zip`** (~47 MB) — el ejecutable dentro de un zip
**`LimpiaPro.exe`** (~47 MB) — el mismo ejecutable sin comprimir

- **Que es**: un unico `.exe` autocontenido.
- **Ventajas**: es un solo archivo, comodo de mover o adjuntar.
- **Inconvenientes**: se descomprime en `%TEMP%` en **cada arranque** (tarda
  unos segundos mas en abrir) y, al ser un `.exe` grande y sin firmar, los
  navegadores y antivirus lo truncan o ponen en cuarentena con mas
  facilidad; por eso se ofrece tambien dentro de un `.zip`.
- **Elige esta si**: prefieres un unico archivo y no te importa que la
  primera apertura tarde un poco mas.

## Solo para diagnostico

**`LimpiaProDebug.exe`** (~47 MB)

- **Que es**: la misma aplicacion con una consola visible.
- **Elige esta si**: algo falla y quieres ver los mensajes de error, o
  reportar un problema con detalles.

## Verificar la descarga

**`SHA256SUMS.txt`** — hashes SHA-256 de todos los archivos.

Util si Windows avisa de que el archivo "esta danado" (suele ser una
descarga cortada). En PowerShell:

```powershell
Get-FileHash .\LimpiaProSetup.exe -Algorithm SHA256
```

Compara el resultado con la linea correspondiente de `SHA256SUMS.txt`. Si no
coincide, la descarga se interrumpio: vuelve a bajarla.

## Comparativa rapida

| Archivo | Instala | Arranque | Acceso directo | Desinstalador | Tamano |
|---|---|---|---|---|---|
| `LimpiaProSetup.exe` | Si | Instantaneo | Si (opcional) | Si | ~34 MB |
| `LimpiaProPortable.zip` | No | Instantaneo | Manual | — | ~47 MB |
| `LimpiaPro.zip` | No | Lento (extrae a %TEMP%) | Manual | — | ~47 MB |
| `LimpiaPro.exe` | No | Lento (extrae a %TEMP%) | Manual | — | ~47 MB |
| `LimpiaProDebug.exe` | No | Lento (consola) | Manual | — | ~47 MB |

## Si Windows no deja ejecutarlo

1. **Comprueba el hash** con `SHA256SUMS.txt` (paso anterior).
2. **Usa el zip o el instalador** en lugar del `.exe` suelto.
3. **Desbloquea el archivo**: clic derecho > Propiedades > marca
   *Desbloquear* (los archivos descargados de Internet llevan esa marca).
4. Si el antivirus lo puso en cuarentena, añade una **exclusion** para la
   carpeta o el archivo.

## Requisitos

- Windows 10 u 11, **64 bits**.
- Para limpiar carpetas del sistema (TEMP, Windows Update, Prefetch...) la
  app pide permisos de administrador al arrancar. Si los rechazas, sigue
  funcionando con las funciones que no requieren admin.
