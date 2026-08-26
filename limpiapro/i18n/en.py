"""Translations table for English."""

STRINGS = {

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
    "nav.clean": "Cleanup",
    "nav.startup": "Startup",
    "nav.dupes": "Duplicates",
    "nav.update": "Windows Update",
    "nav.uninstall": "Uninstall",
    "nav.log": "Log",
    "theme.dark": "Dark mode",
    "theme.light": "Light mode",
    "log.started_admin": "{app} {ver} started. (administrator)",
    "log.started_no_admin": "{app} {ver} started. (no admin)",
    "status.analyzing": "Analyzing system...",
    "status.parsing_winapp": "Parsing winapp2 rules...",
    "status.analysis_done": "Analysis complete",
    "status.analyze_cancelled": "Analysis cancelled",
    "log.analyze_cancelled": "Analysis cancelled by the user.",
    "status.cleaning": "Cleaning...",
    "status.clean_done": "Cleanup finished - {size} freed",
    "status.clean_cancelled": "Cleanup cancelled",
    "log.clean_cancelled": "Cleanup cancelled by the user.",
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
                              "be permanently deleted.\n"
                              "RECOMMENDATION: close your browsers "
                              "(Chrome, Edge, Firefox, etc.) before "
                              "cleaning to avoid errors.\n"),
    "msg.clean_detail_recycle": "\nWARNING: the RECYCLE BIN will be emptied.\n",
    "msg.clean_detail_admin": ("\nNOTE: administrator rights are required "
                               "to clean system files.\n"),
    "msg.clean_confirm": ("The following will be cleaned:\n{names}\n\n"
                          "Estimated size: {size}\n\n{detail}\nContinue?"),
    "msg.clean_confirm_heading": "{n} categories will be cleaned ({size})",
    "msg.clean_confirm_sub": ("Files will be permanently deleted. Use "
                              "Preview to review the list before "
                              "deleting."),
    "msg.clean_note_browsers": ("Recommendation: close your browsers "
                                "(Chrome, Edge, Firefox, etc.) and other "
                                "apps before cleaning to avoid errors."),
    "msg.clean_note_recycle": ("Attention: the recycle bin will be "
                               "emptied permanently."),
    "msg.clean_note_admin": ("Notice: running without administrator "
                             "rights; some system categories will be "
                             "skipped."),
    "msg.clean_note_winapp": ("winapp2: only caches and logs of the "
                              "applications detected by the community "
                              "database will be removed. Passwords, "
                              "history and personal data are excluded "
                              "for safety."),
    "msg.preview_empty": "No files to show (everything looks clean).",
    "title.preview": "Cleanup preview",
    "preview.header": "Files that will be deleted (first 1000 entries)",
    "preview.recycle_section": "== {label}: recycle bin will be emptied ==",
    "preview.section": "== {label} ({shown} shown of {total} detected) ==",
    "msg.preview_error": "Error collecting the preview:\n{exc}",
    "log.error_kind": "    {n} -> {kind}",
    "errk.in_use": "file in use",
    "errk.access_denied": "access denied",
    "errk.not_found": "disappeared during the scan",
    "errk.readonly": "read-only file",
    "errk.dir_not_empty": "directory not empty",
    "errk.safety": "blocked by the delete safety policy",
    "errk.other": "other",
    # ------------------------------------------------------- clean page
    "clean.title": "System cleanup",
    "clean.subtitle": ("Choose what you want to clean. Nothing is deleted "
                       "without your confirmation."),
    "btn.select_all": "Select all",
    "btn.select_none": "Deselect all",
    "btn.preview": "Preview",
    "btn.cancel": "Cancel",
    "btn.accept": "OK",
    "btn.confirm_yes": "Yes, continue",
    "btn.clean_yes": "Yes, clean",
    "btn.delete_yes": "Yes, delete",
    "btn.uninstall_yes": "Yes, uninstall",
    "btn.winapp_rules": "winapp2 rules",
    "btn.clean_selected": "Clean selected",
    "clean.total_calculating": "Selected total: calculating...",
    "clean.total": "Selected total: {size}",
    "clean.needs_admin": "  [administrator required]",
    "clean.recycle_empty": "recycle bin empty",
    "clean.is_clean": "clean",
    "clean.n_files": "{n} files",
    "clean.safety_note": ("Deletion goes through the central safety "
                          "policy (SafetyGuard): protected folders "
                          "(Documents, Desktop, Downloads, ...) and "
                          "their subfolders are never deleted."),
    # ------------------------------------------------------- qt UI
    "nav.home": "Home",
    "nav.results": "Results",
    "nav.settings": "Settings",
    "home.title": "Welcome to LimpiaPro",
    "home.subtitle": "Analyze your system and free up space safely.",
    "home.stat_junk": "Junk found",
    "home.stat_categories": "Categories",
    "home.stat_status": "Last analysis",
    "home.stat_files": "{n} files detected",
    "home.btn_analyze": "Analyze now",
    "home.btn_go_clean": "Go to Cleaning",
    "home.btn_go_results": "View Results",
    "home.safety_note": ("Safety: cleaning goes through SafetyGuard. "
                         "Personal folders (Documents, Desktop, "
                         "Downloads, Pictures, Music, Videos) and their "
                         "subfolders can never be deleted."),
    "results.title": "Results",
    "results.subtitle": "Per-category detail and final clean outcome.",
    "results.col_files": "Files",
    "results.summary": ("Cleaning finished: {freed} freed, {removed} "
                        "items, {errors} errors."),
    "results.empty": "No results yet. Run an analysis first.",
    "results.btn_go_clean": "Go to Cleaning",
    "settings.title": "Settings",
    "settings.subtitle": "Application preferences.",
    "settings.group_appearance": "Appearance",
    "settings.theme": "Theme",
    "settings.theme_dark": "Dark",
    "settings.theme_light": "Light",
    "settings.theme_system": "System",
    "settings.language": "Language",
    "settings.lang_auto": "Automatic",
    "settings.lang_note": "The language change applies on restart.",
    "settings.group_behaviors": "Behavior",
    "settings.auto_analyze": "Analyze automatically on start",
    "settings.confirm_clean": "Confirm before cleaning",
    "settings.group_paths": "Locations",
    "settings.cache": "Cache",
    "settings.logs": "Logs",
    "settings.data_dir": "User data",
    "settings.group_about": "About",
    "settings.saved": "Saved.",
    # ------------------------------------------------------- categories
    "cat.temp.label": "System temporary files",
    "cat.temp.desc": ("Windows and app temp cache. Regenerated "
                      "automatically: your documents and settings are "
                      "never touched."),
    "cat.browser.label": "Browser caches",
    "cat.browser.desc": ("Pages cached by Edge, Chrome, Brave, Vivaldi, "
                         "Opera and Firefox. Your passwords, bookmarks "
                         "and history are not touched; sites load a bit "
                         "slower the first time you revisit them after "
                         "cleaning."),
    "cat.recycle.label": "Recycle bin",
    "cat.recycle.desc": ("Permanently empties the recycle bin. Check its "
                         "contents first: deleted files cannot be "
                         "recovered."),
    "cat.apps.label": "App caches and logs",
    "cat.apps.desc": ("Explorer thumbnails, crash reports, Windows "
                      "Update cache and system logs. Windows recreates "
                      "them whenever needed."),
    "cat.history.label": "Recent history",
    "cat.history.desc": ("Recent documents and searches shown in the "
                         "Start menu. Your files are not deleted, only "
                         "the access trail."),
    "cat.winapp.label": "Applications (winapp2 rules)",
    "cat.winapp.desc_detected": ("Community winapp2.ini database: {n} "
                                 "apps detected. Only caches and logs "
                                 "are removed; sections with passwords, "
                                 "history or personal data are excluded "
                                 "for safety."),
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
    "btn.reenable": "Re-enable disabled",
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
    "startup.runonce_warning": ("WARNING: this is a one-time (RunOnce) "
                                "entry.\n\nIf you disable it, it may "
                                "never run."),
    "startup.runonce_confirm": "Are you sure you want to disable '{name}'?",
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
    "msg.process_protected": ("{name} is a critical system process "
                              "and cannot be ended."),
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
    "btn.choose_folder": "Choose folder",
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
    "dupes.unreadable": "{n} file(s) could not be read and were skipped.",
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
    "log.dupes_changed": "{n} file(s) changed since the scan and were skipped.",
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
}
