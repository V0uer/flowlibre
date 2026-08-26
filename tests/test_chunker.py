import numpy as np
import pytest

from flowlibre.audio import SAMPLE_RATE
from flowlibre.chunker import Chunker


def habla(segundos: float) -> np.ndarray:
    """Audio fuerte (por encima del umbral de silencio)."""
    n = int(segundos * SAMPLE_RATE)
    return (np.random.default_rng(0).standard_normal(n) * 0.2).astype("float32")


def silencio(segundos: float) -> np.ndarray:
    n = int(segundos * SAMPLE_RATE)
    return np.zeros(n, dtype="float32")


def alimentar(ch: Chunker, audio: np.ndarray, bloque_s: float = 0.1):
    """Mete audio en bloques como lo haria el microfono. Devuelve los trozos emitidos."""
    salida = []
    paso = int(bloque_s * SAMPLE_RATE)
    for i in range(0, len(audio), paso):
        trozo = ch.feed(audio[i:i + paso])
        if trozo is not None:
            salida.append(trozo)
    return salida


def test_no_corta_antes_del_minimo():
    ch = Chunker()
    # 5s de habla y luego una pausa larga: aun no llega al minimo de 8s
    trozos = alimentar(ch, np.concatenate([habla(5), silencio(1.0)]))
    assert trozos == []


def test_corta_en_silencio_despues_del_minimo():
    ch = Chunker()
    trozos = alimentar(ch, np.concatenate([habla(9), silencio(0.6), habla(2)]))
    assert len(trozos) == 1
    # El trozo debe cubrir al menos los 9s de habla
    assert len(trozos[0]) >= 9 * SAMPLE_RATE


def test_no_corta_en_pausas_cortas():
    ch = Chunker()
    # Pausa de 150ms: por debajo del umbral de 400ms, es una pausa de respiracion
    trozos = alimentar(ch, np.concatenate([habla(9), silencio(0.15), habla(3)]))
    assert trozos == []


def test_corta_forzado_al_maximo_sin_silencio():
    ch = Chunker()
    # 30s continuos sin una sola pausa: debe cortar solo a los 25s
    trozos = alimentar(ch, habla(30))
    assert len(trozos) == 1
    assert len(trozos[0]) == pytest.approx(25 * SAMPLE_RATE, rel=0.05)


def test_los_trozos_se_traslapan():
    ch = Chunker(overlap_s=0.5)
    alimentar(ch, np.concatenate([habla(9), silencio(0.6)]))
    resto = ch.flush()
    # Tras cerrar un trozo, el siguiente arranca con 0.5s del anterior
    assert len(resto) >= 0.5 * SAMPLE_RATE


def test_flush_devuelve_lo_pendiente():
    ch = Chunker()
    alimentar(ch, habla(4))
    resto = ch.flush()
    assert len(resto) == pytest.approx(4 * SAMPLE_RATE, rel=0.05)


def test_flush_en_vacio_no_truena():
    assert len(Chunker().flush()) == 0
