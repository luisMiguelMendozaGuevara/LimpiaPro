# LimpiaPro v2.10.1

## Los tamanos no aparecian: causa real, corregida

El sintoma era que Limpieza no mostraba los GB por categoria ni el total.
La causa no estaba en el analisis sino en los **datos de usuario
contaminados**: la suite de tests escribia en tu perfil real
(`%LOCALAPPDATA%\LimpiaPro`), y dejo dos cosas envenenadas:

1. `settings.json` con **"analizar automaticamente al iniciar" en false**,
   asi que la app no analizaba nada al arrancar.
2. Una cache "reciente" con categorias que no existen (`{"many": ...}`),
   que hacia que el arranque se saltara el analisis dando por buenos unos
   numeros que no eran de ninguna categoria.

Correcciones:

- **Los tests ya no tocan tus datos**: todo lo que la app escribe por
  usuario (cache, logs, ajustes) se puede redirigir con
  `LIMPIAPRO_DATA_DIR`, y la suite lo apunta a una carpeta temporal. Un
  test nuevo verifica que jamas se use la ruta real.
- **Robustez en la app**: una cache reciente que no describe las
  categorias actuales ya no evita el analisis (se ignora y se escanea).
- Si tenias el sintoma: revisa en **Ajustes** que "Analizar
  automaticamente al iniciar" este activado (en esta version los valores
  contaminados se descartan, pero ese ajuste es una preferencia tuya).

Verificado con el flujo real (sin cache, perfil real): temp 1.3 GB,
navegadores 1.5 GB, papelera 2.7 GB, aplicaciones 133 MB, historial
1.4 MB, reglas winapp2 5.4 GB, total 11.1 GB.

## Ademas

- La suite crece a 293 tests (incluye los guards de aislamiento, de
  cache y de la pagina de Ajustes).
- CI: lint (Ruff + Pyright + Bandit) y tests en **Python 3.10 a 3.14** +
  build del ejecutable.

## Descargas

| Archivo | Para que |
|---|---|
| `LimpiaProPortable.zip` | **Recomendado**: portable OneDir, arranque instantaneo |
| `LimpiaPro.zip` | El .exe de un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragil) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |
