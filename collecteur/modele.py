"""Format commun renvoyé par tous les adaptateurs."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

FUSEAU = ZoneInfo("Europe/Brussels")

_HEURE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True)
class Creneau:
    club: str            # identifiant du club dans config/clubs.csv
    terrain: str         # nom du terrain tel qu'affiché par la plateforme
    date: str            # jour local, AAAA-MM-JJ
    heure: str           # heure de début locale, HH:MM
    duree_min: int       # durée en minutes
    prix_eur: float | None   # prix total du terrain, None si inconnu
    interieur: bool | None   # True intérieur, False extérieur, None inconnu
    lien: str            # page de réservation (pré-remplie si possible)

    def debut(self) -> datetime:
        return datetime.fromisoformat(f"{self.date}T{self.heure}").replace(tzinfo=FUSEAU)

    def cle(self) -> tuple:
        return (self.club, self.terrain, self.date, self.heure, self.duree_min)

    def en_dict(self) -> dict:
        return asdict(self)


def nettoyer_nom(nom: str) -> str:
    """Décode les échappements JSON et HTML restants (\\u0026amp; -> &) et normalise les espaces."""
    nom = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), nom or "")
    return " ".join(html.unescape(nom).split())


def valider(c: Creneau) -> list[str]:
    """Renvoie la liste des problèmes d'un créneau (vide si tout va bien)."""
    erreurs = []
    if not isinstance(c.club, str) or not c.club:
        erreurs.append("club vide")
    if not isinstance(c.terrain, str) or not c.terrain.strip():
        erreurs.append("terrain vide")
    try:
        date.fromisoformat(c.date)
    except (TypeError, ValueError):
        erreurs.append(f"date invalide : {c.date!r}")
    if not isinstance(c.heure, str) or not _HEURE.match(c.heure):
        erreurs.append(f"heure invalide : {c.heure!r}")
    if not isinstance(c.duree_min, int) or isinstance(c.duree_min, bool) or not 15 <= c.duree_min <= 240:
        erreurs.append(f"durée invalide : {c.duree_min!r}")
    if c.prix_eur is not None and (not isinstance(c.prix_eur, (int, float)) or not 0 <= c.prix_eur <= 500):
        erreurs.append(f"prix invalide : {c.prix_eur!r}")
    if c.interieur not in (True, False, None):
        erreurs.append(f"intérieur invalide : {c.interieur!r}")
    if not isinstance(c.lien, str) or not c.lien.startswith("https://"):
        erreurs.append(f"lien invalide : {c.lien!r}")
    return erreurs
