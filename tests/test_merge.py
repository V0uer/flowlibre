from flowlibre.merge import merge_overlap


def test_une_sin_traslape():
    assert merge_overlap("hola que tal", "todo bien") == "hola que tal todo bien"


def test_elimina_el_traslape_repetido():
    prev = "necesito que me ayudes con el reporte"
    nxt = "con el reporte de agosto por favor"
    assert merge_overlap(prev, nxt) == "necesito que me ayudes con el reporte de agosto por favor"


def test_ignora_diferencias_de_puntuacion_y_mayusculas():
    prev = "vamos a revisar el Presupuesto,"
    nxt = "el presupuesto de este mes"
    assert merge_overlap(prev, nxt) == "vamos a revisar el Presupuesto, de este mes"


def test_prefiere_el_traslape_mas_largo():
    prev = "uno dos tres uno dos tres"
    nxt = "uno dos tres cuatro"
    assert merge_overlap(prev, nxt) == "uno dos tres uno dos tres cuatro"


def test_maneja_lados_vacios():
    assert merge_overlap("", "hola") == "hola"
    assert merge_overlap("hola", "") == "hola"
    assert merge_overlap("", "") == ""


def test_no_borra_repeticiones_legitimas_lejanas():
    # "de" aparece en ambos pero no es traslape: no debe comerse nada
    prev = "el reporte de agosto"
    nxt = "manda copia de eso"
    assert merge_overlap(prev, nxt) == "el reporte de agosto manda copia de eso"
