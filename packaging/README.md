# Empaquetado de FlowLibre (Windows)

Produce `FlowLibre-Setup-2.0.0.exe`, el archivo que se comparte.

## Herramientas (no son dependencias de la app)

```bash
.venv/Scripts/python.exe -m pip install pyinstaller
winget install --id JRSoftware.InnoSetup
```

Ninguna de las dos va en `requirements.txt`: solo hacen falta para construir.

## Construir

```bash
# 1. Los iconos (si cambiaron)
.venv/Scripts/python.exe tools/make_icons.py

# 2. El bundle sin CUDA
.venv/Scripts/python.exe -m PyInstaller packaging/flowlibre.spec --noconfirm \
    --distpath packaging/dist --workpath packaging/build

# 3. El instalador
"$LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe" packaging/flowlibre.iss
# -> packaging/salida/FlowLibre-Setup-2.0.0.exe
```

## Medido el 2026-08-31

| | |
|---|---:|
| Bundle sin comprimir | 261 MB |
| **Instalador** | **70.9 MB** |
| Objetivo del spec (criterio 3) | ≤ 200 MB |

Sin una sola DLL de CUDA adentro: son 1.94 GB que se descargan aparte y solo en
máquinas con NVIDIA (ver `flowlibre/gpu.py`).

## `flowlibre-debug.spec`, y por qué existe

Es el mismo bundle con `console=True`. **Se genera desde el spec principal con
sed**, así que no se edita a mano.

Sirve para lo único que no se puede ver de otra forma: un bundle con `console=False`
que falla, falla **en silencio**. Así se encontró que excluir PyAV producía una app
que abría, se veía perfecta y no transcribía nada. Cuando algo del empaquetado se
comporte raro, se construye esta variante y se lee su stderr:

```bash
sed -e 's/console=False,.*/console=True,/' -e 's/name="FlowLibre",/name="FlowLibreDebug",/g' \
    packaging/flowlibre.spec > packaging/flowlibre-debug.spec
```

## La versión no se escribe aquí

Vive en `flowlibre/__init__.py` y en ningún otro lado. El `.spec` (que es Python
y corre al construir) la vuelca a `packaging/VERSION`, y el `.iss` la lee de ahí
con `FileRead`. **No pongas el número a mano en el `.iss`**: hay un test que lo
prohíbe, porque cuando estaban separados el instalador decía 2.0.0 y el paquete
1.0.0 — una app recién instalada que se cree vieja y se ofrece actualizar a la
versión que ya tiene, en bucle, en cada arranque (C43).

## Publicar un release

```bash
# 1. Los artefactos pesados que NO caben en el instalador, con sus hashes
.venv/Scripts/python.exe tools/publicar_artefactos.py

# 2. Commitear descargas.py (el script le escribe los sha256 dentro)
# 3. Etiquetar: el workflow construye, prueba y publica solo
git tag v2.0.1 && git push origin v2.0.1
```

Si te saltas el paso 2, la app **se niega** a bajar los artefactos y lo dice en
el mensaje. Es a propósito: bajar 1.4 GB que no se pueden verificar produce un
.zip corrupto que se descomprime a medias, y entonces la app abre, se ve
perfecta y no transcribe (el fallo de C41).

## Lo que todavía no está

- **Sin firma de código.** Windows mostrará "Windows protegió tu PC" → Más
  información → Ejecutar de todos modos. Va documentado en la página de descarga.
- **Sin repo remoto.** El auto-update y la página leen GitHub Releases, que
  todavía no existen: falta crear el repo y subirlo (tarea 9, paso 2).
- **Sin los assets publicados.** `flowlibre/descargas.py` tiene los `sha256` en
  blanco hasta que se corra `tools/publicar_artefactos.py` contra un release.
