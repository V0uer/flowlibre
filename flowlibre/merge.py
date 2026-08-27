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
   (normalizados individualmente, no el bloque unido) tienen
   `difflib.SequenceMatcher(None, tok_a, tok_b).ratio() >= 0.8` — con
   `k == 1` la unica posicion exige igualdad exacta, no 0.8, porque con una
   sola palabra de contexto una coincidencia difusa es casi siempre falso
   positivo ("casa" / "caza").
2. Al menos un token del bloque tiene contenido real (el filtro de bloques de
   pura puntuacion, sin cambios).

Como ya no hay ratios de distinta escala que comparar, "el traslape mas largo
que califica" vuelve a ser un criterio bien definido: se recorren los k de
mayor a menor y se devuelve el primero que califica.

Limitacion conocida (sin resolver): un traslape real mas largo puede seguir
perdiendo contra un match exacto de una sola palabra si alguna pareja del
bloque largo no llega a 0.8. Ejemplo verificado:
`merge_overlap('dijo que no puedo no', 'no podo no hacerlo bien')` — el
traslape real es "no puedo no" / "no podo no" (k=3), pero la pareja
"puedo"/"podo" da ratio 0.667 (no ~0.89 como se estimo al diseñar esto), por
debajo de 0.8, asi que k=3 no califica y gana k=1 (el "no" suelto), dejando
"puedo no podo no" duplicado a medias. No se subio el umbral para forzar este
caso porque bajarlo tambien acepta pares mas flojos en todos los demas
bloques de 2+ palabras. Ver `tests/test_merge.py` y el reporte de la Task 6
para los numeros completos.

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
_TOKEN_FUZZY_THRESHOLD = 0.8


def _norm(word: str) -> str:
    """Palabra sin puntuacion ni mayusculas, para comparar."""
    return "".join(c for c in word.lower() if unicodedata.category(c) not in _PUNCT)


def _califica(cola: list[str], cabeza: list[str], k: int) -> bool:
    """True si el bloque de k tokens normalizados cuenta como traslape."""
    # Un bloque donde todas las palabras normalizan a vacio es puro signos de
    # puntuacion (p.ej. "..." vs "-"): no hay contenido real que comparar, y
    # aceptarlo como traslape se comeria texto real por coincidencia
    # accidental de puntuacion.
    if not any(cola) or not any(cabeza):
        return False

    if k == 1:
        # Con una sola palabra de contexto, un umbral difuso seria casi
        # siempre falso positivo ("casa" / "caza"). Se exige exactitud.
        return cola == cabeza

    return all(
        difflib.SequenceMatcher(None, tok_a, tok_b).ratio() >= _TOKEN_FUZZY_THRESHOLD
        for tok_a, tok_b in zip(cola, cabeza)
    )


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
