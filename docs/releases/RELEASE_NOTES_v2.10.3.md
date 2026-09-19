# LimpiaPro v2.10.3

## El idioma cambia al instante (sin reiniciar)

Elegir **Ingles** en Ajustes guardaba la preferencia y esta ya se aplicaba
al reiniciar (v2.10.2), pero la ventana abierta seguia en el idioma
anterior: los textos se fijan cuando se construye cada widget, asi que
cambiarlos exigia reconstruir la interfaz.

- Ahora la aplicacion **reconstruye la ventana al momento** cuando cambias
  el idioma: se conserva la posicion, el tamano y la pagina en la que
  estabas (vuelves a Ajustes), y el controlador se comparte, asi que no se
  pierde ningun analisis ni limpieza en curso.
- El resultado es inmediato: eliges *Ingles* y todo —menu, titulos, botones
  y textos— pasa a ingles sin cerrar la aplicacion. Lo mismo de vuelta a
  *Espanol* o a *Automatico* (el idioma de Windows).
- La nota de la pagina ahora dice "El idioma cambia al instante" y el
  mensaje de estado "Idioma aplicado".

## Como comprobarlo

1. Abre Ajustes (engranaje del menu).
2. En **Idioma**, elige *Ingles*.
3. La ventana se reconstruye sola y veras la interfaz en ingles.

## Descargas

| Archivo | Para que |
|---|---|
| `LimpiaProPortable.zip` | **Recomendado**: portable OneDir, arranque instantaneo |
| `LimpiaPro.zip` | El .exe de un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragil) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |
