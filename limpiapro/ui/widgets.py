"""Widgets y helpers compartidos de la interfaz."""

import threading
from tkinter import messagebox, ttk

from .. import APP_NAME
from ..utils import _errlog


def make_tree(parent, spec, style="Dup.Treeview"):
    """Treeview + scrollbar vertical con estilo comun.

    spec: lista de (columna, encabezado, ancho[, anclaje]); la primera
    entrada describe la columna de arbol (#0). Devuelve el treeview."""
    cols = tuple(s[0] for s in spec[1:])
    tree = ttk.Treeview(parent, columns=cols, show="tree", style=style)
    tree.heading("#0", text=spec[0][1])
    tree.column("#0", width=spec[0][2])
    for col, head, width, *rest in spec[1:]:
        anchor = rest[0] if rest else "w"
        tree.heading(col, text=head)
        tree.column(col, width=width, anchor=anchor)
    sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
    sb.pack(side="right", fill="y", pady=4)
    return tree


def selected_one(tree, data):
    """Entrada de `data` para la seleccion de `tree`, o None.

    Robusto frente a refrescos que desincronizan los iid del arbol."""
    sel = tree.selection()
    if not sel:
        messagebox.showinfo(APP_NAME, "Selecciona un elemento en la lista.")
        return None
    try:
        return data[int(sel[0])]
    except (ValueError, IndexError):
        messagebox.showerror(
            APP_NAME, "Error: no se pudo localizar el elemento seleccionado.")
        return None


def selected_many(tree, data):
    """Como selected_one pero con la seleccion multiple completa."""
    sel = tree.selection()
    if not sel:
        messagebox.showinfo(APP_NAME, "Selecciona un elemento en la lista.")
        return None
    try:
        return [data[int(iid)] for iid in sel]
    except (ValueError, IndexError):
        messagebox.showerror(
            APP_NAME, "Error: no se pudo localizar la seleccion.")
        return None


def run_async(widget, worker, done, args=()):
    """Ejecuta worker(*args) en un hilo y llama done(*resultado) en la UI.

    El worker debe devolver una tupla con los argumentos de done. Si el
    worker revienta, queda registro en el log de errores."""
    def _thread():
        try:
            result = worker(*args)
        except Exception as e:
            _errlog(f"worker fallo ({getattr(worker, '__name__', worker)}): {e!r}")
            return
        widget.after(0, lambda: done(*result))
    threading.Thread(target=_thread, daemon=True).start()
