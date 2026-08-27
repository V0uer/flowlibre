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
    # Critical de la revision original: Whisper transcribio "completo" de un
    # lado y "completos" del otro para el mismo traslape de audio. La
    # igualdad exacta dejaba la frase del traslape repetida entera. Con la
    # calificacion por pareja de tokens (umbral 0.8 individual), el bloque de
    # 2 ("reporte"/"reporte"=1.0, "completo"/"completos"=0.941) califica; el
    # de 3 ("el"/"reporte"=0.222, ...) no, asi que gana el de 2 y se conserva
    # "de".
    prev = "vamos a revisar el reporte completo"
    nxt = "reporte completos de este mes"
    assert merge_overlap(prev, nxt) == "vamos a revisar el reporte completo de este mes"


def test_bloque_grande_no_califica_si_una_pareja_de_tokens_no_encaja():
    # Actualizado de esta ronda: con el criterio anterior (ratio de
    # caracteres sobre el bloque unido) este caso se explicaba como "el de 3
    # cruza el umbral pero el de 2 tiene mejor ratio, gana el de mejor
    # ratio". Ese razonamiento ya no aplica -- no hay ratios que comparar
    # entre tamaños. Con el criterio por pareja de tokens, el bloque de 3
    # ("tu"/"reporte"=0.0, "reporte"/"completos"=0.941, "completo"/"ya"=0.0)
    # simplemente no califica porque "tu"/"reporte" no llega a 0.8; el de 2
    # ("reporte"/"reporte"=1.0, "completo"/"completos"=0.941) si califica y
    # gana por ser el mas grande que califica.
    prev = "oye tu reporte completo"
    nxt = "reporte completos ya no"
    assert merge_overlap(prev, nxt) == "oye tu reporte completo ya no"


def test_prefiere_el_bloque_mas_grande_que_tambien_califica():
    # Actualizado de esta ronda: ya no hay "empate de ratio" que desempatar
    # (la calificacion es binaria, no un numero). Este caso ahora demuestra
    # que, cuando mas de un k califica (aqui k=1 y k=2, ambos con igualdad
    # exacta en "si"/"si"), gana el mas grande porque el bucle los recorre de
    # mayor a menor y retorna en el primero que califica -- sin necesidad de
    # revisar los mas chicos. Si ganara k=1 quedaria un "si" duplicado.
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


def test_no_borra_palabra_real_cuando_una_pareja_de_tokens_no_encaja():
    # Important de la re-revision: con el criterio de ratio de bloque unido,
    # "el reporte completo del mes" + "completo del proyecto anterior" daba
    # ratio 0.757 en k=3 y calificaba, borrando "proyecto" -- perdida
    # silenciosa de contenido real, sin dejar ni un duplicado visible que
    # alguien notara. Con el criterio por pareja de tokens, el bloque de 3
    # ("completo"/"completo"=1.0, "del"/"del"=1.0, "mes"/"proyecto"=0.182) no
    # califica porque la pareja "mes"/"proyecto" no llega a 0.8. Ningun otro k
    # califica tampoco, asi que se concatena entero y "proyecto" se conserva.
    prev = "el reporte completo del mes"
    nxt = "completo del proyecto anterior"
    assert merge_overlap(prev, nxt) == "el reporte completo del mes completo del proyecto anterior"


def test_traslape_real_mas_largo_con_pareja_debajo_del_umbral_no_se_resuelve():
    # Caso de la re-revision que el coordinador esperaba resuelto y que NO lo
    # esta con el criterio actual -- documentado aqui, no maquillado.
    # El traslape real son 3 palabras ("no puedo no" / "no podo no"), y el
    # coordinador esperaba que calificara por la pareja "puedo"/"podo". El
    # ratio real de esa pareja es 0.667 (no ~0.89 como se estimo), por debajo
    # del umbral de 0.8, asi que el bloque de 3 NO califica. Solo califica
    # k=1 (el ultimo "no" de prev contra el primer "no" de nxt, exacto), y
    # ese es un traslape mas chico y casual dentro del real: el bug original
    # (un match exacto corto le gana a un traslape real mas largo) sigue sin
    # resolverse para este caso concreto. Ver reporte para los numeros
    # completos y la discusion.
    prev = "dijo que no puedo no"
    nxt = "no podo no hacerlo bien"
    assert merge_overlap(prev, nxt) == "dijo que no puedo no podo no hacerlo bien"


def test_palabras_funcionales_cortas_no_se_confunden_con_traslape():
    # Critical de esta ronda: SequenceMatcher(None, 'de', 'del').ratio() da
    # exactamente 0.8, y esa es la forma general de una palabra corta contra
    # una variante de un caracter mas ('un'/'una', 'se'/'sea', etc. dan lo
    # mismo). Sin la regla de largo minimo, cada posicion del bloque
    # "tiene un" / "tienen una" calificaba por su cuenta y el bloque entero
    # se aceptaba como traslape sin serlo, comiendose "tienen una" -- perdida
    # silenciosa de contenido real, sin dejar ni un duplicado visible.
    prev = "el sistema tiene un"
    nxt = "tienen una falla grave"
    assert merge_overlap(prev, nxt) == "el sistema tiene un tienen una falla grave"


def test_cadena_de_palabras_funcionales_cortas_no_se_come_varias():
    # Variante encadenada: tres parejas de palabras funcionales cortas
    # seguidas ('de'/'del', 'un'/'una', 'se'/'sea'), cada una a exactamente
    # 0.8 de ratio. Antes de la regla de largo minimo esto calificaba un
    # bloque de k=3 completo y se comia "del una sea" entero.
    prev = "manda el reporte de un se"
    nxt = "del una sea el correcto"
    assert merge_overlap(prev, nxt) == "manda el reporte de un se del una sea el correcto"


def test_regla_de_largo_minimo_token_por_token():
    # Fija la regla misma, no un caso de merge_overlap completo: una pareja
    # de tokens cortos casi identicos ('de'/'del', longitudes 2 y 3) no
    # califica aunque su ratio de caracteres (0.8) cruce el umbral, porque
    # alguno de los dos mide menos que MIN_LEN_DIFUSO (5) y se exige
    # igualdad exacta. Una pareja larga con la misma diferencia de una letra
    # ('completo'/'completos', longitudes 8 y 9) si califica porque ambos
    # tokens llegan al largo minimo y el ratio (0.941) supera 0.8.
    from flowlibre.merge import _tokens_coinciden

    assert _tokens_coinciden("de", "del") is False
    assert _tokens_coinciden("completo", "completos") is True


def test_sustitucion_de_una_letra_no_se_confunde_con_traslape():
    # Critical de esta ronda: pesar/pasar son verbos distintos, ambos de 5
    # letras, y su ratio es exactamente 0.8 -- una sustitucion de un caracter
    # en una palabra de n=5 da 2(n-1)/2n = 0.8 exacto (no es casualidad de
    # este par, es la formula general). Con el umbral en 0.8 esto calificaba
    # y se comia "pasar" en silencio. Con 0.85 ya no califica.
    prev = "hoy vamos a pesar mucho"
    nxt = "pasar mucho tiempo aqui"
    assert merge_overlap(prev, nxt) == "hoy vamos a pesar mucho pasar mucho tiempo aqui"


def test_adicion_califica_pero_sustitucion_de_cinco_letras_no():
    # Congela la separacion aritmetica que justifica 0.85: una ADICION de
    # letra (tiene/tienen, ratio 0.909 -- variacion real de Whisper) sigue
    # calificando, mientras que una SUSTITUCION en una palabra de 5 letras
    # (ratio 0.8 exacto) ya no. Es el razonamiento del umbral, no solo un
    # caso mas de merge_overlap.
    from flowlibre.merge import _tokens_coinciden

    assert _tokens_coinciden("tiene", "tienen") is True
    assert _tokens_coinciden("pesar", "pasar") is False
