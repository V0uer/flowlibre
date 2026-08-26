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
    # umbral difuso ya no.
    #
    # OJO (reportado aparte al coordinador): con este mismo ejemplo, el
    # ratio en k=3 ("el reporte completo" vs "reporte completos de") tambien
    # cae por encima de 0.75 (~0.82), y como el algoritmo prueba k de mayor
    # a menor, se queda con el traslape de 3 palabras en vez del de 2 reales,
    # comiendose "de" -- una palabra que no era parte del traslape. El
    # assert de abajo documenta el comportamiento actual, no el ideal.
    prev = "vamos a revisar el reporte completo"
    nxt = "reporte completos de este mes"
    assert merge_overlap(prev, nxt) == "vamos a revisar el reporte completo este mes"


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
