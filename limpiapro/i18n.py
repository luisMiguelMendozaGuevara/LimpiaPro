"""Lightweight internationalization (Spanish / English).

The UI language is chosen once at import time from the Windows display
language (GetUserDefaultUILanguage). Spanish Windows gets Spanish, anything
else gets English. The LIMPIAPRO_LANG environment variable overrides the
detection, which is handy for development and tests.

Design rules:
  - Every user-facing string lives here as a key; UI code calls t(key).
  - Values are plain ASCII (no accents), following the project convention.
  - Placeholders use str.format syntax: t("log.winapp_loaded", n=3, path=p).
  - Backend modules return stable English/ASCII status strings; the UI
    layer translates them for display (architecture rule).
"""

import ctypes
import locale as _locale
import os

from .utils import _errlog

# Internal fallback chain when a key is missing from the active language
# table: current language -> Spanish (the project's original language).
_STRINGS = {
    "es": {
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
        "nav.clean": "\U0001F9F9  Limpieza",
        "nav.startup": "\U0001F4C8  Inicio",
        "nav.dupes": "\U0001F50D  Duplicados",
        "nav.update": "\U0001F504  Windows Update",
        "nav.uninstall": "\U0001F5D1  Desinstalar",
        "nav.log": "\U0001F4DD  Registro",
        "theme.dark": "Modo oscuro",
        "theme.light": "Modo claro",
        "log.started_admin": "{app} {ver} iniciado. (administrador)",
        "log.started_no_admin": "{app} {ver} iniciado. (sin admin)",
        "status.analyzing": "Analizando sistema...",
        "status.parsing_winapp": "Parseando reglas winapp2...",
        "status.analysis_done": "Analisis completado",
        "status.cleaning": "Limpiando...",
        "status.clean_done": "Limpieza completada - {size} liberados",
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
                                  "temporales, la cache y el historial.\n"),
        "msg.clean_detail_recycle": "\nATENCION: se vaciara la PAPELERA DE RECICLAJE.\n",
        "msg.clean_detail_admin": ("\nAVISO: se requiere ejecutar como "
                                   "administrador para limpiar archivos del "
                                   "sistema.\n"),
        "msg.clean_confirm": ("Se limpiaran:\n{names}\n\nTamano estimado: "
                              "{size}\n\n{detail}\nContinuar?"),
        "msg.preview_empty": "No hay archivos que mostrar (todo parece limpio).",
        "title.preview": "Vista previa de limpieza",
        "preview.header": ("Archivos que se eliminaran (primeras 1000 "
                           "entradas)"),
        "preview.recycle_section": "== {label}: se vaciara la papelera ==",
        "preview.section": "== {label} ({shown} mostradas de {total} detectadas) ==",
        "msg.preview_error": "Error al recopilar la vista previa:\n{exc}",
        # ------------------------------------------------------- clean page
        "clean.title": "Limpieza del sistema",
        "clean.subtitle": ("Selecciona lo que quieres limpiar. Nada se "
                           "elimina sin tu confirmacion."),
        "btn.select_all": "Seleccionar todo",
        "btn.none": "Ninguno",
        "btn.preview": "Vista previa",
        "btn.winapp_rules": "Reglas winapp2...",
        "btn.clean_selected": "Limpiar seleccionado",
        "clean.total_calculating": "Total seleccionado: calculando...",
        "clean.total": "Total seleccionado: {size}",
        "clean.needs_admin": "  [requiere administrador]",
        "clean.recycle_empty": "papelera vacia",
        "clean.is_clean": "limpio",
        "clean.n_files": "{n} archivos",
        # ------------------------------------------------------- categories
        "cat.temp.label": "Archivos temporales del sistema",
        "cat.temp.desc": "TEMP de usuario y sistema, Prefetch",
        "cat.browser.label": "Cache de navegadores",
        "cat.browser.desc": "Edge, Chrome, Brave, Vivaldi, Opera, Opera GX y Firefox",
        "cat.recycle.label": "Papelera de reciclaje",
        "cat.recycle.desc": "Vacia la papelera del sistema",
        "cat.apps.label": "Cache de aplicaciones y logs",
        "cat.apps.desc": "Miniaturas, CrashDumps, Windows Update, logs CBS",
        "cat.history.label": "Historial reciente",
        "cat.history.desc": "Elementos recientes del menu Inicio",
        "cat.winapp.label": "Aplicaciones (reglas winapp2)",
        "cat.winapp.desc_detected": ("Base de datos comunitaria winapp2.ini: "
                                     "{n} apps detectadas"),
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
        "btn.reenable": "Reactivar desactivadas...",
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
        "btn.choose_folder": "Elegir carpeta...",
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
    },
    "en": {
        # ------------------------------------------------------- common
        "ui.continue_q": "Continue?",
        "btn.refresh": "Refresh",
        "label.calculating": "calculating...",
        "label.scanning": "Scanning...",
        "status.ready": "Ready",
        "msg.error_simple": "Error: {exc}",
        "msg.and_n_more": "... and {n} more",
        "msg.no_categories": "No category is selected.",
        "col.name": "Name",
        "col.size": "Size",
        "col.status": "Status",
        "col.command": "Command",
        "col.user": "User",
        "msg.recycle_emptied": "Recycle bin emptied.",
        # ------------------------------------------------------- app
        "app.window_subtitle": "System cleaner",
        "nav.clean": "\U0001F9F9  Cleanup",
        "nav.startup": "\U0001F4C8  Startup",
        "nav.dupes": "\U0001F50D  Duplicates",
        "nav.update": "\U0001F504  Windows Update",
        "nav.uninstall": "\U0001F5D1  Uninstall",
        "nav.log": "\U0001F4DD  Log",
        "theme.dark": "Dark mode",
        "theme.light": "Light mode",
        "log.started_admin": "{app} {ver} started. (administrator)",
        "log.started_no_admin": "{app} {ver} started. (no admin)",
        "status.analyzing": "Analyzing system...",
        "status.parsing_winapp": "Parsing winapp2 rules...",
        "status.analysis_done": "Analysis complete",
        "status.cleaning": "Cleaning...",
        "status.clean_done": "Cleanup finished - {size} freed",
        "log.total_freed": "Total freed: {size}",
        "dialog.winapp_title": "Select winapp2 rules file",
        "dialog.winapp_filter": "winapp2.ini",
        "dialog.all_files": "All files",
        "log.winapp_loaded": "winapp2 rules loaded: {n} applications from {path}",
        "status.winapp_loaded": "{n} applications with rules loaded",
        "log.winapp_none": "No valid rules were detected in the selected file.",
        "msg.winapp_none": ("No valid rules detected (or no program matches "
                            "the Detect= conditions)."),
        "status.winapp_error": "Error loading winapp2 rules",
        "msg.winapp_error": "Error parsing the winapp2 rules:\n{exc}",
        "log.cleaning_cat": "Cleaning: {label} ...",
        "log.recycle_line": "  Recycle bin: {msg}",
        "log.cat_cleaned": "  Removed {n} items, {e} errors ({size} freed).",
        "msg.clean_detail_base": ("Temporary files, caches and history will "
                                  "be permanently deleted.\n"),
        "msg.clean_detail_recycle": "\nWARNING: the RECYCLE BIN will be emptied.\n",
        "msg.clean_detail_admin": ("\nNOTE: administrator rights are required "
                                   "to clean system files.\n"),
        "msg.clean_confirm": ("The following will be cleaned:\n{names}\n\n"
                              "Estimated size: {size}\n\n{detail}\nContinue?"),
        "msg.preview_empty": "No files to show (everything looks clean).",
        "title.preview": "Cleanup preview",
        "preview.header": "Files that will be deleted (first 1000 entries)",
        "preview.recycle_section": "== {label}: recycle bin will be emptied ==",
        "preview.section": "== {label} ({shown} shown of {total} detected) ==",
        "msg.preview_error": "Error collecting the preview:\n{exc}",
        # ------------------------------------------------------- clean page
        "clean.title": "System cleanup",
        "clean.subtitle": ("Choose what you want to clean. Nothing is deleted "
                           "without your confirmation."),
        "btn.select_all": "Select all",
        "btn.none": "None",
        "btn.preview": "Preview",
        "btn.winapp_rules": "winapp2 rules...",
        "btn.clean_selected": "Clean selected",
        "clean.total_calculating": "Selected total: calculating...",
        "clean.total": "Selected total: {size}",
        "clean.needs_admin": "  [administrator required]",
        "clean.recycle_empty": "recycle bin empty",
        "clean.is_clean": "clean",
        "clean.n_files": "{n} files",
        # ------------------------------------------------------- categories
        "cat.temp.label": "System temporary files",
        "cat.temp.desc": "User and system TEMP, Prefetch",
        "cat.browser.label": "Browser caches",
        "cat.browser.desc": "Edge, Chrome, Brave, Vivaldi, Opera, Opera GX and Firefox",
        "cat.recycle.label": "Recycle bin",
        "cat.recycle.desc": "Empties the system recycle bin",
        "cat.apps.label": "App caches and logs",
        "cat.apps.desc": "Thumbnails, crash dumps, Windows Update, CBS logs",
        "cat.history.label": "Recent history",
        "cat.history.desc": "Start menu recent items",
        "cat.winapp.label": "Applications (winapp2 rules)",
        "cat.winapp.desc_detected": ("Community winapp2.ini database: {n} "
                                     "apps detected"),
        "cat.winapp.desc_none": "Community winapp2.ini database: no rules loaded",
        # ------------------------------------------------------- widgets
        "msg.select_one": "Select an item in the list.",
        "msg.select_one_error": "Error: could not locate the selected item.",
        "msg.select_many_error": "Error: could not locate the selection.",
        # ------------------------------------------------------- log page
        "logpage.title": "Activity log",
        # ------------------------------------------------------- startup page
        "startup.title": "Startup manager",
        "startup.subtitle": ("Apps that start with Windows, scheduled tasks "
                             "and running processes."),
        "tab.startup_apps": "Startup apps",
        "tab.tasks": "Scheduled tasks",
        "tab.processes": "Running processes",
        "btn.disable_selected": "Disable selected",
        "btn.reenable": "Re-enable disabled...",
        "btn.disable": "Disable",
        "btn.enable": "Enable",
        "btn.end_process": "End process",
        "btn.filter": "Filter",
        "startup.search_placeholder": "Search process...",
        "col.source": "Source",
        "col.task": "Task",
        "col.schedule": "Schedule",
        "col.next_run": "Next run",
        "col.process": "Process",
        "col.session": "Session",
        "col.memory": "Memory",
        "col.cmd_file": "Command / file",
        "msg.disable_startup": ("Disable startup of:\n\n  {name}\n\nIt will "
                                "be moved to the disabled list and can be "
                                "re-enabled later."),
        "log.startup_disabled": "Startup app disabled: {name}",
        "status.startup_disabled": "Startup app disabled: {name}",
        "status.startup_disable_error": "Error disabling",
        "log.startup_disable_error": "Error disabling {name}: {msg}",
        "msg.startup_disable_error": "Could not disable:\n{msg}",
        "title.reattach": "Re-enable startup apps",
        "startup.reattach_label": "Select the apps to re-enable",
        "btn.reenable_selected": "Re-enable selected",
        "msg.no_disabled": "There are no disabled startup apps.",
        "log.startup_enabled": "Startup app re-enabled: {name}",
        "log.startup_enable_error": "Error re-enabling {name}: {msg}",
        "log.startup_loaded": "Startup apps: {n} found.",
        "msg.task_enable_q": "ENABLE the task:\n\n  {name} ?",
        "msg.task_disable_q": "DISABLE the task:\n\n  {name} ?",
        "status.task_enabled": "Task enabled: {name}",
        "status.task_disabled": "Task disabled: {name}",
        "log.task_enabled": "Task enabled: {name}",
        "log.task_disabled": "Task disabled: {name}",
        "status.task_error": "Error modifying task",
        "log.task_error": "Task error {name}: {msg}",
        "msg.task_error": "Could not modify:\n{msg}\n\n(administrator required)",
        "startup.tasks_count": "{n} active - {m} disabled",
        "log.tasks_loaded": "Scheduled tasks: {n} loaded.",
        "msg.select_process": "Select a process in the list.",
        "msg.kill_process": ("End the process:\n\n  {name} (PID {pid}) ?\n\n"
                             "It will be closed forcefully and unsaved "
                             "changes will be lost."),
        "log.process_killed": "Process ended: {name}",
        "status.process_killed": "Process ended: {name}",
        "status.process_error": "Error ending process",
        "log.process_error": "Error ending {name}: {msg}",
        "msg.process_error": "Could not end:\n{msg}",
        "log.processes_shown": "Processes: {n} shown.",
        "status.load_error": "Error loading {area}",
        "log.load_error": "Error in {area}: {exc}",
        "msg.load_error": "Error loading {area}:\n{exc}",
        "area.startup": "startup",
        "area.tasks": "tasks",
        "area.processes": "processes",
        "area.disabled": "disabled list",
        # ------------------------------------------------------- duplicates page
        "dupes.title": "Duplicate files",
        "dupes.subtitle": ("Scan a folder and find files with identical "
                           "content (blake2b hash)."),
        "btn.choose_folder": "Choose folder...",
        "dupes.path_placeholder": "Folder to scan",
        "dupes.min_size": "Min size:",
        "btn.find_dupes": "Find duplicates",
        "col.file_group": "File / group",
        "col.copies": "Copies",
        "dupes.help": ("Check the duplicates in the tree (Ctrl+click for "
                       "several)\nthen press {btn}."),
        "btn.delete_selected": "Delete selected",
        "dialog.pick_folder": "Select the folder to scan",
        "msg.dupes_no_folder": "Select a folder first.",
        "status.dupes_scanning": "Searching for duplicates in {folder} ...",
        "status.dupes_failed": "Search failed",
        "log.dupes_error": "Duplicates error: {exc}",
        "status.dupes_none": "No duplicates found",
        "dupes.none_found": "No duplicate files were found.",
        "dupes.summary": "{n} duplicate groups - {size} recoverable",
        "dupes.results_of": "Results from: {folder}",
        "dupes.group_head": "{name} - {size}",
        "dupes.original": "(original, kept)",
        "status.dupes_done": "Search finished: {n} duplicate groups",
        "log.dupes_done": ("Duplicates in {folder}: {n} groups, {m} files, "
                           "{size} wasted."),
        "msg.dupes_select": ("Select duplicate files in the tree (those below "
                             "each group).\nThe original is kept."),
        "msg.delete_files_header": "These files will be permanently deleted:\n\n",
        "msg.space_to_free": "({size} to free)",
        "status.dupes_deleted": "Duplicates deleted: {n}, errors: {e}",
        "log.dupes_deleted": "Deleted {n} duplicates ({e} errors).",
        "msg.dupes_deleted": "{n} duplicate files were deleted.",
        # ------------------------------------------------------- uninstall page
        "uninstall.title": "Uninstaller",
        "uninstall.subtitle": ("Uninstall programs and search for leftovers "
                              "on disk and registry."),
        "btn.uninstall": "Uninstall",
        "btn.find_leftovers": "Find leftovers",
        "btn.delete_leftovers": "Delete leftovers",
        "col.application": "Application",
        "col.publisher": "Publisher",
        "status.apps_load_error": "Error loading applications",
        "log.apps_load_error": "Error loading applications: {exc}",
        "uninstall.n_apps": "{n} applications",
        "log.apps_loaded": "Installed programs: {n}.",
        "msg.no_uninstall_cmd": "This application has no uninstall command.",
        "msg.run_uninstaller": ("Run the uninstaller of:\n\n  {name}\n\n{cmd}"
                                "\n\nFollow the program's instructions."),
        "log.uninstaller_launched": "Uninstaller launched: {name}",
        "status.uninstaller_launched": "Uninstaller launched: {name}",
        "log.uninstaller_error": "Could not launch the uninstaller of {name}: {msg}",
        "msg.uninstaller_error": "Could not launch the uninstaller:\n{msg}",
        "msg.leftover_error": "Error searching for leftovers:\n{exc}",
        "uninstall.leftover_count": "{name}: {n} leftovers",
        "msg.no_leftovers": "No leftovers found for: {name}",
        "log.leftovers_found": "Leftovers of {name}: {n} found.",
        "title.leftovers": "Leftovers found",
        "uninstall.leftovers_header": "Leftovers found for {name} ({n}):",
        "kind.folder": "folder",
        "kind.registry": "registry",
        "msg.search_first": "First search for leftovers with '{btn}'.",
        "msg.delete_generic_header": "The following will be permanently deleted:\n\n",
        "log.leftovers_deleted": "Leftovers deleted: {ok} OK, {err} errors.",
        "status.leftovers_deleted": "Leftovers deleted: {ok} OK, {err} errors.",
        # ------------------------------------------------------- update page
        "update.title": "Windows Update leftovers",
        "update.subtitle": ("Cleans old components (WinSxS) and previous "
                            "update versions. Requires administrator."),
        "btn.analyze": "Analyze",
        "btn.clean_updates": "Clean updates",
        "update.not_available": "not available",
        "log.winsxs_error": "Error measuring WinSxS: {exc}",
        "update.winsxs_size": "WinSxS store: {size}",
        "update.section": ">> {label}",
        "update.error": "Error: {exc}",
        "update.no_output": "(no output)",
        "update.finished": ">> Finished.",
        "update.analyzing": "Analyzing component store...",
        "update.cleaning": "Cleaning old components...",
        "msg.update_clean_confirm": ("Previous versions of Windows updates "
                                     "will be deleted.\n\nThe process can "
                                     "take several minutes (DISM).\n\n"
                                     "Continue?"),
    },
}


def detect_language():
    """Return the UI language code: "es" (Spanish Windows) or "en" (anything
    else, English being the fallback lingua franca).

    Resolution order:
      1. LIMPIAPRO_LANG environment variable (development/testing override).
      2. GetUserDefaultUILanguage(): primary language id 10 == Spanish.
      3. locale.getdefaultlocale() as a last resort if the Win32 call fails.
    """
    override = (os.environ.get("LIMPIAPRO_LANG") or "").strip().lower()
    if override[:2] in _STRINGS:
        return override[:2]
    try:
        # Primary language id: the low 10 bits of the LANGID.
        if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 10:
            return "es"
        return "en"
    except Exception:
        try:
            loc = (_locale.getdefaultlocale()[0] or "").lower()
        except Exception:
            loc = ""
        return "es" if loc.startswith("es") else "en"


LANG = detect_language()


def t(key, **fmt):
    """Translate `key` into the active language, formatting placeholders.

    Missing keys fall back to Spanish, then to the key itself (and leave a
    trace in the error log so gaps are easy to spot). With no `fmt` the
    string is returned as-is, avoiding format errors on literal braces.
    """
    text = _STRINGS.get(LANG, {}).get(key)
    if text is None:
        text = _STRINGS["es"].get(key)
    if text is None:
        _errlog(f"i18n: missing translation key '{key}'")
        return key
    return text.format(**fmt) if fmt else text
