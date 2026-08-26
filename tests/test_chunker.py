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
    # A diferencia de la version anterior de este test, agregamos habla
    # nueva DESPUES del corte: asi flush() tiene algo que devolver (la cola
    # de 0.5s de traslape mas la voz nueva). Si solo hubiera silencio tras
    # el corte, flush() debe venir vacio (ver test_flush_tras_corte_no_repite_audio_transcrito) —
    # ese es justo el bug que arregla la compuerta de voz (I2).
    alimentar(ch, np.concatenate([habla(9), silencio(0.6), habla(0.3)]))
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


def test_invariante_cobertura_y_traslape_exacto():
    """La propiedad que de verdad le importa al autor: ni una muestra perdida,
    ni una duplicada fuera del traslape declarado. Se verifica con
    comparacion exacta de arreglos (habla()/silencio() son deterministas),
    no con conteos aproximados."""
    ch = Chunker(overlap_s=0.5)
    original = np.concatenate(
        [habla(9), silencio(0.6), habla(9), silencio(0.6), habla(5)]
    )
    trozos = alimentar(ch, original)
    trozos.append(ch.flush())
    assert len(trozos) >= 2  # al menos dos cortes naturales + el remanente

    overlap = ch.overlap_samples
    reconstruido = trozos[0]
    for trozo in trozos[1:]:
        if overlap:
            # El siguiente trozo debe arrancar EXACTAMENTE con la cola del anterior.
            assert np.array_equal(trozo[:overlap], reconstruido[-overlap:])
        reconstruido = np.concatenate([reconstruido, trozo[overlap:]])

    assert reconstruido.shape[0] == original.shape[0]
    assert np.array_equal(reconstruido, original)


def test_silencio_prolongado_no_emite_trozos():
    ch = Chunker()
    trozos = alimentar(ch, silencio(60))
    assert trozos == []
    assert len(ch.flush()) == 0


def test_flush_tras_corte_no_repite_audio_transcrito():
    ch = Chunker(overlap_s=0.5)
    alimentar(ch, np.concatenate([habla(9), silencio(0.6)]))
    resto = ch.flush()
    # La cola de traslape ya salio dentro del trozo emitido; si no llego
    # voz nueva despues del corte, flush() no debe repetirla.
    assert len(resto) == 0


def test_nan_no_bloquea_corte_natural():
    ruido_nan = np.full(int(0.6 * SAMPLE_RATE), np.nan, dtype="float32")
    ch = Chunker()
    trozos = alimentar(ch, np.concatenate([habla(9), ruido_nan]))
    assert len(trozos) == 1
    assert np.isfinite(trozos[0]).all()


def test_overlap_excesivo_no_degenera():
    ch = Chunker(overlap_s=8.0)
    trozos = alimentar(ch, habla(30))
    # Antes del clamp esto daba 51 trozos (uno cada 0.4s). Con el clamp,
    # el comportamiento vuelve a ser el de un troceador sano.
    assert len(trozos) <= 3


def test_stats_cuenta_cortes_naturales_y_forzados():
    ch = Chunker()
    alimentar(ch, np.concatenate([habla(9), silencio(0.6), habla(2)]))
    alimentar(ch, habla(30))
    stats = ch.stats()
    assert stats["naturales"] == 1
    assert stats["forzados"] == 1


@pytest.mark.parametrize("bloque_s", [0.008, 0.026, 0.064])
def test_corte_natural_con_distintos_tamanos_de_bloque(bloque_s):
    ch = Chunker()
    trozos = alimentar(
        ch,
        np.concatenate([habla(9), silencio(0.6), habla(2)]),
        bloque_s=bloque_s,
    )
    assert len(trozos) == 1
    assert len(trozos[0]) >= 9 * SAMPLE_RATE
