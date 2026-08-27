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


def test_traslape_con_una_palabra_distinta_se_deduplica():
    # Critical de la revision: Whisper transcribio "completo" de un lado y
    # "completos" del otro para el mismo traslape de audio. La igualdad
    # exacta anterior dejaba la frase del traslape repetida entera; con el
    # umbral difuso mas la regla de "mejor ratio, no el primero que cruza"
    # se queda con el traslape real de 2 palabras y conserva "de".
    prev = "vamos a revisar el reporte completo"
    nxt = "reporte completos de este mes"
    assert merge_overlap(prev, nxt) == "vamos a revisar el reporte completo de este mes"


def test_gana_el_k_de_mejor_ratio_no_el_primero_que_cruza():
    # Regresion concreta de esta ronda: el bloque de 3 palabras
    # ("tu reporte completo" / "reporte completos ya", ratio ~0.82) tambien
    # cruza el umbral de 0.75, pero el bloque de 2 ("reporte completo" /
    # "reporte completos", ratio ~0.97) es el traslape real y tiene mejor
    # ratio. Debe ganar el de mejor ratio, no el k=3 por aparecer primero al
    # buscar de mayor a menor.
    prev = "oye tu reporte completo"
    nxt = "reporte completos ya no"
    assert merge_overlap(prev, nxt) == "oye tu reporte completo ya no"


def test_empate_de_ratio_prefiere_el_k_mas_grande():
    # Traslape real de 2 palabras identicas ("si si"): k=1 (ultima palabra de
    # prev vs primera de nxt, ambas "si") y k=2 (bloque completo) empatan en
    # ratio 1.0. Debe ganar el k mas grande (2), o se quedaria "si" duplicado.
    prev = "hola que tal si si"
    nxt = "si si vamos ya"
    assert merge_overlap(prev, nxt) == "hola que tal si si vamos ya"


def test_umbral_difuso_no_fusiona_textos_que_no_se_traslapan():
    # Comparten palabras sueltas ("archivo") pero no son el mismo traslape de
    # audio: el ratio debe quedar por debajo de 0.75 y concatenar entero.
    prev = "manda el archivo ahora"
    nxt = "dame otro archivo distinto"
    assert merge_overlap(prev, nxt) == "manda el archivo ahora dame otro archivo distinto"


def test_k_uno_sigue_siendo_estricto():
    # "casa" y "caza" comparten 3 de 4 letras (ratio 0.75) pero son palabras
    # distintas: con una sola palabra de contexto no se acepta lo difuso.
    prev = "esto es una casa"
    nxt = "caza mayor de venados"
    assert merge_overlap(prev, nxt) == "esto es una casa caza mayor de venados"


def test_no_confunde_puntuacion_suelta_con_traslape():
    # "..." y "—" normalizan ambos a "": no hay contenido real que comparar,
    # no debe tratarse como traslape ni comerse el "—".
    prev = "espera ..."
    nxt = "— bueno entonces"
    assert merge_overlap(prev, nxt) == "espera ... — bueno entonces"


def test_saltos_de_linea_se_aplanan():
    # Documental: split()/join() convierten cualquier \n en un espacio. Hoy
    # esto no muerde porque transcribe.py nunca manda texto con saltos de
    # linea a esta funcion (ver docstring de merge_overlap).
    assert merge_overlap("primera linea\n", "segunda linea") == "primera linea segunda linea"


def test_traslape_que_excede_max_words_no_se_deduplica_completo():
    # El traslape real son 4 palabras ("de agosto queda listo") pero
    # max_words=2 limita la ventana de busqueda: no alcanza a verlo y el
    # duplicado se queda completo. Documenta la limitacion, no la arregla.
    prev = "el reporte final de agosto queda listo"
    nxt = "de agosto queda listo para enviar"
    assert (
        merge_overlap(prev, nxt, max_words=2)
        == "el reporte final de agosto queda listo de agosto queda listo para enviar"
    )


def test_max_words_cero_concatena_sin_buscar():
    assert merge_overlap("hola que tal", "todo bien", max_words=0) == "hola que tal todo bien"
