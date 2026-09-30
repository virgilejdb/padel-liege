"""Télécharge une fois les logos des clubs dans docs/logos/<id>.png (128 px), pour la page.

    py -m pip install pillow      (une fois)
    py outils/logos.py            logos manquants seulement
    py outils/logos.py --tous     tout retélécharger

Sources, par ordre de préférence :
  1. paramètre logo=<url> dans config/clubs.csv (choix manuel) ;
  2. logo publié par la plateforme (Doinsport, Sport-finder, MATCHi) ;
  3. icône du site web du club (Playtomic donne l'adresse du site).
Sans logo trouvé, la page affiche les initiales du club. Pour en ajouter un à la main,
déposez simplement une image carrée dans docs/logos/<id>.png.
"""

import html
import io
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from collecteur.__main__ import lire_clubs  # noqa: E402
from collecteur.http import Client, ErreurHttp  # noqa: E402

DOSSIER = Path(__file__).resolve().parent.parent / "docs" / "logos"
TAILLE = 128
client = Client(pause=(0.8, 1.6))


def depuis_doinsport(club):
    d = client.get_json(f"https://api-v3.doinsport.club/clubs/{club.params['club']}")
    chemin = (d.get("logo") or {}).get("contentUrl")
    return f"https://api-v3.doinsport.club{chemin}" if chemin else None


def depuis_sportfinder(club):
    d = client.get_json(f"https://www.sport-finder.com/api/centers/{club.params['centre']}",
                        entetes={"Accept": "application/ld+json"})
    return d.get("logo")


def depuis_matchi(club):
    page = client.get_texte(f"https://www.matchi.se/facilities/{club.params['slug']}", entetes={"Accept": "text/html"})
    m = re.search(r'<img class="img-responsive img-responsive" src="([^"]+)"', page)
    return m.group(1) if m else None


def icone_du_site(site):
    """Plus grande icône déclarée par un site web (apple-touch-icon, icon), sinon son image de partage."""
    page = client.get_texte(site, entetes={"Accept": "text/html"})
    candidats = []
    for balise in re.findall(r"<link[^>]+>", page, re.I):
        rel = re.search(r'rel=["\']([^"\']+)', balise, re.I)
        href = re.search(r'href=["\']([^"\']+)', balise, re.I)
        if rel and href and "icon" in rel.group(1).lower():
            tailles = re.search(r'sizes=["\'](\d+)', balise)
            bonus = 1000 if "apple-touch" in rel.group(1).lower() else 0
            candidats.append((bonus + int(tailles.group(1) if tailles else 16), html.unescape(href.group(1))))
    if candidats:
        return urllib.parse.urljoin(site, max(candidats)[1])
    og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page, re.I)
    return urllib.parse.urljoin(site, html.unescape(og.group(1))) if og else None


def depuis_playtomic(club):
    page = client.get_texte(f"https://playtomic.com/fr/clubs/{club.params['slug']}",
                            entetes={"Accept": "text/html"}).replace('\\"', '"')
    m = re.search(r'"WEBSITE_URL":"(https?://[^"]+)"', page)
    return icone_du_site(m.group(1)) if m else None


SOURCES = {"doinsport": depuis_doinsport, "sportfinder": depuis_sportfinder,
           "matchi": depuis_matchi, "playtomic": depuis_playtomic}


def enregistrer(url, chemin):
    brut = client.get(url, entetes={"Accept": "image/avif,image/webp,image/png,image/*,*/*"})
    img = Image.open(io.BytesIO(brut))
    img = img.convert("RGBA")
    # Rogne les bords transparents, puis centre dans un carré blanc (lisible en thème sombre aussi).
    boite = img.getbbox()
    if boite:
        img = img.crop(boite)
    img.thumbnail((TAILLE - 12, TAILLE - 12), Image.LANCZOS)
    carre = Image.new("RGBA", (TAILLE, TAILLE), (255, 255, 255, 255))
    carre.alpha_composite(img, ((TAILLE - img.width) // 2, (TAILLE - img.height) // 2))
    carre.convert("RGB").save(chemin, "PNG", optimize=True)


def main():
    tous = "--tous" in sys.argv
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for club in lire_clubs():
        chemin = DOSSIER / f"{club.id}.png"
        if chemin.exists() and not tous:
            continue
        try:
            url = club.params.get("logo") or (SOURCES.get(club.plateforme, lambda c: None))(club)
            if not url:
                print(f"{club.id:18} aucun logo trouvé (initiales)")
                continue
            enregistrer(url, chemin)
            print(f"{club.id:18} ok  {url[:80]}")
        except (ErreurHttp, OSError, ValueError) as e:
            print(f"{club.id:18} échec : {e}")


if __name__ == "__main__":
    main()
