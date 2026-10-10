# LimpiaPro v2.11.3

## Ya no se borran los accesos directos anclados

La limpieza incluia una categoria "Historial reciente" que vaciaba la
carpeta `%APPDATA%\Microsoft\Windows\Recent`. Esa carpeta no es basura:
guarda tus **accesos directos de documentos recientes**, los **anclajes de
Acceso rapido** y las **listas de salto** del Explorador y de la barra de
tareas. Al limpiarla desaparecian cosas que tu mismo habias anclado (se veia
como "se borran mis accesos directos en Documentos").

- Se elimino esa categoria por completo.
- Ademas, el arbol `Recent` entero queda **protegido**: ninguna categoria ni
  regla de `winapp2.ini` puede listarlo, medirlo ni borrarlo.
- El analisis ya no muestra archivos que la capa de seguridad vaya a
  rechazar (antes veias "archivos que no se borran").

## Ejecutables mas ligeros y con metadatos

- Los binarios incluyen ahora **recurso de version** (`CompanyName`,
  `FileVersion`, copyright): antes salian "anonimos" ante Windows y ante
  algunos antivirus.
- Se recortan componentes de Qt que una app de escritorio nunca carga:
  el paquete baja de ~49 MB a ~31 MB.
- La release puede firmarse (Authenticode) si configuras un certificado
  (`LIMPIAPRO_SIGN_PFX` o `LIMPIAPRO_SIGN_THUMBPRINT`).

## Variante de consola

`LimpiaProDebug.exe` (consola, para ver trazas al depurar) se reconstruye sin
la ruta de depuracion del bootloader, que abortaba el empaquetado en
PyInstaller 6.22.

## Verificacion

Cada descarga trae su hash SHA-256 en `SHA256SUMS.txt`.
