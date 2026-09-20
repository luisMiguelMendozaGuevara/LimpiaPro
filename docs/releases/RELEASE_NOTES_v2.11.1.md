# LimpiaPro v2.11.1

## El instalador ahora avisa y deja elegir la carpeta

Dos mejoras sobre el instalador de v2.11:

### Detecta la version instalada y lo dice

Si LimpiaPro ya esta instalado, el asistente lo avisa antes de empezar,
indicando **que version tienes y en que carpeta esta**, por ejemplo:

> LimpiaPro 2.11 ya esta instalado en:
> C:\Users\...\AppData\Local\Programs\LimpiaPro
>
> Se reinstalara sobre esa misma carpeta (puedes cambiarla en el siguiente
> paso).

- Si la version instalada es **distinta**, el aviso dice a que version se
  actualizara.
- La actualizacion se hace **en el mismo sitio** y deja una sola entrada en
  "Aplicaciones instaladas" (no se duplica).

### Siempre se puede elegir la carpeta

Inno Setup ocultaba la pagina "Seleccione la Carpeta de Destino" en las
actualizaciones (con la ruta anterior ya elegida), por eso parecia que no
existia. Ahora **aparece siempre**, con la ruta actual rellenada y el boton
*Examinar...* para cambiarla.

- Si eliges **otra carpeta**, al terminar se **elimina la instalacion
  anterior** en lugar de dejarla huerfana.

### Ademas

- Si LimpiaPro esta **abierto** durante la instalacion o desinstalacion,
  el asistente lo cierra de forma ordenada (Restart Manager de Windows) en
  vez de fallar por archivos en uso. No lo vuelve a abrir solo.

Verificado: actualizacion en el mismo sitio (una sola entrada en el
registro), instalacion en carpeta distinta (borra la anterior), arranque
del exe instalado y captura del asistente mostrando el aviso y la pagina
de carpeta.

## Descargas

| Archivo | Para que |
|---|---|
| **`LimpiaProSetup.exe`** | **Recomendado**: instalador con desinstalador |
| `LimpiaProPortable.zip` | Portable: descomprime y ejecuta, sin instalar |
| `LimpiaPro.zip` | Un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragil) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |
