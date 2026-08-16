"""Tests del contrato run_async/post_ui sin Tk real.

No se crea ninguna ventana; se drena manualmente _UI_QUEUE (o se
monkeypatchea post_ui) para aislar la logica de programacion de callbacks.
"""

import threading
import time

import pytest

from limpiapro.ui import widgets


@pytest.fixture(autouse=True)
def _cola_limpia():
    """Los threads de run_async pueden quedar residuos en la cola."""
    while True:
        try:
            widgets._UI_QUEUE.get_nowait()
        except Exception:
            break
    yield
    while True:
        try:
            widgets._UI_QUEUE.get_nowait()
        except Exception:
            break


def _drenar_cola():
    """Ejecuta en este hilo todos los callbacks pendientes de la UI."""
    while True:
        try:
            fn = widgets._UI_QUEUE.get_nowait()
        except Exception:
            return
        fn()


def test_post_ui_encola_y_pasa_por_cola():
    recibidos = []
    widgets.post_ui(lambda: recibidos.append("a"))
    widgets.post_ui(lambda: recibidos.append("b"))
    assert recibidos == []  # aun no se ha drenado
    _drenar_cola()
    assert recibidos == ["a", "b"]


def _esperar(cond, timeout=5.0):
    fin = time.time() + timeout
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_run_async_worker_ok_llama_done_con_tupla():
    resultados = []

    def worker(a, b):
        return a + b, a * b

    def done(suma, prod):
        resultados.append((suma, prod))

    widgets.run_async(None, worker, done, args=(3, 4))
    assert _esperar(lambda: widgets._UI_QUEUE.qsize() >= 1)
    _drenar_cola()
    assert _esperar(lambda: resultados)
    assert resultados == [(7, 12)]


def test_run_async_worker_error_hace_post_ui_de_on_error(monkeypatch):
    errores = []
    done_calls = []
    monkeypatch.setattr(widgets, "_errlog", lambda msg: None)

    def worker():
        raise ValueError("fallo interno")

    def done(*_a):
        done_calls.append(1)

    def on_error(e):
        errores.append(e)

    widgets.run_async(None, worker, done, on_error=on_error)
    assert _esperar(lambda: widgets._UI_QUEUE.qsize() >= 1)
    _drenar_cola()
    assert _esperar(lambda: errores)
    assert len(done_calls) == 0  # done NO se invoca si el worker fallo
    assert isinstance(errores[0], ValueError)


def test_run_async_on_error_none_no_produce_callback(monkeypatch):
    logs = []
    monkeypatch.setattr(widgets, "_errlog", lambda msg: logs.append(msg))

    def worker():
        raise ValueError("sin on_error")

    widgets.run_async(None, worker, lambda: None)
    # El worker reventara y, al no haber on_error, la cola queda sin
    # callbacks: solo debe llegar el registro del error en el log.
    assert _esperar(lambda: logs)
    assert "worker fallo" in logs[0]
    assert widgets._UI_QUEUE.empty()


def test_start_ui_poller_drena_en_intervalo():
    ejecutados = []
    pendientes = []

    class _FalsoWidget:
        def after(self, _ms, fn=None):
            pendientes.append(fn)

    widgets.post_ui(lambda: ejecutados.append("echo"))
    widgets.start_ui_poller(_FalsoWidget(), interval=0)
    # El poller programa su tick via after(); lo ejecutamos manualmente
    # (el fake no corre callbacks por si solo para evitar recursividad).
    assert _esperar(lambda: pendientes)
    pendientes.pop()()          # primer _poll
    assert "echo" in ejecutados
    assert pendientes            # el poller se reprogramo a si mismo