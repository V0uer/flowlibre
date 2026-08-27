"""Une textos de trozos consecutivos, quitando el traslape duplicado.

Los trozos de audio se traslapan medio segundo para que ninguna palabra quede
partida. El precio es que esas palabras se transcriben dos veces. Aqui se
busca el sufijo mas largo de un trozo que coincida (difusamente) con el
prefijo del siguiente, y se pega solo una vez.

La comparacion normaliza mayusculas y puntuacion porque Whisper puntua distinto
segun el contexto: el mismo audio puede salir "el presupuesto," en un trozo y
"El presupuesto" en el otro.

Umbral difuso vs. exacto
-------------------------
Ademas de puntuacion y mayusculas, Whisper tambien varia singular/plural o
articulos justo en los bordes de corte ("reporte completo" / "reporte
completos"): son el mismo traslape de audio, transcrito con una palabra
distinta. Exigir igualdad exacta en todo el bloque de k palabras hace que una
sola diferencia asi invalide el traslape completo, y el resultado es la frase
del traslape repetida entera en el texto final — mucho peor que una palabra
duplicada.

Por eso, para bloques de 2 palabras o mas, la coincidencia se acepta con un
umbral difuso (difflib.SequenceMatcher, ratio() >= 0.75) sobre el texto
normalizado y unido del bloque, en vez de igualdad estricta. Con 2+ palabras de
contexto, dos bloques que solo comparten una raiz o unas pocas letras ya caen
muy por debajo de 0.75, asi que el umbral no fusiona textos que en realidad no
se traslapan.

Para bloques de **una sola palabra** (k == 1) no hay contexto que respalde una
decision difusa: "casa" y "caza" comparten 3 de 4 letras (ratio 0.75) y son
palabras distintas. Ahi se exige igualdad exacta.

Seleccion de k: coincidencia palabra por palabra, gana el bloque mas grande
que califica
------------------------------------------------------------------------------
Version anterior (abandonada): un ratio de caracteres de difflib sobre el
bloque de k palabras **unido en una sola cadena**, comparando el bloque contra
el umbral y quedandose con el de mayor ratio entre distintos tamaños de
ventana. Eso resulto mal planteado de raiz: un ratio de caracteres sobre
ventanas de tamaños distintos no es comparable entre si (una ventana de 4
palabras y una de 2 producen numeros que no significan lo mismo), y el camino
de k == 1 competia en la misma escala devolviendo 1.0 o 0.0 en binario contra
fracciones de ventanas largas. Esto abrio dos fallas nuevas: un traslape real
de 3 palabras perdia contra un match exacto casual de 1 palabra (`'dijo que no
puedo no'` + `'no podo no hacerlo bien'`), y un traslape real de 3 palabras con
ratio 0.757 se aceptaba pese a que una de las tres parejas no tenia nada que
ver (`'el reporte completo del mes'` + `'completo del proyecto anterior'`
borraba "proyecto").

Diseño actual: la calificacion de un bloque de k palabras es **binaria**, no
un ratio a comparar entre tamaños. Un k **califica** si:

1. Para cada una de las k posiciones, el token de `cola` y el de `cabeza`
   (normalizados individualmente, no el bloque unido) *coinciden* segun la
   regla de largo minimo de abajo — con `k == 1` la unica posicion siempre
   exige igualdad exacta, sin importar el largo, porque con una sola palabra
   de contexto una coincidencia difusa es casi siempre falso positivo
   ("casa" / "caza").
2. Al menos un token del bloque tiene contenido real (el filtro de bloques de
   pura puntuacion, sin cambios).

Como ya no hay ratios de distinta escala que comparar, "el traslape mas largo
que califica" vuelve a ser un criterio bien definido: se recorren los k de
mayor a menor y se devuelve el primero que califica.

Regla de largo minimo para la comparacion difusa (MIN_LEN_DIFUSO = 5)
------------------------------------------------------------------------
El umbral por token (0.8) tiene un problema que no aparece con palabras
largas pero es sistematico con palabras cortas: `SequenceMatcher(None, "de",
"del").ratio()` da **exactamente 0.8**, y esa no es una casualidad de ese
par — es la forma general de una palabra corta contra una variante de un
caracter mas que la contiene. El español tiene medio diccionario de palabras
funcionales asi: de/del, la/las, el/del, un/una, se/sea, le/les, lo/los,
mi/mis, tu/tus, me/mes, si/sin, va/vas, da/dan — todas dan 0.8 exacto. Como
el criterio de un bloque es "todas las parejas califican", bastaba con que
cada posicion de un bloque cayera en uno de estos pares para que el bloque
entero calificara **sin que hubiera traslape real**, comiendose contenido de
`nxt` sin dejar ni un duplicado visible que alguien notara (peor que el
problema que esto reemplazo: al menos un duplicado se ve; una palabra borrada
en silencio no).

La causa de fondo: un ratio difuso sobre un token de 2 o 3 caracteres no
significa nada. En una palabra tan corta, una letra de diferencia es una
palabra completamente distinta, no una variacion de transcripcion — al
reves de "completo"/"completos", donde una letra de diferencia sobre 8-9 es
ruido de Whisper. Por eso la comparacion difusa exige suficiente señal para
ser confiable: **una pareja de tokens califica con ratio >= 0.8 solo si
ambos tokens tienen `MIN_LEN_DIFUSO` (5) caracteres o mas; si cualquiera de
los dos es mas corto, se exige igualdad exacta.** "completo"/"completos"
(8 y 9) sigue calificando por ratio (0.941); "de"/"del" (2 y 3) y
"un"/"una" (2 y 3) ahora exigen exactitud y no califican.

Umbral 0.8 -> 0.85: separar sustitucion de adicion
------------------------------------------------------------------------
Con el umbral en 0.8 sobrevivia un tercer agujero, mas sutil que las palabras
cortas: dos palabras de **contenido**, ambas de 5+ letras, que difieren en
**una sola letra sustituida** (no añadida) tambien pueden calificar sin ser
la misma palabra. Ejemplo verificado:
`merge_overlap('hoy vamos a pesar mucho', 'pasar mucho tiempo aqui')` ->
se comia "pasar" porque `pesar`/`pasar` da ratio exactamente 0.8.

La separacion no es casualidad, es aritmetica. Para una palabra de n letras:
una **sustitucion** de un caracter dentro de la palabra da un ratio de
`2(n-1) / 2n`, que para n=5 es exactamente 0.8; una **adicion** (plural,
sufijo, acento agregado) da `2n / (2n+1)`, que para n=5 ya es 0.909 y solo
sube con n. Verificado: completo/completos=0.941, tiene/tienen=0.909,
reporte/reportes=0.933, presupuesto/presupuestos=0.957 (todas adiciones);
pesar/pasar=0.8, vivir/vivar=0.8 (sustituciones de 5 letras).

Esto importa porque la variacion real que introduce Whisper en los bordes de
corte es casi siempre una adicion o supresion (plural, acento, sufijo), no
una sustitucion — una sustitucion que ademas produce otra palabra española
valida es, casi por definicion, otra palabra. Por eso el umbral subio de 0.8
a 0.85 (`_TOKEN_FUZZY_THRESHOLD`): eso rechaza las sustituciones de 5 letras
sin rechazar ninguna de las adiciones de arriba.

Limitacion conocida, tercera categoria (sin resolver): subir el umbral no
cierra el problema del todo. Una sustitucion en una palabra de 8 letras da
`2*7/16 = 0.875`, que sigue por encima de 0.85 — asi que dos palabras
españolas reales de 8+ letras que difieran en una sola letra (mas raras que
el caso de 5, pero existen) todavia pueden calificar como "la misma palabra"
sin serlo, con la misma perdida silenciosa que el caso de "pesar"/"pasar".
Seguir subiendo el umbral no cierra esto sin costo: en algun punto empieza a
rechazar adiciones legitimas en palabras cortas-medianas. La via de solucion
real no es seguir moviendo este numero, sino comparar con los timestamps de
los segmentos de Whisper (ver la limitacion del tartamudeo, mas abajo) en vez
de inferir "misma palabra" solo del texto.

Limitacion conocida (sin resolver): un traslape real mas largo puede seguir
perdiendo contra un match exacto de una sola palabra si alguna pareja del
bloque largo no coincide. Ejemplo verificado:
`merge_overlap('dijo que no puedo no', 'no podo no hacerlo bien')` — el
traslape real es "no puedo no" / "no podo no" (k=3), pero "podo" mide 4
caracteres (< MIN_LEN_DIFUSO), asi que esa pareja exige igualdad exacta y
"puedo" != "podo" la hace fallar; k=3 no califica y gana k=1 (el "no"
suelto), dejando "puedo no podo no" duplicado a medias. No se bajo
MIN_LEN_DIFUSO ni se ajusto el umbral para forzar este caso porque eso
reabriria el agujero de las palabras funcionales cortas. Ver
`tests/test_merge.py` y el reporte de la Task 6 para los numeros completos.

Limitacion conocida: repeticion legitima en la frontera del corte
-------------------------------------------------------------------
Esta funcion compara solo texto, sin ver los timestamps de los segmentos de
Whisper. Eso significa que no puede distinguir una repeticion real del que
habla (un tartamudeo: "esto no no hay problema" cortado justo entre los dos
"no") de un traslape genuino de audio — en ambos casos el texto muestra la
misma palabra repetida en el borde. El resultado es que un tartamudeo real
justo en el punto de corte puede perder una repeticion. Arreglarlo bien
requeriria comparar con los timestamps del chunker en vez de solo el texto, lo
cual es un cambio de diseño fuera de alcance aqui. En la practica el impacto es
chico: la etapa de limpieza con Claude que corre despues ya reescribe
tartamudeos ("no no no" -> "No."), asi que solo se nota con
`format_mode: crudo`.

Nota sobre saltos de linea
----------------------------
Esta funcion asume texto de una sola linea: usa `split()`/`" ".join()`, que
aplanan cualquier `\n` a un espacio. Hoy eso no muerde porque el texto que
llega aqui viene de `transcribe.py`, que arma la transcripcion con
`" ".join(...)` sobre los segmentos y por lo tanto nunca trae saltos de linea
— el comando de voz "nueva linea" lo aplica `commands.apply_inline` despues,
sobre el texto ya unido. Si el pipeline cambia de orden en el futuro, esta
funcion dejaria de preservar saltos de linea reales.
"""

from __future__ import annotations

import difflib
import unicodedata

_PUNCT = {"Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps"}

# Umbral por token individual (no por bloque unido). Ver docstring: un ratio
# de caracteres sobre bloques de tamaños distintos no es comparable entre si,
# asi que la calificacion de un bloque es binaria (todas sus parejas de
# tokens pasan este umbral), no un numero a competir entre tamaños de k.
#
# 0.85, no 0.8: para una palabra de n letras, una SUSTITUCION de un caracter
# da ratio 2(n-1)/2n (0.8 exacto en n=5, p.ej. pesar/pasar, vivir/vivar),
# mientras que una ADICION (plural, sufijo -- la variacion real que Whisper
# introduce) da 2n/(2n+1), que ya es 0.909 en n=5 y solo sube. 0.85 cae entre
# ambas familias: rechaza las sustituciones de 5 letras y conserva todas las
# adiciones (completo/completos=0.941, tiene/tienen=0.909,
# reporte/reportes=0.933, presupuesto/presupuestos=0.957). No lo bajes a 0.8
# de nuevo sin releer el docstring: a 0.8 cualquier sustitucion de 5 letras
# que resulte en otra palabra valida del español cuenta como "la misma
# palabra" y borra contenido en silencio.
_TOKEN_FUZZY_THRESHOLD = 0.85

# Largo minimo (en caracteres normalizados) que deben tener AMBOS tokens de
# una pareja para que la comparacion difusa aplique. Por debajo de este largo
# el ratio de caracteres deja de significar "variacion de transcripcion" y
# empieza a significar "palabra corta cualquiera parecida a otra" (de/del,
# un/una, etc. dan 0.8 exacto sin ser el mismo traslape). Ver docstring.
_MIN_LEN_DIFUSO = 5


def _norm(word: str) -> str:
    """Palabra sin puntuacion ni mayusculas, para comparar."""
    return "".join(c for c in word.lower() if unicodedata.category(c) not in _PUNCT)


def _tokens_coinciden(tok_a: str, tok_b: str) -> bool:
    """True si dos tokens normalizados cuentan como la misma palabra."""
    if len(tok_a) < _MIN_LEN_DIFUSO or len(tok_b) < _MIN_LEN_DIFUSO:
        # Palabra corta: una letra de diferencia es una palabra distinta, no
        # ruido de transcripcion. Se exige igualdad exacta.
        return tok_a == tok_b
    return difflib.SequenceMatcher(None, tok_a, tok_b).ratio() >= _TOKEN_FUZZY_THRESHOLD


def _califica(cola: list[str], cabeza: list[str], k: int) -> bool:
    """True si el bloque de k tokens normalizados cuenta como traslape."""
    # Un bloque donde todas las palabras normalizan a vacio es puro signos de
    # puntuacion (p.ej. "..." vs "-"): no hay contenido real que comparar, y
    # aceptarlo como traslape se comeria texto real por coincidencia
    # accidental de puntuacion.
    if not any(cola) or not any(cabeza):
        return False

    if k == 1:
        # Con una sola palabra de contexto, una coincidencia difusa seria
        # casi siempre falso positivo ("casa" / "caza"). Se exige exactitud
        # sin importar el largo.
        return cola == cabeza

    return all(_tokens_coinciden(tok_a, tok_b) for tok_a, tok_b in zip(cola, cabeza))


def merge_overlap(prev: str, nxt: str, max_words: int = 15) -> str:
    """Pega `nxt` despues de `prev` sin repetir el traslape."""
    if not prev.strip():
        return nxt.strip()
    if not nxt.strip():
        return prev.strip()

    prev_words = prev.split()
    next_words = nxt.split()
    limite = min(max_words, len(prev_words), len(next_words))

    # De mayor a menor: la calificacion es binaria por ventana (ver
    # _califica), asi que el primer k que califica ya es "el traslape mas
    # largo que califica" — no hace falta seguir buscando ni comparar ratios
    # entre tamaños distintos.
    for k in range(limite, 0, -1):
        cola = [_norm(w) for w in prev_words[-k:]]
        cabeza = [_norm(w) for w in next_words[:k]]
        if _califica(cola, cabeza, k):
            return " ".join(prev_words + next_words[k:])

    return " ".join(prev_words + next_words)
