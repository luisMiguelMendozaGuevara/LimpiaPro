# LimpiaPro v2.11

## Instalador para Windows (nuevo)

Ahora puedes instalar LimpiaPro como cualquier programa, en lugar de
descomprimir un zip a mano:

- **`LimpiaProSetup.exe`** (34 MB): asistente con siguiente/siguiente en
  espanol o ingles, carpeta de instalacion y opcion de acceso directo.
- **Se instala sin pedir administrador** (por usuario, en
  `%LOCALAPPDATA%\Programs\LimpiaPro`); la app sigue elevandose sola
  cuando necesita permisos de sistema.
- **Aparece en "Aplicaciones instaladas"** con nombre, version, autor e
  icono, y tiene **desinstalador** propio.
- **Actualiza en el mismo sitio**: instalar una version nueva reemplaza la
  anterior sin dejar restos.
- **Opciones del asistente**: acceso directo en el escritorio, entrada en
  el menu Inicio, iniciar con Windows (desmarcado) y "ejecutar LimpiaPro"
  al terminar.

### Tus datos se conservan al desinstalar

La desinstalacion borra solo el programa. Los ajustes, la cache y los logs
(`%LOCALAPPDATA%\LimpiaPro`) son tuyos y **se mantienen**; si quieres
eliminarlos tambien, ejecuta el desinstalador con `PURGEDATA=1`:

```
"%LOCALAPPDATA%\Programs\LimpiaPro\unins000.exe" /PURGEDATA=1
```

### Instalacion silenciosa (automatizable)

```
LimpiaProSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

## Descargas

| Archivo | Para que |
|---|---|
| **`LimpiaProSetup.exe`** | **Recomendado**: instalador con desinstalador |
| `LimpiaProPortable.zip` | Portable: descomprime y ejecuta, sin instalar |
| `LimpiaPro.zip` | Un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragil) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |

Si Windows avisa de que el archivo "esta danado" al descargar, revisa el
hash con `SHA256SUMS.txt` y usa el zip o el instalador (los `.exe` sueltos
se truncan con mas facilidad al descargar).
