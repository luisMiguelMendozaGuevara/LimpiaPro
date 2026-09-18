# LimpiaPro v2.9

## Correccion de seguridad (importante)

- **Nunca se atraviesan enlaces al limpiar.** Si la ubicacion de una
  categoria es un junction o un symlink, antes se seguia el enlace y se
  borraban los archivos REALES de la carpeta destino (por ejemplo, un
  enlace en `%TEMP%` apuntando a Documentos borraba los documentos).
  Ahora se elimina el enlace y el destino queda intacto.
- Nuevo test de regresion con un junction real (funciona sin permisos de
  administrador). El escaneo mide el enlace como un solo elemento en vez
  de recorrer el destino.

## Infraestructura (CI)

- **CI reparado**: el workflow estaba guardado con encoding corrupto y
  GitHub rechazaba todos los runs ("workflow file issue"). Ahora un test
  verifica que los archivos criticos sean UTF-8, que el workflow parsee
  como YAML con pasos por job y que cada `uses:` este pinneado por SHA.
- El job de lint instala las dependencias de runtime, para que Pyright
  resuelva PySide6 (antes fallaba con `reportMissingImports`).
- Actions actualizadas a versiones con Node 24: `checkout` v7.0.1,
  `setup-python` v7.0.0, `upload-artifact` v7.0.1.
- Tests compatibles con **Python 3.10** (`hashlib.file_digest` es 3.11+).
- Nueva dependencia de desarrollo: `pyyaml` (guard del workflow).

Verificado en CI: lint + tests en **Python 3.10, 3.11, 3.12, 3.13 y 3.14**
+ build del ejecutable.

## Descargas

- **LimpiaPro.exe** — un solo archivo.
- **LimpiaProPortable.zip** — portable OneDir, arranque instantaneo
  (recomendado).
- **LimpiaProDebug.exe** — variante con consola para diagnostico.
