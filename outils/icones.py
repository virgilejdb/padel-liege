"""Génère les icônes de l'écran d'accueil (balle de padel sur fond marine), sans dépendance.

    python outils/icones.py
"""

import math
import struct
import zlib
from pathlib import Path

FOND = (15, 27, 45)
BALLE = (198, 239, 58)
COUTURE = (250, 252, 240)
DOSSIER = Path(__file__).resolve().parent.parent / "docs" / "icones"


def pixel(x, y, n):
    cx = cy = n / 2
    r = n * 0.30
    d = math.hypot(x - cx, y - cy)
    if d > r + 1:
        return FOND
    # Deux coutures courbes, comme sur une balle.
    for sens in (-1, 1):
        ox = cx + sens * r * 1.35
        if abs(math.hypot(x - ox, y - cy) - r * 0.95) < n * 0.018:
            return COUTURE if d < r else FOND
    if d > r:  # anticrénelage simple du bord
        t = r + 1 - d
        return tuple(round(f + (b - f) * t) for f, b in zip(FOND, BALLE))
    return BALLE


def png(n, chemin):
    lignes = b"".join(b"\0" + bytes(c for x in range(n) for c in pixel(x + .5, y + .5, n)) for y in range(n))
    def bloc(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    chemin.write_bytes(b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
                       + bloc(b"IDAT", zlib.compress(lignes, 9)) + bloc(b"IEND", b""))


if __name__ == "__main__":
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for n in (180, 192, 512):
        png(n, DOSSIER / f"icone-{n}.png")
        print("écrit", DOSSIER / f"icone-{n}.png")
