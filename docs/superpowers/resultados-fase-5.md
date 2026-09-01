# Fase 5 — Distribución: resultados medidos

Escrito el 2026-09-01. Los números son medidos, no estimados. Los que no
cumplen el objetivo también están aquí.

## Criterio 3 — peso

| | Objetivo del spec | Medido | |
|---|---:|---:|---|
| Instalador | ≤ 200 MB | **70.9 MB** | cumple |
| Bundle sin comprimir | — | 263 MB | |
| DLLs de CUDA dentro del instalador | 0 | **0** | cumple |
| Instalación sin NVIDIA | ≤ 800 MB | *sin medir* | falta una máquina sin NVIDIA |
| Instalación con NVIDIA | ≤ 2.5 GB | *sin medir* | falta publicar los assets |

Las dos últimas filas no se pueden cerrar todavía: dependen de descargar los
artefactos de un release que aún no existe (no hay repo remoto). Lo que sí está
medido es que **el instalador no lleva una sola DLL de CUDA** — 1.94 GB que se
bajan aparte y solo en máquinas que puedan usarlas.

## Criterio 4 — del link a la primera frase, en menos de 5 minutos

**Sin medir, y no se puede medir todavía.** Necesita una máquina limpia (o una
VM) sin Python y sin CUDA, y un link real del que bajar el instalador. El link
no existe hasta que el repo esté subido y haya un release.

Lo que sí se puede decir hoy: el instalador son 70.9 MB, la instalación es por
usuario y sin UAC, y el asistente de primer arranque son cuatro pasos de los
cuales tres se pueden saltar.

## Lo que se verificó del ejecutable empaquetado

Contra un `%APPDATA%` limpio y aislado, con el bundle de consola (`console=True`)
para poder leer stderr:

- Arranca y sigue vivo a los 25 segundos.
- Siembra sus datos en un `%APPDATA%` vacío sin pisar lo que ya estaba.
- Carga faster-whisper y el modelo **sin una sola excepción** (stderr vacío).

## Lo que NO se verificó

- **Un dictado real de punta a punta con la app instalada.** Necesita atajo
  global y micrófono, que este shell no ve.
- **La interfaz del asistente.** Necesita display, micrófono y una descarga real.
  Lo que sí está probado es su lógica, que es donde viven los fallos mudos.
- **La instalación en una máquina limpia**, la actualización sobre una
  instalación previa, y la desinstalación (tarea 8, step 3).
- **El auto-update de punta a punta.** El chequeo está probado contra cinco
  formas de fallar, pero nunca ha visto un release de verdad.

## Los dos defectos que encontró el build de consola

Ninguno de los dos daba error al construir. Los dos producían un binario que
compila, abre, se ve perfecto y no transcribe — el mismo patrón de C41.

### 1. El bundle empaquetaba el `config.yaml` de desarrollo

Cada instalación limpia nacía con el atajo del autor, su micrófono Elgato, y
`whisper_model: "models/large-v3-turbo-int8"` — una ruta que en otra máquina no
existe.

**Por qué es grave y no cosmético:** faster-whisper trata cualquier cadena como
`repo_id` de Hugging Face. Le pidió `models/large-v3-turbo-int8` a la API, HF
respondió **401 Unauthorized**, y el hilo de carga murió con un traceback que
habla de credenciales. Con `console=False` ese traceback no lo ve nadie: el
síntoma es "la app no transcribe".

**Arreglo:** se empaqueta `packaging/config.plantilla.yaml`, derivada del
config real para que los comentarios (que son la documentación que el usuario
lee) no se queden atrás, pero con los valores personales en su default.
`tests/test_plantilla_config.py` lo caza sin construir el bundle.

### 2. Una ruta local inexistente acababa en Hugging Face

Independiente del anterior, y peor: pasaba con **cualquier** ruta configurada
que no existiera. `_resolve_origen()` imprimía el aviso correcto y luego
devolvía la ruta igual.

**Arreglo:** cae a `small`, que es un modelo que HF de verdad tiene, y conserva
el mensaje que dice cómo generar el int8. La red de seguridad no puede fallar
ella también.

## El método, que vale más que los hallazgos

Los dos defectos aparecieron por lo mismo que C41: **construir una variante con
`console=True` y leer stderr**. Ninguna prueba unitaria los tenía, ninguno daba
error al compilar, y el bundle normal es mudo por diseño.

Ahora sí hay pruebas de los dos — escritas *después* de verlos, que es la señal
de que el arnés de pruebas no los cubría.
