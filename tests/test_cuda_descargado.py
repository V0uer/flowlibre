"""Bajar 1.4 GB de CUDA y no cargarlas es peor que no bajarlas.

La app empaquetada NO trae las DLLs de NVIDIA (esa es la razon de que el
instalador pese 70.9 MB). Se bajan despues a %APPDATA%\FlowLibre\cuda\bin.
Si el buscador de DLLs no mira ahi, la descarga es un adorno de 1.4 GB y el
sintoma es "la app no acelera", sin una sola pista de por que.
"""

from __future__ import annotations

import sys

import pytest

from flowlibre import descargas, transcribe


@pytest.mark.skipif(sys.platform != "win32", reason="rutas de DLL de Windows")
def test_registra_el_cuda_descargado(tmp_path, monkeypatch):
    binario = tmp_path / "cuda" / "bin"
    binario.mkdir(parents=True)
    (binario / "cublas64_12.dll").write_bytes(b"x")
    monkeypatch.setattr(descargas.paths, "data_dir", lambda: tmp_path)

    registrados = []
    monkeypatch.setattr(transcribe.os, "add_dll_directory", registrados.append)
    monkeypatch.setenv("PATH", "")
    transcribe._add_nvidia_dll_dirs()

    assert str(binario) in registrados
    assert str(binario) in transcribe.os.environ["PATH"]


@pytest.mark.skipif(sys.platform != "win32", reason="rutas de DLL de Windows")
def test_sin_cuda_descargado_no_registra_nada_inventado(tmp_path, monkeypatch):
    monkeypatch.setattr(descargas.paths, "data_dir", lambda: tmp_path)
    registrados = []
    monkeypatch.setattr(transcribe.os, "add_dll_directory", registrados.append)
    transcribe._add_nvidia_dll_dirs()
    # En desarrollo si hay nvidia-* en el venv; lo que no puede aparecer
    # es una ruta bajo el directorio de datos, que aqui esta vacio.
    assert not any(str(tmp_path) in r for r in registrados)
