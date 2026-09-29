"""MATCHi (www.matchi.se). La réponse est un fragment HTML, pas du JSON.

Paramètres dans config/clubs.csv :
  facility   identifiant numérique du club
  slug       nom du club dans l'URL matchi.se/facilities/<slug>

On s'appuie sur le lien « Réserver » de chaque terrain libre (start et end en epoch ms UTC),
plus stable que la mise en page du tableau.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from ..http import Client, construire_url
from ..modele import FUSEAU, Creneau, nettoyer_nom

PARAMETRES = ("facility", "slug")

SITE = "https://www.matchi.se"
PADEL = "5"

_LIGNE = re.compile(r'<li class="list-group-item">(.*?)</li>', re.S)
_CELLULE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_DEBUT_FIN = re.compile(r"start%3D(\d{13})%26end%3D(\d{13})")
_BALISE = re.compile(r"<[^>]+>")


def lien_reservation(slug: str, jour: date) -> str:
    return f"{SITE}/facilities/{slug}?date={jour.isoformat()}&sport={PADEL}"


def _local(ms: str) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).astimezone(FUSEAU)


def interpreter(html: str, club_id: str, slug: str) -> list[Creneau]:
    creneaux = []
    for ligne in _LIGNE.findall(html):
        m = _DEBUT_FIN.search(ligne)
        cellules = _CELLULE.findall(ligne)
        if not m or len(cellules) < 3:
            continue
        debut, fin = _local(m.group(1)), _local(m.group(2))
        infos = _BALISE.sub(" ", cellules[2]).lower()
        # MATCHi ne mentionne que les terrains extérieurs (« (Outdoors) », « (À l'extérieur) »).
        interieur = not ("outdoor" in infos or "extérieur" in infos)
        creneaux.append(Creneau(
            club=club_id,
            terrain=nettoyer_nom(_BALISE.sub(" ", cellules[0])),
            date=debut.date().isoformat(),
            heure=debut.strftime("%H:%M"),
            duree_min=int((fin - debut).total_seconds() // 60),
            prix_eur=None,  # chargé à part par le site, non collecté
            interieur=interieur,
            lien=lien_reservation(slug, debut.date()),
        ))
    return creneaux


def _creneaux(p: dict, jour: date) -> tuple[str, dict]:
    return f"{SITE}/book/listSlots", {"wl": "", "facility": p["facility"], "date": jour.isoformat(),
                                      "sport": PADEL, "week": "", "year": ""}


def requetes(club, jours: list[date]) -> list[str]:
    """Adresses à interroger depuis l'iPhone."""
    return [construire_url(*_creneaux(club.params, j)) for j in jours]


def collecter(club, jours: list[date], client: Client) -> list[Creneau]:
    p = club.params
    page = f"{SITE}/facilities/{p['slug']}"
    creneaux = []
    for jour in jours:
        url, params = _creneaux(p, jour)
        html = client.get_texte(url, params=params, entetes={
            "X-Requested-With": "XMLHttpRequest", "Accept": "text/html, */*; q=0.01", "Referer": page})
        if "<" not in html:  # attendu : un fragment HTML, même vide de créneaux
            raise ValueError(f"réponse inattendue : {html[:100]!r}")
        creneaux += interpreter(html, club.id, p["slug"])
    return creneaux
