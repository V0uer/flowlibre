"""Detección de NVIDIA: decide qué modelo usa la app en una máquina ajena.

Corre en el primer arranque, antes de que exista CUDA, así que no puede
apoyarse en nada de CUDA. Y no puede colgar el arranque ni tumbarlo: un `False`
conservador es un mal resultado aceptable, un crash no.
"""

import subprocess

import flowlibre.gpu as gpu


class _Salida:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_detecta_con_nvidia_smi(monkeypatch):
    monkeypatch.setattr(gpu.subprocess, "run",
                        lambda *a, **k: _Salida("NVIDIA GeForce RTX 3080 Ti\n"))
    assert gpu.detectar_nvidia() is True


def test_sin_nvidia_smi_pregunta_al_sistema(monkeypatch):
    llamadas = []

    def falso(cmd, *a, **k):
        llamadas.append(cmd)
        if "nvidia-smi" in cmd[0]:
            raise FileNotFoundError()
        return _Salida("Intel(R) UHD Graphics\n")

    monkeypatch.setattr(gpu.subprocess, "run", falso)
    assert gpu.detectar_nvidia() is False
    assert len(llamadas) == 2, "debe intentar el respaldo, no rendirse al primer fallo"


def test_el_respaldo_tambien_encuentra_nvidia(monkeypatch):
    def falso(cmd, *a, **k):
        if "nvidia-smi" in cmd[0]:
            raise FileNotFoundError()
        return _Salida("NVIDIA GeForce GTX 1650\nIntel(R) UHD Graphics\n")

    monkeypatch.setattr(gpu.subprocess, "run", falso)
    assert gpu.detectar_nvidia() is True


def test_un_comando_colgado_no_cuelga_el_arranque(monkeypatch):
    def falso(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=3)

    monkeypatch.setattr(gpu.subprocess, "run", falso)
    assert gpu.detectar_nvidia() is False


def test_cualquier_error_raro_devuelve_falso(monkeypatch):
    monkeypatch.setattr(gpu.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("qué sé yo")))
    assert gpu.detectar_nvidia() is False


def test_el_perfil_con_nvidia_usa_el_modelo_grande(monkeypatch):
    monkeypatch.setattr(gpu, "detectar_nvidia", lambda: True)
    p = gpu.perfil_recomendado()
    assert "turbo" in p["whisper_model"]
    assert p["whisper_compute_type"] == "int8_float16"


def test_el_perfil_sin_nvidia_usa_el_chico_en_cpu(monkeypatch):
    monkeypatch.setattr(gpu, "detectar_nvidia", lambda: False)
    p = gpu.perfil_recomendado()
    assert p["whisper_model"] == "small"
    assert p["whisper_compute_type"] == "int8"
