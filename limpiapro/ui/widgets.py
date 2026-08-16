"""Widgets y helpers compartidos de la interfaz."""

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import APP_NAME
from ..utils import _errlog


# Cola thread-safe para ejecutar callbacks en el hilo de la UI. tkinter no
# garantiza widget.after() desde hilos; un unico poller la drena.
_UI_QUEUE = queue.Queue()


def post_ui(fn):
    """Programa `fn` para ejecutarse en el hilo de la UI (thread-safe)."""
    _UI_QUEUE.put(fn)


def start_ui_poller(widget, interval=50):
    """Arranca el poller unico de post_ui sobre `widget`."""
    def _poll():
        try:
            while True:
                fn = _UI_QUEUE.get_nowait()
                try:
                    fn()
                except Exception as e:
                    _errlog(f"callback de UI fallo: {e!r}")
        except queue.Empty:
            pass
        try:
            widget.after(interval, _poll)
        except Exception:
            pass
    widget.after(interval, _poll)


def run_async(widget, worker, done, args=(), on_error=None):
    """Ejecuta worker(*args) en un hilo y llama done(*resultado) en la UI.

    Contrato: worker devuelve la tupla de argumentos de done. Si el worker
    revienta, se registra en el log de errores y se invoca on_error()
    (en la UI) si se facilito, para que el llamador pueda deshacer el
    estado busy y marcar el error."""
    def _thread():
        try:
            result = worker(*args)
        except Exception as e:
            _errlog(f"worker fallo ({getattr(worker, '__name__', worker)}): {e!r}")
            if on_error is not None:
                # Capturamos `e` como default argument: `except` borra la
                # variable de excepcion al salir del bloque, y el lambda
                # programado en la UI se ejecuta mas tarde.
                post_ui(lambda e=e: on_error(e))
            return
        post_ui(lambda: done(*result))
    threading.Thread(target=_thread, daemon=True).start()


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


def fill_tree(tree, specs, chunk=200):
    """Llena un Treeview en lotes (no congela la UI con miles de inserts).

    `specs` es una lista de tuplas (iid, parent, text, values, kw):
      - iid: identificador del item ('' deja que ttk lo asigne; para
        selected_one/selected_many lo uso como indice en la lista de datos).
      - parent: iid del item padre, o '' para raiz.
      - kw: dict opcional (tags, image, open, ...).
    Conserva el esquema de iid enteros que usan selected_one/selected_many."""
    tree.delete(*tree.get_children())
    total = len(specs)
    if not total:
        return
    idx = 0

    def _flush():
        nonlocal idx
        end = min(idx + chunk, total)
        for i in range(idx, end):
            entry = specs[i]
            iid, parent, text, values, *rest = entry
            kw = rest[0] if rest else {}
            tree.insert(parent, "end", iid=iid or None, text=text,
                        values=values, **kw)
        idx = end
        if idx < total:
            try:
                tree.after(1, _flush)
            except Exception:
                _flush()
    _flush()


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


def readonly_scrolled(parent):
    """Textbox monospace de solo lectura dentro de un frame transparente.
    Devuelve (frame, box); el box debe escribirse con state='normal'."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    box = ctk.CTkTextbox(frame, font=ctk.CTkFont(family="Consolas", size=11))
    box.pack(side="left", fill="both", expand=True)
    box.configure(state="disabled")
    return frame, box


def readonly_toplevel(master, title, geometry, header=None):
    """Ventana Toplevel con cabecera opcional y textbox de solo lectura.
    Devuelve (win, box)."""
    win = ctk.CTkToplevel(master)
    win.title(title)
    win.geometry(geometry)
    if header:
        ctk.CTkLabel(win, text=header, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=("gray30", "gray70")).pack(anchor="w", padx=14, pady=(10, 2))
    frame, box = readonly_scrolled(win)
    frame.pack(fill="both", expand=True, padx=14, pady=6)
    return win, box


def confirm_destructive(title, details, extra=""):
    """Dialogo de confirmacion destruccion. Cierra (cierra el parent).
    Devuelve True/False."""
    msg = f"{details}\n\n{extra}\nContinuar?" if extra else f"{details}\n\nContinuar?"
    return messagebox.askyesno(APP_NAME, msg, parent=None, icon="warning")