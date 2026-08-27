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

Seleccion de k: el de mejor ratio, no el primero que cruza el umbral
----------------------------------------------------------------------
El ratio es por caracteres sobre el bloque unido, y eso tiene una consecuencia
no obvia: un bloque mas largo que incluye el traslape real mas 1-2 palabras
ajenas todavia comparte casi toda esa subcadena, asi que su ratio se diluye
poco y con frecuencia *tambien* cruza 0.75 — aunque esas palabras ajenas no
sean parte del traslape. Ejemplo real:
`merge_overlap('vamos a revisar el reporte completo', 'reporte completos de este mes')`:
el traslape real es "reporte completo(s)" (k=2, ratio 0.97), pero el bloque de
3 palabras ("el reporte completo" / "reporte completos de") tambien cruza el
umbral (ratio ~0.82). Si el algoritmo se quedara con el primer k que cruza
(buscando de mayor a menor), elegiria el bloque de 3 y se comeria "de" — una
palabra real que no era parte del traslape.

Por eso no se corta en el primer k que cruza: se recorren todos los k
candidatos y se elige el de **mayor ratio** (k == 1 cuenta como ratio 1.0
cuando hay igualdad exacta). En caso de empate exacto se prefiere el k **mas
grande**: un traslape real de 2 palabras identicas empata entre k=1 y k=2, y
quedarse con k=1 dejaria una palabra duplicada en cada frontera de trozo, en
todos los dictados — eso es mucho mas frecuente que el caso raro (un
tartamudeo del que habla justo en la frontera) que el empate hacia k grande
sacrifica. Se prefiere fallar en lo raro.

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

_FUZZY_THRESHOLD = 0.75


def _norm(word: str) -> str:
    """Palabra sin puntuacion ni mayusculas, para comparar."""
    return "".join(c for c in word.lower() if unicodedata.category(c) not in _PUNCT)


def merge_overlap(prev: str, nxt: str, max_words: int = 15) -> str:
    """Pega `nxt` despues de `prev` sin repetir el traslape."""
    if not prev.strip():
        return nxt.strip()
    if not nxt.strip():
        return prev.strip()

    prev_words = prev.split()
    next_words = nxt.split()
    limite = min(max_words, len(prev_words), len(next_words))

    # Se recorren todos los k candidatos y se elige el de mejor ratio, no el
    # primero que cruza el umbral (ver docstring: un k mas grande puede cruzar
    # el umbral por inercia de caracteres sin ser el traslape real). Al
    # iterar de mayor a menor y actualizar solo con '>' estricto, un empate
    # exacto de ratio se queda con el k mas grande visto primero.
    mejor_k = None
    mejor_ratio = -1.0
    for k in range(limite, 0, -1):
        cola = [_norm(w) for w in prev_words[-k:]]
        cabeza = [_norm(w) for w in next_words[:k]]

        # Un bloque donde todas las palabras normalizan a vacio es puro
        # signos de puntuacion (p.ej. "..." vs "-"): no hay contenido real
        # que comparar, y aceptarlo como traslape se comeria texto real por
        # coincidencia accidental de puntuacion.
        if not any(cola) or not any(cabeza):
            continue

        if k == 1:
            # Con una sola palabra de contexto, un umbral difuso seria casi
            # siempre falso positivo ("casa" / "caza"). Se exige exactitud;
            # cuenta como ratio 1.0 para competir con bloques mas largos.
            ratio = 1.0 if cola == cabeza else 0.0
        else:
            cola_norm = " ".join(cola)
            cabeza_norm = " ".join(cabeza)
            ratio = difflib.SequenceMatcher(None, cola_norm, cabeza_norm).ratio()

        if ratio >= _FUZZY_THRESHOLD and ratio > mejor_ratio:
            mejor_ratio = ratio
            mejor_k = k

    if mejor_k is not None:
        return " ".join(prev_words + next_words[mejor_k:])

    return " ".join(prev_words + next_words)
