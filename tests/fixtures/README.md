# Fixtures de audio

Los `.wav` de esta carpeta son grabaciones de voz real y **no se versionan**
(ver `.gitignore`). Para regenerarlos, grabar 60 segundos hablando normal a
16 kHz mono y guardarlos como `voz_60s.wav`, luego recortar con:

    ffmpeg -i voz_60s.wav -t 21 voz_21s.wav
    ffmpeg -i voz_60s.wav -t 6  voz_6s.wav

Los benchmarks de `tools/bench.py` los necesitan; los tests unitarios no.
