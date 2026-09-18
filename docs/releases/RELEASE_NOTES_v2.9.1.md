# LimpiaPro v2.9.1

## Si Windows dice que el .exe "esta danado" al descargarlo

El archivo subido a GitHub es correcto (los SHA256 estan en
`SHA256SUMS.txt`), pero un `.exe` suelto de ~50 MB es justo lo que los
navegadores y los antivirus truncan o ponen en cuarentena al descargar:
el resultado es un ejecutable incompleto y Windows avisa de que esta
danado. Para v2.9.1 eso queda resuelto asi:

- **Descarga `LimpiaPro.zip`** (o `LimpiaProPortable.zip`) en vez del
  `.exe` suelto: dentro del zip los bytes llegan intactos. Descomprime y
  ejecuta.
- **Verifica la descarga** con `SHA256SUMS.txt` (PowerShell):
  `Get-FileHash LimpiaPro.exe -Algorithm SHA256`
  Si el hash no coincide, la descarga se corto: vuelve a bajarla.
- Si aun asi no arranca: clic derecho en el exe -> **Propiedades** ->
  marca **Desbloquear** (viene de Internet); y si tu antivirus lo puso en
  cuarentena, anade una exclusion para la carpeta.
- **Recomendado**: `LimpiaProPortable.zip` (arranque instantaneo y menos
  falsos positivos que un one-file).

## Correcciones

- **Cargar reglas winapp2 estaba roto**: `winapp_loaded` era
  `Signal(int)` y PySide6 rechazaba la conexion con `done(PyObject)`
  (`RuntimeError: Failed to connect signal...`), asi que cargar un
  `winapp2.ini` no hacia nada. Ahora es `Signal(object)` y entrega el
  conteo de reglas. Test de regresion incluido.
- **Nunca se atraviesan enlaces al limpiar**: si la ubicacion de una
  categoria es un junction o un symlink, se elimina el enlace y el
  destino queda intacto (antes se borraban los archivos reales del
  destino). Test de regresion con un junction real.
- La descripcion de la categoria winapp2 ahora se traduce (antes
  escribia "detected N apps" en ingles fijo).
- Las rutas de Windows usan `%SystemRoot%` en vez de `C:\Windows` fijo
  (Windows puede estar en otra unidad o reubicado).

## Verificado en CI

Lint (Ruff + Pyright + Bandit) y tests en **Python 3.10, 3.11, 3.12,
3.13 y 3.14**, mas build del ejecutable.

## Descargas

| Archivo | Para que |
|---|---|
| `LimpiaProPortable.zip` | **Recomendado**: portable OneDir, arranque instantaneo |
| `LimpiaPro.zip` | El .exe de un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragile) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |
