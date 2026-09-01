# FlowLibre Fase 5 — Distribución (instalador y auto-update)

Escrito el 2026-08-31, después de cerrar la fase 1. Cubre la sección 10 del spec
(`docs/superpowers/specs/2026-08-25-flowlibre-2.0-design.md`), más la detección de NVIDIA y
la descarga condicional de CUDA de la sección 7.

**Qué entrega:** un link que el autor le pasa a cualquiera, del que sale una app instalada y
funcionando en menos de cinco minutos.

## Dependencias reales, y por qué el plan se parte en dos

El spec dice que la fase 5 depende de las fases 3 (macOS) y 4 (identidad visual). Eso es
cierto para el entregable completo, pero **bloquear todo el trabajo de Windows detrás del
port de macOS retrasaría meses algo que ya se puede tener**. Este plan se ejecuta en dos
carriles:

| Carril | Tareas | Bloqueado por |
|---|---|---|
| **A — Windows** | 1 a 10 | Solo la tarea 8 necesita el `.ico` de la fase 4 |
| **B — macOS** | 11 | Fase 3 completa. No se empieza antes |

Las tareas 1 a 4 no dependen de nada: son deuda de arquitectura que hoy hace **imposible**
empaquetar, y se pueden hacer hoy mismo.

## Los tres bloqueadores que el spec no vio

Verificados en el código el 2026-08-31, antes de escribir este plan:

1. **La app escribe sus datos junto al código.** `config.py` define `CONFIG_PATH`,
   `HISTORY_PATH`, `DICTIONARY_PATH` y `COMMANDS_PATH` todos bajo `ROOT`, que es la carpeta
   que contiene el paquete. Instalada en `C:\Program Files\FlowLibre\`, la app **no puede
   escribir ahí** (permisos), y aunque se instalara por usuario, la primera actualización
   que reemplace la carpeta **se lleva el historial de dictados del autor**. Esto se arregla
   antes de empaquetar nada.
2. **El auto-inicio apunta a un archivo que no existirá.** `autostart.py:23` registra
   `ROOT / "flowlibre.pyw"` con el `pythonw.exe` del venv. En un bundle no hay venv ni
   `.pyw`: hay un `FlowLibre.exe`.
3. **No hay repositorio remoto.** `git remote -v` no devuelve nada. El auto-update del spec
   lee GitHub Releases, así que hace falta subir el repo antes de que exista un release.

## Restricciones globales

- Nada de esto puede cambiar el comportamiento de la app corriendo desde el código fuente
  en `D:\FlowLibre`. El autor la usa todos los días; el desarrollo no se detiene por empaquetar.
- Toda ruta nueva se cubre con test. Los tests no tocan `%APPDATA%` real (ver
  `tests/conftest.py`, que ya aísla el `debug.log` por la misma razón).
- Las cifras de peso del spec (~150 MB de base) son **estimaciones sin verificar**. La
  tarea 5 las mide; si no se cumplen, se reporta el número real antes de seguir.

---

## Task 1: Separar los datos de usuario del código

**Files:** `flowlibre/paths.py` (nuevo), `flowlibre/config.py`, `flowlibre/history.py`,
`tests/test_paths.py` (nuevo)

**Produce:** `flowlibre.paths.data_dir()` — `%APPDATA%\FlowLibre` cuando la app corre
empaquetada, y la raíz del repo cuando corre desde el código fuente.

- [ ] **Step 1:** Tests que fallan. `data_dir()` devuelve la raíz del repo si
      `sys.frozen` no existe; devuelve `%APPDATA%\FlowLibre` si `sys.frozen` es verdadero
      (simulado con monkeypatch, no con un bundle real). `config.yaml` que no existe en
      `%APPDATA%` se **siembra** desde la copia de la instalación en el primer arranque, sin
      sobrescribir uno existente.
- [ ] **Step 2:** Implementar `paths.py` y reapuntar las cuatro constantes de `config.py`.
- [ ] **Step 3:** Migración: si existe `history.jsonl` junto al código y no en `%APPDATA%`,
      se copia (no se mueve — el original queda como respaldo). El autor tiene 176 dictados de
      historial y **perderlos sería el peor resultado posible de esta fase**.
- [ ] **Step 4:** Correr la suite completa. Confirmar que en desarrollo nada cambió de lugar.

## Task 2: Rutas de recursos empaquetados

**Files:** `flowlibre/paths.py`, `flowlibre/transcribe.py`, `tests/test_paths.py`

`_resolve_origen()` resuelve el modelo contra `ROOT`. En un bundle, los recursos de solo
lectura viven en `sys._MEIPASS` (onefile) o junto al `.exe` (onedir), y el modelo descargado
después vive en `%APPDATA%`. Se necesitan las dos rutas, en ese orden de búsqueda.

- [ ] **Step 1:** Test: con `sys.frozen`, un modelo en el directorio de datos gana sobre el
      empaquetado; sin ninguno de los dos, el mensaje de error dice qué hacer (ya existe ese
      aviso, no perderlo).
- [ ] **Step 2:** `resource_dir()` y búsqueda en cascada.

## Task 3: Auto-inicio y accesos directos apuntando al ejecutable

**Files:** `flowlibre/autostart.py`, `tests/test_autostart.py`

- [ ] **Step 1:** Test: con `sys.frozen`, el comando registrado es `"<ruta>\FlowLibre.exe"`
      entre comillas; sin él, el comando de hoy (pythonw + `.pyw`) no cambia.
- [ ] **Step 2:** Implementar. **Ojo:** una ruta con espacios sin comillas rompe el registro
      Run en silencio — la app simplemente no arranca con Windows y nadie sabe por qué.

## Task 4: Detección de NVIDIA y perfil de aceleración

**Files:** `flowlibre/gpu.py` (nuevo), `tests/test_gpu.py`

**Produce:** `detectar_nvidia() -> bool` y `perfil_recomendado() -> dict` con el modelo y el
`compute_type` sugeridos.

- [ ] **Step 1:** Decidir el método de detección **sin depender de CUDA**, que es
      justamente lo que no está instalado todavía. Opción primaria: `nvidia-smi` en el PATH.
      Respaldo: consultar WMI por adaptadores de video. La detección debe ser rápida y no
      tumbar la app si falla — un `False` conservador es aceptable, un crash no.
- [ ] **Step 2:** Perfiles: con NVIDIA, `large-v3-turbo` int8 + `int8_float16`; sin NVIDIA,
      `small` + `int8` en CPU. El spec ya fijó esa decisión.
- [ ] **Step 3:** Tests con el detector simulado en ambos sentidos.

## Task 5: Bundle de PyInstaller sin CUDA — y medir el peso de verdad

**Files:** `packaging/flowlibre.spec` (nuevo), `packaging/README.md`

- [ ] **Step 1:** Spec de PyInstaller en modo **onedir** (arranca más rápido que onefile y
      hace el auto-update parcial posible). Excluir: `av` y `av.libs` (67 MB), `pip`,
      `setuptools` (22 MB), `nvidia*` (1.94 GB — es el punto entero de la tarea).
- [ ] **Step 2:** Construir y **medir el tamaño real**. El spec estima ~150 MB. Anotar el
      número medido en el reporte, cumpla o no.
- [ ] **Step 3:** Correr el `.exe` en la misma máquina y confirmar que dicta en modo CPU con
      `small`, sin CUDA presente en el bundle.
- [ ] **Step 4:** Si el bundle pesa mucho más de lo estimado, listar los diez directorios
      más grandes antes de seguir. No maquillar el número.

## Task 6: Descarga condicional del paquete de aceleración y del modelo

**Files:** `flowlibre/descargas.py` (nuevo), `tests/test_descargas.py`

- [ ] **Step 1:** **Decisión pendiente del autor:** dónde se hospedan el paquete CUDA
      (~1.4 GB) y los modelos. GitHub Releases admite archivos de hasta 2 GB, así que cabe,
      pero cada descarga sale del ancho de banda del repo. Alternativa: los modelos se bajan
      de Hugging Face como hoy, y solo CUDA va en Releases.
- [ ] **Step 2:** Descarga con reanudación (`Range`), verificación de hash y progreso por
      callback. Una descarga de 1.4 GB que se corta al 90% y empieza de cero es la forma más
      rápida de que alguien desinstale la app.
- [ ] **Step 3:** Tests con un servidor local: descarga completa, corte y reanudación, hash
      que no cuadra (debe borrar el archivo y avisar, nunca dejar un binario corrupto).

## Task 7: Wizard de primer arranque

**Files:** `flowlibre/wizard.py` (nuevo), `flowlibre/app.py`

Cuatro pasos, tal como el spec: bienvenida, API key (con botón de saltar y aviso explícito
de que sin key la app funciona en modo crudo), micrófono con medidor en vivo, y descarga del
modelo con barra de progreso.

- [ ] **Step 1:** Se dispara solo cuando no existe `config.yaml` en el directorio de datos.
- [ ] **Step 2:** Reusar el medidor de nivel que ya existe en el overlay en vez de escribir
      otro.
- [ ] **Step 3:** La API key se guarda como variable de entorno de usuario, no en
      `config.yaml` — el archivo se comparte al reportar un problema.

## Task 8: Instalador de Windows

**Files:** `packaging/flowlibre.iss` (nuevo)

**Bloqueada por la fase 4:** necesita `FlowLibre.ico`.

- [ ] **Step 1:** Inno Setup: instalación por usuario en `%LOCALAPPDATA%\Programs\FlowLibre`
      (sin UAC, y sin el problema de permisos de Program Files), accesos directos de
      escritorio y menú inicio, casilla de auto-inicio.
- [ ] **Step 2:** El desinstalador **no borra** `%APPDATA%\FlowLibre`. Pregunta.
- [ ] **Step 3:** Probar la instalación en limpio, la actualización sobre una instalación
      previa (el historial debe sobrevivir) y la desinstalación.

## Task 9: Repositorio remoto, releases y auto-update

**Files:** `flowlibre/actualizacion.py` (nuevo), `.github/workflows/release.yml` (nuevo)

- [ ] **Step 1:** **Decisión pendiente del autor:** repo público o privado. Privado implica
      que las descargas necesitan token, lo que rompe el "un link para compartir".
- [ ] **Step 2:** Subir el repo. Hoy no hay remote.
- [ ] **Step 3:** Versionado en un solo lugar (`flowlibre/__init__.py`), leído por el
      instalador y por el chequeo de actualización.
- [ ] **Step 4:** Chequeo al arrancar, descarga en segundo plano, aplicación al siguiente
      reinicio, aviso desde la bandeja, e interruptor en Ajustes para apagarlo.
- [ ] **Step 5:** Workflow que construye el instalador y publica el release al etiquetar.

## Task 10: Página de descarga

- [ ] **Step 1:** Detección del sistema operativo del visitante, archivo correcto al frente y
      el otro como enlace secundario.
- [ ] **Step 2:** Las instrucciones para saltar SmartScreen y Gatekeeper van **visibles**, no
      escondidas en un acordeón: el spec marca ese susto como el riesgo de probabilidad alta.

## Task 11: macOS (carril B)

**Bloqueada por la fase 3.** PyInstaller a `FlowLibre.app`, create-dmg a
`FlowLibre-2.0.0.dmg`, e instrucciones de Gatekeeper. No se empieza hasta que la app corra
en la Mac.

## Task 12: Validación

- [ ] Instalar en una máquina limpia (o una VM) sin Python y sin CUDA, y cronometrar desde el
      link hasta la primera frase dictada. **El criterio 4 del spec pide menos de 5 minutos.**
- [ ] Medir la instalación con NVIDIA y sin ella, contra los objetivos del criterio 3
      (≤ 2.5 GB con NVIDIA, ≤ 800 MB sin ella) y el del instalador (≤ 200 MB).
- [ ] Escribir `docs/superpowers/resultados-fase-5.md` con los números reales, incluidos los
      que no se cumplan.

---

## Decisiones que necesito del autor antes de ejecutar

1. **Repo público o privado** en GitHub (tarea 9). El auto-update y el link para compartir
   son mucho más simples si es público.
2. **Dónde se hospeda el paquete CUDA de 1.4 GB** (tarea 6).
3. **Nombre y dominio** de la página de descarga (tarea 10), si es que quieres uno propio.
