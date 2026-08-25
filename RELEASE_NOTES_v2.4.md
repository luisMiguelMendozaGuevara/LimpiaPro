# LimpiaPro v2.4

## Interfaz (PySide6)

- **Sistema de iconos SVG propio**: 20+ iconos estilo Fluent renderizados en
  runtime, recoloreables por tema (claro/oscuro) y acento del sistema. Sin
  emojis en la navegacion ni en los botones.
- **Logo** con el icono de la aplicacion (34 px) junto al nombre.
- **Tipografia mejorada**: Segoe UI Variable con escala consistente; titulos
  de pagina 22 px, descripciones de categorias reescritas con explicaciones
  y recomendaciones claras (ej.: la cache de navegadores no toca
  contrasenas, marcadores ni historial).
- **Alertas renovadas**: nuevos dialogos estructurados con icono lateral
  tematico, cabecera en negrita, lista de categorias con su tamano, y las
  recomendaciones en tarjetas destacadas (ambar/rojo). Botones explicitos
  ("Si, limpiar" / "Cancelar") con Cancelar por defecto.
- **Boton inteligente Seleccionar todo / Deseleccionar todo**: un solo
  control que muestra la accion a realizar.
- Corregidos: cajas grises en tema claro, iconos que no reescalaban,
  textos de botones truncados (toolbar con FlowLayout que salta de linea).

## Seguridad

- **winapp2 mas seguro**: las secciones con contrasenas, autofill,
  historial de navegacion, sesiones o marcadores se excluyen por defecto
  (la categoria winapp2 era un borrado silencioso de datos personales).
- La confirmacion de limpieza muestra una nota especifica cuando se usa
  winapp2.
- Auditoria: bandit sin hallazgos HIGH/MEDIUM (10.282 LOC), 22 comprobaciones
  de seguridad pasando (SafetyGuard, sin shell=True, traversal, datos
  sensibles).

## Rendimiento

- Hoja de estilos cacheada por (acento, tema); analisis inicial diferido
  hasta el primer pintado; import del controller diferido. Ventana lista en
  ~0,26 s.
- Auditoria real de winapp2 en maquina de pruebas: 3,46 GB coincidentes,
  todos caches/logs/temp regenerables.
