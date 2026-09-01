"""Genera todos los iconos de FlowLibre desde una sola definicion de la marca.

Uso:  .venv/Scripts/python.exe tools/make_icons.py

Produce:
  assets/icons/FlowLibre.ico          — Windows: 16, 32, 48, 64, 128, 256 px
  assets/icons/FlowLibre-{n}.png      — el mosaico suelto, para la pagina y el instalador
  assets/icons/tray-{estado}.png      — los cuatro estados de la bandeja, 64 px
  assets/icons/iconset/*.png          — insumos para el .icns de macOS (fase 3)
  assets/logo/marca-flowlibre.svg     — la marca como vector, para la pagina y el instalador

**Este archivo es la fuente de la verdad de la marca**, no un SVG dibujado aparte.
La geometria son cuatro numeros (el eje, la amplitud, el grosor y el perfil de
afinado) y de ellos salen por igual los PNG, el .ico y el SVG: asi no pueden
separarse. Los tres conceptos que se propusieron viven en `assets/logo/concepto-*.svg`
como registro de la decision; el elegido fue el 1, la onda fluida.

Por que se dibuja con PIL y no se rasteriza un SVG: rasterizar necesitaria cairo o
reportlab, dependencias de build fragiles en Windows y mas pesadas que este archivo.
Muestrear la curva a mano cuesta veinte lineas y da control exacto del grosor a cada
tamano, que es justo lo que un icono de 16 px necesita.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / "assets" / "icons"

SS = 8                      # supermuestreo: se dibuja 8x y se reduce con LANCZOS
LIENZO = 256                # el espacio de diseno del SVG

# --- la marca: onda fluida (concepto 1) -------------------------------------
# Una onda completa recorriendo una diagonal que sube. Se define por matematicas
# y no por una curva de Bezier a ojo: la primera version, trazada con dos Bezier,
# salia demasiado horizontal y a 16 px se leia como una tilde en vez de una cinta.
# Aqui el eje sube de verdad (de abajo-izquierda a arriba-derecha) y la onda es
# simetrica, que es lo que la hace leerse como voz y no como garabato.
EJE_INICIO = (54, 188)
EJE_FIN = (202, 68)
AMPLITUD = 34               # que tan alto sube y baja la onda respecto al eje
GROSOR = 33                 # grosor en el centro; las puntas se afinan (ver PERFIL)


def PERFIL(t: float) -> float:
    """Grosor relativo a lo largo del trazo: puntas afinadas, cuerpo lleno.

    El afinado es lo que la vuelve una *cinta* y no un tubo, pero se mantiene
    conservador (nunca baja de 0.72) porque una punta muy fina desaparece al
    reducir a 16 px, que es la restriccion que manda en todo este diseno.
    """
    return 0.72 + 0.28 * (1 - (2 * t - 1) ** 2)

TILE_DESDE = (0x5B, 0x9C, 0xFF)
TILE_HASTA = (0x2E, 0x5F, 0xE0)
RADIO = 56

ESTADOS = {                 # los colores que ya usa flowlibre/tray.py
    "listo": (70, 130, 240),
    "grabando": (230, 60, 60),
    "procesando": (240, 180, 40),
    "apagado": (120, 120, 120),
}


def puntos_marca(pasos: int = 220):
    """La onda en el espacio de diseno de 256, con su grosor punto por punto.

    Devuelve (x, y, grosor_relativo). El trazo es el eje diagonal mas un
    desplazamiento perpendicular sinusoidal: una onda completa, dos lomos.
    """
    import math

    (x0, y0), (x1, y1) = EJE_INICIO, EJE_FIN
    dx, dy = x1 - x0, y1 - y0
    largo = math.hypot(dx, dy)
    px, py = -dy / largo, dx / largo          # normal unitaria al eje
    for i in range(pasos + 1):
        t = i / pasos
        off = AMPLITUD * math.sin(2 * math.pi * t)
        yield (x0 + dx * t + px * off, y0 + dy * t + py * off, PERFIL(t))


def dibuja_marca(img: Image.Image, color, escala: float, grosor: float) -> None:
    """Traza la onda como una sucesion de discos.

    Un disco por punto, con el radio del perfil: asi el trazo puede engordar y
    afinarse a lo largo del recorrido, cosa que `line(width=...)` no permite, y
    los extremos quedan redondos sin trabajo extra.
    """
    d = ImageDraw.Draw(img)
    for x, y, w in puntos_marca():
        r = grosor * w / 2
        cx, cy = x * escala, y * escala
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def _mosaico(lado: int) -> Image.Image:
    """Cuadrado redondeado con el degradado diagonal del concepto."""
    grande = lado * SS
    rampa = Image.new("RGB", (grande, grande))
    px = rampa.load()
    for y in range(grande):
        for x in range(grande):
            # proyeccion sobre la diagonal, como el gradiente del SVG
            t = (x + (grande - y)) / (2 * grande)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(TILE_DESDE, TILE_HASTA))
    mascara = Image.new("L", (grande, grande), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        [0, 0, grande - 1, grande - 1], radius=int(RADIO * lado / LIENZO * SS), fill=255)
    tile = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    tile.paste(rampa, (0, 0), mascara)
    return tile


def icono_app(lado: int) -> Image.Image:
    """El icono completo: mosaico con degradado y la marca en blanco."""
    grande = lado * SS
    img = _mosaico(lado)
    escala = grande / LIENZO
    # A tamanos chicos el trazo se engorda un poco: un stroke fiel se adelgaza al
    # reducir y la S se rompe. Es el ajuste que se hace a mano en cualquier icono.
    engorde = 1.18 if lado <= 24 else 1.06 if lado <= 48 else 1.0
    dibuja_marca(img, (255, 255, 255, 255), escala, GROSOR * escala * engorde)
    return img.resize((lado, lado), Image.LANCZOS)


def icono_bandeja(lado: int, color) -> Image.Image:
    """Solo la marca, del color del estado, sobre transparente."""
    grande = lado * SS
    img = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    escala = grande / LIENZO
    # Sin mosaico detras, la marca puede ocupar todo el lienzo: se agranda 1.25x
    # alrededor del centro para que llene el espacio de la bandeja.
    zoom = 1.22
    capa = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    dibuja_marca(capa, tuple(color) + (255,), escala, GROSOR * escala * 1.1)
    capa = capa.resize((int(grande * zoom), int(grande * zoom)), Image.LANCZOS)
    off = (grande - capa.width) // 2
    img.alpha_composite(capa, (off, off))
    return img.resize((lado, lado), Image.LANCZOS)


TAMANOS_ICO = [16, 32, 48, 64, 128, 256]
TAMANOS_ICNS = [16, 32, 64, 128, 256, 512, 1024]

SVG_SALIDA = ROOT / "assets" / "logo" / "marca-flowlibre.svg"


def _contorno_marca():
    """El contorno cerrado de la cinta, para exportarla como SVG.

    El trazo tiene grosor variable, asi que no se puede escribir como un `path`
    con `stroke-width`: hay que recorrer un lado, regresar por el otro y cerrar.
    Se calcula de los MISMOS puntos que dibuja el icono, para que el SVG y el
    .ico no puedan separarse.
    """
    import math

    pts = list(puntos_marca(pasos=160))
    izq, der = [], []
    for i, (x, y, w) in enumerate(pts):
        ant = pts[max(i - 1, 0)]
        sig = pts[min(i + 1, len(pts) - 1)]
        tx, ty = sig[0] - ant[0], sig[1] - ant[1]
        largo = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / largo, tx / largo       # normal a la tangente
        r = GROSOR * w / 2
        izq.append((x + nx * r, y + ny * r))
        der.append((x - nx * r, y - ny * r))
    return izq + list(reversed(der))


def escribe_svg() -> None:
    d = " ".join(f"{'M' if i == 0 else 'L'}{x:.2f} {y:.2f}"
                 for i, (x, y) in enumerate(_contorno_marca())) + " Z"
    SVG_SALIDA.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" '
        'height="256" role="img" aria-label="FlowLibre">\n'
        '  <!-- Generado por tools/make_icons.py. No editar a mano: la geometria vive\n'
        '       en ese archivo y de ahi salen tambien el .ico y los iconos de bandeja. -->\n'
        '  <defs>\n'
        '    <linearGradient id="tile" x1="0" y1="256" x2="256" y2="0" '
        'gradientUnits="userSpaceOnUse">\n'
        f'      <stop offset="0" stop-color="#{TILE_DESDE[0]:02X}{TILE_DESDE[1]:02X}{TILE_DESDE[2]:02X}"/>\n'
        f'      <stop offset="1" stop-color="#{TILE_HASTA[0]:02X}{TILE_HASTA[1]:02X}{TILE_HASTA[2]:02X}"/>\n'
        '    </linearGradient>\n'
        '  </defs>\n'
        f'  <rect width="256" height="256" rx="{RADIO}" fill="url(#tile)"/>\n'
        f'  <path id="marca" fill="#FFFFFF" d="{d}"/>\n'
        '</svg>\n', encoding="utf-8")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "iconset").mkdir(exist_ok=True)

    imagenes = {n: icono_app(n) for n in TAMANOS_ICO}
    for n, img in imagenes.items():
        img.save(DESTINO / f"FlowLibre-{n}.png")
    # El .ico lleva los seis tamanos adentro: Windows elige el que necesita en cada
    # lugar (16 en la barra, 32 en el escritorio, 256 en vista de iconos grandes).
    imagenes[256].save(DESTINO / "FlowLibre.ico", format="ICO",
                       sizes=[(n, n) for n in TAMANOS_ICO])

    for estado, color in ESTADOS.items():
        icono_bandeja(64, color).save(DESTINO / f"tray-{estado}.png")

    for n in TAMANOS_ICNS:
        icono_app(n).save(DESTINO / "iconset" / f"icon_{n}x{n}.png")

    escribe_svg()

    total = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file())
    print(f"Listo: {len(list(DESTINO.rglob('*.png')))} PNG + FlowLibre.ico "
          f"({total / 1024:.0f} KB) en {DESTINO}")


if __name__ == "__main__":
    main()
