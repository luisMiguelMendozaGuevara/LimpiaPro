# LimpiaPro v2.10

## Pagina de Ajustes (nueva)

Un septimo apartado en el menu, con todo lo configurable en un sitio:

- **Apariencia**: tema Oscuro / Claro / Sistema.
- **Idioma**: Automatico, Espanol o Ingles (el texto visible cambia al
  reiniciar; queda avisado en la propia pagina).
- **Comportamiento**: analizar automaticamente al iniciar, confirmar antes
  de limpiar y **mover a la papelera en vez de borrar** (antes era una
  casilla suelta en la barra de Limpieza).
- **Ubicaciones**: abrir la carpeta de datos, los logs y la cache.
- Todo se guarda al instante y el conmutador de tema del lateral queda
  sincronizado con esta pagina.

## Barra de Limpieza reorganizada

- Dos grupos visuales: arriba las herramientas (Seleccionar todo, Vista
  previa, Reglas winapp2 y **Analizar de nuevo**, nuevo), y abajo a la
  derecha las acciones principales (Cancelar / Limpiar seleccionado).
- La casilla de papelera se movio a Ajustes: la barra queda mas limpia y
  con un boton para relanzar el analisis sin reiniciar.

## Correcciones

- **Los tamanos ya se muestran siempre** (GB por categoria y total). Habia
  dos fallos encadenados:
  1. Al arrancar con cache reciente, los numeros cacheados solo llegaban
     al total: las filas de categoria se quedaban con su texto inicial
     ("limpio"). Ahora la cache refresca tambien cada fila.
  2. Si el temporizador del analisis de arranque coincidia con la carga de
     reglas winapp2 (que deja el controller ocupado), el analisis se
     **descartaba en silencio** y todo quedaba a 0 hasta pulsar Analizar.
     Ahora se encola y se ejecuta al liberarse.
- **winapp ya mide de verdad**: se mostraba "limpio" aunque sus reglas
  tuvieran GB. La causa era el punto anterior mas la cache envenenada:
  - La cache ya no guarda una categoria basada en reglas cuando sus reglas
    aun no estan cargadas (no es 0, es desconocido).
  - El esquema de cache sube a 2 para descartar los archivos ya danados.

Verificado en CI: lint (Ruff + Pyright + Bandit) y tests en **Python 3.10,
3.11, 3.12, 3.13 y 3.14** + build.

## Descargas

| Archivo | Para que |
|---|---|
| `LimpiaProPortable.zip` | **Recomendado**: portable OneDir, arranque instantaneo |
| `LimpiaPro.zip` | El .exe de un solo archivo, dentro de un zip |
| `LimpiaPro.exe` | Un solo archivo (descarga directa, mas fragil) |
| `LimpiaProDebug.exe` | Variante con consola para diagnostico |
| `SHA256SUMS.txt` | Hashes para verificar la descarga |
