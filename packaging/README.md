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

## Lo que todavía no está

- **Sin firma de código.** Windows mostrará "Windows protegió tu PC" → Más
  información → Ejecutar de todos modos. Va documentado en la página de descarga.
- **Sin descarga del paquete CUDA** (tarea 6 del plan): hoy el instalador deja la
  app en modo CPU. En una máquina con NVIDIA hay que apuntarle a un modelo local
  a mano.
- **Sin wizard de primer arranque** (tarea 7) ni **auto-update** (tarea 9).
