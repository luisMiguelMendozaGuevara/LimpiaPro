"""Translations table for Spanish."""

STRINGS = {

    # ------------------------------------------------------- common
    "ui.continue_q": "Continuar?",
    "btn.refresh": "Refrescar",
    "label.calculating": "calculando...",
    "label.scanning": "Escaneando...",
    "status.ready": "Listo",
    "msg.error_simple": "Error: {exc}",
    "msg.and_n_more": "... y {n} mas",
    "msg.no_categories": "No hay ninguna categoria seleccionada.",
    "col.name": "Nombre",
    "col.size": "Tamano",
    "col.status": "Estado",
    "col.command": "Comando",
    "col.user": "Usuario",
    "msg.recycle_emptied": "Papelera vaciada.",
    # ------------------------------------------------------- app
    "app.window_subtitle": "Limpiador de sistema",
    "nav.clean": "Limpieza",
    "nav.startup": "Inicio",
    "nav.dupes": "Duplicados",
    "nav.update": "Windows Update",
    "nav.uninstall": "Desinstalar",
    "nav.log": "Registro",
    "theme.dark": "Modo oscuro",
    "theme.light": "Modo claro",
    "log.started_admin": "{app} {ver} iniciado. (administrador)",
    "log.started_no_admin": "{app} {ver} iniciado. (sin admin)",
    "status.analyzing": "Analizando sistema...",
    "status.parsing_winapp": "Parseando reglas winapp2...",
    "status.analysis_done": "Analisis completado",
    "status.analyze_cancelled": "Analisis cancelado",
    "log.analyze_cancelled": "Analisis cancelado por el usuario.",
    "status.cleaning": "Limpiando...",
    "status.clean_done": "Limpieza completada - {size} liberados",
    "status.clean_cancelled": "Limpieza cancelada",
    "log.clean_cancelled": "Limpieza cancelada por el usuario.",
    "log.total_freed": "Total liberado: {size}",
    "dialog.winapp_title": "Seleccionar archivo de reglas winapp2",
    "dialog.winapp_filter": "winapp2.ini",
    "dialog.all_files": "Todos los archivos",
    "log.winapp_loaded": ("Reglas winapp2 cargadas: {n} aplicaciones "
                          "de {path}"),
    "status.winapp_loaded": "{n} aplicaciones con reglas cargadas",
    "log.winapp_none": ("No se detectaron reglas validas en el archivo "
                        "seleccionado."),
    "msg.winapp_none": ("No se detectaron reglas validas (o ningun "
                        "programa coincide con las condiciones Detect=)."),
    "status.winapp_error": "Error al cargar reglas winapp2",
    "msg.winapp_error": "Error al parsear las reglas winapp2:\n{exc}",
    "log.cleaning_cat": "Limpiando: {label} ...",
    "log.recycle_line": "  Papelera: {msg}",
    "log.cat_cleaned": ("  Eliminados {n} elementos, {e} errores "
                        "({size} liberados)."),
    "msg.clean_detail_base": ("Se eliminaran definitivamente los archivos "
                              "temporales, la cache y el historial.\n"
                              "RECOMENDACION: cierra los navegadores "
                              "(Chrome, Edge, Firefox, etc.) antes de "
                              "limpiar para evitar errores.\n"),
    "msg.clean_detail_recycle": "\nATENCION: se vaciara la PAPELERA DE RECICLAJE.\n",
    "msg.clean_detail_admin": ("\nAVISO: se requiere ejecutar como "
                               "administrador para limpiar archivos del "
                               "sistema.\n"),
    "msg.clean_confirm": ("Se limpiaran:\n{names}\n\nTamano estimado: "
                          "{size}\n\n{detail}\nContinuar?"),
    "msg.clean_confirm_heading": "Se limpiaran {n} categorias ({size})",
    "msg.clean_confirm_sub": ("Los archivos se eliminaran de forma "
                              "permanente. Marca Vista previa para ver "
                              "la lista antes de borrar."),
    "msg.clean_note_browsers": ("Recomendacion: cierra los navegadores "
                                "(Chrome, Edge, Firefox, etc.) y otras "
                                "aplicaciones antes de limpiar para "
                                "evitar errores."),
    "msg.clean_note_recycle": ("Atencion: la papelera de reciclaje se "
                               "vaciara de forma permanente."),
    "msg.clean_note_admin": ("Aviso: estas ejecutando sin permisos de "
                             "administrador; algunas categorias del "
                             "sistema se omitiran."),
    "msg.clean_note_winapp": ("winapp2: solo se borraran caches y logs "
                              "de las aplicaciones detectadas por la "
                              "base de datos comunitaria. Contrasenas, "
                              "historial y datos personales estan "
                              "excluidos por seguridad."),
    "msg.preview_empty": "No hay archivos que mostrar (todo parece limpio).",
    "title.preview": "Vista previa de limpieza",
    "preview.header": ("Archivos que se eliminaran (primeras 1000 "
                       "entradas)"),
    "preview.recycle_section": "== {label}: se vaciara la papelera ==",
    "preview.section": "== {label} ({shown} mostradas de {total} detectadas) ==",
    "msg.preview_error": "Error al recopilar la vista previa:\n{exc}",
    "log.error_kind": "    {n} -> {kind}",
    "errk.in_use": "archivo en uso",
    "errk.access_denied": "acceso denegado",
    "errk.not_found": "desaparecio durante el analisis",
    "errk.readonly": "archivo de solo lectura",
    "errk.dir_not_empty": "carpeta no vacia",
    "errk.safety": "bloqueado por la politica de seguridad",
    "errk.other": "otro",
    # ------------------------------------------------------- clean page
    "clean.title": "Limpieza del sistema",
    "clean.subtitle": ("Selecciona lo que quieres limpiar. Nada se "
                       "elimina sin tu confirmacion."),
    "btn.select_all": "Seleccionar todo",
    "btn.select_none": "Deseleccionar todo",
    "btn.preview": "Vista previa",
    "btn.cancel": "Cancelar",
    "btn.accept": "Aceptar",
    "btn.confirm_yes": "Si, continuar",
    "btn.clean_yes": "Si, limpiar",
    "btn.delete_yes": "Si, eliminar",
    "btn.uninstall_yes": "Si, desinstalar",
    "btn.winapp_rules": "Reglas winapp2",
    "btn.clean_selected": "Limpiar seleccionado",
    "clean.total_calculating": "Total seleccionado: calculando...",
    "clean.total": "Total seleccionado: {size}",
    "clean.needs_admin": "  [requiere administrador]",
    "clean.recycle_empty": "papelera vacia",
    "clean.is_clean": "limpio",
    "clean.n_files": "{n} archivos",
    "clean.safety_note": ("El borrado pasa por la politica de seguridad "
                          "central (SafetyGuard): las carpetas protegidas "
                          "(Documents, Desktop, Downloads, ...) y sus "
                          "subcarpetas nunca se eliminan."),
    # ------------------------------------------------------- qt UI
    "nav.home": "Inicio",
    "nav.results": "Resultados",
    "nav.settings": "Configuracion",
    "home.title": "Bienvenido a LimpiaPro",
    "home.subtitle": "Analiza tu sistema y libera espacio de forma segura.",
    "home.stat_junk": "Basura encontrada",
    "home.stat_categories": "Categorias",
    "home.stat_status": "Ultimo analisis",
    "home.stat_files": "{n} archivos detectados",
    "home.btn_analyze": "Analizar ahora",
    "home.btn_go_clean": "Ir a Limpieza",
    "home.btn_go_results": "Ver Resultados",
    "home.safety_note": ("Seguridad: la limpieza pasa por SafetyGuard. "
                         "Las carpetas personales (Documents, Desktop, "
                         "Downloads, Pictures, Music, Videos) y sus "
                         "subcarpetas nunca pueden eliminarse."),
    "results.title": "Resultados",
    "results.subtitle": "Detalle por categoria y resultado final de la limpieza.",
    "results.col_files": "Archivos",
    "results.summary": ("Limpieza completada: {freed} liberados, "
                        "{removed} elementos, {errors} errores."),
    "results.empty": "Sin resultados. Ejecuta un analisis primero.",
    "results.btn_go_clean": "Ir a Limpieza",
    "settings.title": "Configuracion",
    "settings.subtitle": "Preferencias de la aplicacion.",
    "settings.group_appearance": "Apariencia",
    "settings.theme": "Tema",
    "settings.theme_dark": "Oscuro",
    "settings.theme_light": "Claro",
    "settings.theme_system": "Sistema",
    "settings.language": "Idioma",
    "settings.lang_auto": "Automatico",
    "settings.lang_note": "El cambio de idioma se aplica al reiniciar.",
    "settings.group_behaviors": "Comportamiento",
    "settings.auto_analyze": "Analizar automaticamente al iniciar",
    "settings.confirm_clean": "Confirmar antes de limpiar",
    "settings.group_paths": "Ubicaciones",
    "settings.cache": "Cache",
    "settings.logs": "Logs",
    "settings.data_dir": "Datos de usuario",
    "settings.group_about": "Acerca de",
    "settings.saved": "Guardado.",
    # ------------------------------------------------------- categories
    "cat.temp.label": "Archivos temporales del sistema",
    "cat.temp.desc": ("Cache temporal de Windows y de los programas. Se "
                      "regenera sola: no afecta a tus documentos ni a "
                      "tus ajustes."),
    "cat.browser.label": "Cache de navegadores",
    "cat.browser.desc": ("Paginas guardadas en cache por Edge, Chrome, "
                         "Brave, Vivaldi, Opera y Firefox. Tus "
                         "contrasenas, marcadores e historial no se "
                         "tocan; las webs tardaran un poco mas la "
                         "primera vez que las visites tras limpiar."),
    "cat.recycle.label": "Papelera de reciclaje",
    "cat.recycle.desc": ("Vacia la papelera de forma permanente. "
                         "Revisa su contenido antes de continuar: los "
                         "archivos borrados no se podran recuperar."),
    "cat.apps.label": "Cache de aplicaciones y logs",
    "cat.apps.desc": ("Miniaturas del explorador, informes de errores, "
                      "cache de Windows Update y logs del sistema. "
                      "Windows los vuelve a crear cuando los necesita."),
    "cat.history.label": "Historial reciente",
    "cat.history.desc": ("Lista de documentos y busquedas recientes del "
                         "menu Inicio. No borra tus archivos, solo el "
                         "rastro de acceso."),
    "cat.winapp.label": "Aplicaciones (reglas winapp2)",
    "cat.winapp.desc_detected": ("Base de datos comunitaria winapp2.ini: "
                                 "{n} apps detectadas. Solo se borran "
                                 "caches y logs; las secciones con "
                                 "contrasenas, historial o datos "
                                 "personales estan excluidas por "
                                 "seguridad."),
    "cat.winapp.desc_none": ("Base de datos comunitaria winapp2.ini: sin "
                             "reglas cargadas"),
    # ------------------------------------------------------- widgets
    "msg.select_one": "Selecciona un elemento en la lista.",
    "msg.select_one_error": "Error: no se pudo localizar el elemento seleccionado.",
    "msg.select_many_error": "Error: no se pudo localizar la seleccion.",
    # ------------------------------------------------------- log page
    "logpage.title": "Registro de actividad",
    # ------------------------------------------------------- startup page
    "startup.title": "Administrador de inicio",
    "startup.subtitle": ("Apps que arrancan con Windows, tareas "
                         "programadas y procesos activos."),
    "tab.startup_apps": "Apps de inicio",
    "tab.tasks": "Tareas programadas",
    "tab.processes": "Procesos activos",
    "btn.disable_selected": "Desactivar seleccionada",
    "btn.reenable": "Reactivar desactivadas",
    "btn.disable": "Desactivar",
    "btn.enable": "Activar",
    "btn.end_process": "Terminar proceso",
    "btn.filter": "Filtrar",
    "startup.search_placeholder": "Buscar proceso...",
    "col.source": "Origen",
    "col.task": "Tarea",
    "col.schedule": "Planificacion",
    "col.next_run": "Proxima ejecucion",
    "col.process": "Proceso",
    "col.session": "Sesion",
    "col.memory": "Memoria",
    "col.cmd_file": "Comando / archivo",
    "msg.disable_startup": ("Desactivar el inicio de:\n\n  {name}\n\nSe "
                            "movera a la lista de desactivadas y podras "
                            "reactivarla despues."),
    "startup.runonce_warning": ("ADVERTENCIA: esta es una entrada de "
                                "ejecucion unica (RunOnce).\n\nSi la "
                                "desactivas, puede que nunca se ejecute."),
    "startup.runonce_confirm": "Estas seguro de que quieres desactivar '{name}'?",
    "log.startup_disabled": "Desactivada app de inicio: {name}",
    "status.startup_disabled": "App de inicio desactivada: {name}",
    "status.startup_disable_error": "Error al desactivar",
    "log.startup_disable_error": "Error desactivando {name}: {msg}",
    "msg.startup_disable_error": "No se pudo desactivar:\n{msg}",
    "title.reattach": "Reactivar aplicaciones de inicio",
    "startup.reattach_label": "Selecciona las aplicaciones a reactivar",
    "btn.reenable_selected": "Reactivar seleccionadas",
    "msg.no_disabled": "No hay aplicaciones de inicio desactivadas.",
    "log.startup_enabled": "Reactivada app de inicio: {name}",
    "log.startup_enable_error": "Error reactivando {name}: {msg}",
    "log.startup_loaded": "Apps de inicio: {n} encontradas.",
    "msg.task_enable_q": "ACTIVAR la tarea:\n\n  {name} ?",
    "msg.task_disable_q": "DESACTIVAR la tarea:\n\n  {name} ?",
    "status.task_enabled": "Tarea activada: {name}",
    "status.task_disabled": "Tarea desactivada: {name}",
    "log.task_enabled": "Tarea activada: {name}",
    "log.task_disabled": "Tarea desactivada: {name}",
    "status.task_error": "Error al modificar tarea",
    "log.task_error": "Error en tarea {name}: {msg}",
    "msg.task_error": "No se pudo modificar:\n{msg}\n\n(requiere administrador)",
    "startup.tasks_count": "{n} activas - {m} desactivadas",
    "log.tasks_loaded": "Tareas programadas: {n} cargadas.",
    "msg.select_process": "Selecciona un proceso en la lista.",
    "msg.kill_process": ("Terminar el proceso:\n\n  {name} (PID {pid}) "
                         "?\n\nSe cerrara de forma forzosa y se perderan "
                         "cambios sin guardar."),
    "msg.process_protected": ("{name} es un proceso critico del sistema "
                              "y no se puede terminar."),
    "log.process_killed": "Proceso terminado: {name}",
    "status.process_killed": "Proceso terminado: {name}",
    "status.process_error": "Error al terminar proceso",
    "log.process_error": "Error terminando {name}: {msg}",
    "msg.process_error": "No se pudo terminar:\n{msg}",
    "log.processes_shown": "Procesos: {n} mostrados.",
    "status.load_error": "Error al cargar {area}",
    "log.load_error": "Error en {area}: {exc}",
    "msg.load_error": "Error al cargar {area}:\n{exc}",
    "area.startup": "inicio",
    "area.tasks": "tareas",
    "area.processes": "procesos",
    "area.disabled": "desactivadas",
    # ------------------------------------------------------- duplicates page
    "dupes.title": "Archivos duplicados",
    "dupes.subtitle": ("Escanea una carpeta y encuentra archivos con el "
                       "mismo contenido (por hash blake2b)."),
    "btn.choose_folder": "Elegir carpeta",
    "dupes.path_placeholder": "Ruta a escanear",
    "dupes.min_size": "Tamano min:",
    "btn.find_dupes": "Buscar duplicados",
    "col.file_group": "Archivo / grupo",
    "col.copies": "Copias",
    "dupes.help": ("Marca los duplicados en el arbol (Ctrl+clic para "
                   "varios)\ny pulsa {btn}."),
    "btn.delete_selected": "Eliminar seleccionados",
    "dialog.pick_folder": "Selecciona la carpeta a escanear",
    "msg.dupes_no_folder": "Selecciona una carpeta primero.",
    "status.dupes_scanning": "Buscando duplicados en {folder} ...",
    "status.dupes_failed": "Busqueda fallo",
    "log.dupes_error": "Error en duplicados: {exc}",
    "status.dupes_none": "No se encontraron duplicados",
    "dupes.none_found": "No se encontraron archivos duplicados.",
    "dupes.summary": "{n} grupos duplicados - {size} recuperables",
    "dupes.results_of": "Resultados de: {folder}",
    "dupes.unreadable": "{n} archivo(s) no se pudieron leer y se omitieron.",
    "dupes.group_head": "{name} - {size}",
    "dupes.original": "(original, mantenido)",
    "status.dupes_done": "Busqueda finalizada: {n} grupos de duplicados",
    "log.dupes_done": ("Duplicados en {folder}: {n} grupos, {m} "
                       "archivos, {size} desperdiciados."),
    "msg.dupes_select": ("Selecciona archivos duplicados en el arbol (los "
                         "que estan debajo de cada grupo).\nEl original "
                         "se mantiene."),
    "msg.delete_files_header": "Se eliminaran definitivamente estos archivos:\n\n",
    "msg.space_to_free": "({size} a liberar)",
    "status.dupes_deleted": "Duplicados eliminados: {n}, errores: {e}",
    "log.dupes_deleted": "Eliminados {n} duplicados ({e} errores).",
    "log.dupes_changed": "{n} archivo(s) cambiaron desde el escaneo y se omitieron.",
    "msg.dupes_deleted": "Se eliminaron {n} archivos duplicados.",
    # ------------------------------------------------------- uninstall page
    "uninstall.title": "Desinstalador",
    "uninstall.subtitle": ("Desinstala programas y busca restos dejados "
                          "en disco y registro."),
    "btn.uninstall": "Desinstalar",
    "btn.find_leftovers": "Buscar restos",
    "btn.delete_leftovers": "Eliminar restos",
    "col.application": "Aplicacion",
    "col.publisher": "Publicador",
    "status.apps_load_error": "Error al cargar aplicaciones",
    "log.apps_load_error": "Error cargando aplicaciones: {exc}",
    "uninstall.n_apps": "{n} aplicaciones",
    "log.apps_loaded": "Programas instalados: {n}.",
    "msg.no_uninstall_cmd": ("Esta aplicacion no tiene un comando de "
                             "desinstalacion."),
    "msg.run_uninstaller": ("Ejecutar el desinstalador de:\n\n  {name}"
                            "\n\n{cmd}\n\nSigue las instrucciones del "
                            "programa."),
    "log.uninstaller_launched": "Desinstalador lanzado: {name}",
    "status.uninstaller_launched": "Desinstalador lanzado: {name}",
    "log.uninstaller_error": ("No se pudo lanzar el desinstalador de "
                              "{name}: {msg}"),
    "msg.uninstaller_error": "No se pudo lanzar el desinstalador:\n{msg}",
    "msg.leftover_error": "Error al buscar restos:\n{exc}",
    "uninstall.leftover_count": "{name}: {n} restos",
    "msg.no_leftovers": "No se encontraron restos para: {name}",
    "log.leftovers_found": "Restos de {name}: {n} encontrados.",
    "title.leftovers": "Restos encontrados",
    "uninstall.leftovers_header": "Restos encontrados para {name} ({n}):",
    "kind.folder": "carpeta",
    "kind.registry": "registro",
    "msg.search_first": "Primero busca restos con '{btn}'.",
    "msg.delete_generic_header": "Se eliminaran definitivamente:\n\n",
    "log.leftovers_deleted": "Restos eliminados: {ok} OK, {err} errores.",
    "status.leftovers_deleted": "Restos eliminados: {ok} OK, {err} errores.",
    # ------------------------------------------------------- update page
    "update.title": "Restos de Windows Update",
    "update.subtitle": ("Limpia componentes antiguos (WinSxS) y versiones "
                        "previas de actualizaciones. Requiere "
                        "administrador."),
    "btn.analyze": "Analizar",
    "btn.clean_updates": "Limpiar actualizaciones",
    "update.not_available": "no disponible",
    "log.winsxs_error": "Error midiendo WinSxS: {exc}",
    "update.winsxs_size": "Tienda WinSxS: {size}",
    "update.section": ">> {label}",
    "update.error": "Error: {exc}",
    "update.no_output": "(sin salida)",
    "update.finished": ">> Terminado.",
    "update.analyzing": "Analizando tienda de componentes...",
    "update.cleaning": "Limpiando componentes antiguos...",
    "msg.update_clean_confirm": ("Se eliminaran versiones anteriores de "
                                 "actualizaciones de Windows.\n\nEl "
                                 "proceso puede tardar varios minutos "
                                 "(DISM).\n\nContinuar?"),
}
