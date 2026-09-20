# LimpiaPro v2.11.2

## La ventana ya se abre en primer plano

Al arrancar, LimpiaPro pide permisos (UAC) y se relanza elevada. Windows
**niega el primer plano al proceso nuevo** (el dialogo de UAC era el ultimo
en tenerlo), asi que la ventana se abria **detras** del resto y parecia que
no habia arrancado.

- Ahora, al mostrarse, la ventana se **eleva y se activa**; si Windows
  insiste en mantenerla detras, se reintenta con las llamadas nativas
  (`ShowWindow`/`BringWindowToTop`/`SetForegroundWindow`) un cuarto de
  segundo despues.
- Comprobado: la ventana queda visible, activa y no minimizada.

## El analisis arranca solo al abrir

Si, la app analiza por su cuenta **~0,25 s despues** de aparecer la ventana
(no hace falta pulsar nada), siempre que el ajuste "Analizar
automaticamente al iniciar" este activo (Ajustes > Comportamiento).

- Si en disco hay una **cache reciente** que describe las categorias
  actuales, se muestran esos numeros **al instante** y no se reescanea
  (la barra de estado lo indica con la antiguedad). El boton **Analizar**
  fuerza un analisis real.
- El arranque del analisis (o el uso de la cache) queda ahora registrado en
  el log para poder verificarlo.

## Boton "Limpiar seleccionado" con papelera

El boton principal de limpieza usa ahora un **icono de papelera** (antes un
destello), mas claro: es la accion que borra lo seleccionado.

## Descargas

| Archivo | Para que |
|---|---|
| **`LimpiaProSetup.exe`** | **Recomendado**: instalador con desinstalador |
| `LimpiaProPortable.zip` | Portable: descomprime y ejecuta, sin instalar |
| `LimpiaPro.zip` | Un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragil) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |
