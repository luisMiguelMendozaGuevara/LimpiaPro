# LimpiaPro v2.10.2

## La opcion de idioma ya funciona

Elegir **Ingles** en Ajustes no cambiaba nada: el idioma se guardaba y se
aplicaba solo en el momento de elegirlo, pero **al iniciar la aplicacion
nadie leia esa preferencia**, asi que la interfaz se quedaba siempre en el
idioma detectado de Windows.

- Ahora la ventana aplica el idioma guardado **antes de construir ningun
  widget**, de modo que la interfaz completa sale en el idioma elegido.
- El cambio visible ocurre al reiniciar (la propia pagina de Ajustes lo
  avisa con un mensaje claro al guardar): `Espanol`, `Ingles` o
  `Automatico` (el de Windows).

Si tenias la sensacion de que el selector no hacia nada, era esto: vuelve
a elegir el idioma, cierra la aplicacion y abrela de nuevo.

## Nota sobre ajustes contaminados

En versiones anteriores la suite de tests escribia en el perfil real, y
algunos ajustes pudieron quedar cambiados (`auto_analyze`, `theme`,
`language`). v2.10.1 ya aislo los tests; si notas algo raro, revisa la
pagina de Ajustes: los valores por defecto son tema Oscuro, idioma
Automatico, analizar al iniciar y confirmar antes de limpiar.

## Descargas

| Archivo | Para que |
|---|---|
| `LimpiaProPortable.zip` | **Recomendado**: portable OneDir, arranque instantaneo |
| `LimpiaPro.zip` | El .exe de un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragil) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |
