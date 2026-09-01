"""Punto de entrada del ejecutable.

No se puede apuntar PyInstaller directo a `flowlibre/__main__.py`: ese archivo
usa imports relativos (`from .app import ...`), que solo funcionan dentro de un
paquete. Analizado como script suelto, PyInstaller no los sigue y **construye un
bundle vacio sin ninguna dependencia** — que ademas compila sin un solo error y
pesa sospechosamente poco. Ya paso una vez: 18 MB en vez de los ~150 esperados.
"""

from flowlibre.__main__ import main

if __name__ == "__main__":
    main()
