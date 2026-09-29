"""Variante locale : collecte toutes les 30 minutes et sert la page sur le réseau de la maison.

    py outils/local.py            (Windows)
    python3 outils/local.py       (Mac, Linux)

Ouvrez ensuite l'adresse affichée depuis le téléphone, connecté au même Wi-Fi.
Ctrl+C pour arrêter.
"""

import functools
import http.server
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PORT = 8000
INTERVALLE_MIN = 30


def adresse_locale() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))  # aucune donnée envoyée : sert seulement à trouver l'interface réseau
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def servir():
    gestionnaire = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(RACINE / "docs"))
    gestionnaire.log_message = lambda *a: None
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), gestionnaire).serve_forever()


def main():
    threading.Thread(target=servir, daemon=True).start()
    print(f"Page : http://localhost:{PORT}  (téléphone sur le même Wi-Fi : http://{adresse_locale()}:{PORT})")
    while True:
        subprocess.run([sys.executable, "-m", "collecteur", *sys.argv[1:]], cwd=RACINE)
        print(f"Prochaine collecte dans {INTERVALLE_MIN} min. Ctrl+C pour arrêter.")
        time.sleep(INTERVALLE_MIN * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
