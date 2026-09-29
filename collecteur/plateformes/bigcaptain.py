"""Big Captain (api.big-captain.com).

Paramètres dans config/clubs.csv :
  tenant       identifiant numérique du club (ex. 242)
  alias        alias du club dans l'URL my.big-captain.com/site/<alias>
  discipline   identifiant de la discipline padel
  durees       durées autorisées en minutes, séparées par « + » (ex. 90)

On ne lit jamais la fiche du club (/tenants/<alias>) : elle contient des données administratives.
"""

from __future__ import annotations

from datetime import date

from ..http import Client
from ..modele import Creneau, nettoyer_nom

PARAMETRES = ("tenant", "alias", "discipline")

API = "https://api.big-captain.com/api-mobile/v1"


def lien_reservation(alias: str) -> str:
    return f"https://my.big-captain.com/site/{alias}/bookings/online-booking"


def interpreter(reponse: dict, club_id: str, terrains: dict, duree: int, lien: str) -> list[Creneau]:
    creneaux = []
    for s in reponse.get("data", []):
        if not s.get("canBeBooked") or not s.get("numOfAvailabilites"):
            continue
        for rid in s.get("resources", []):  # seulement les terrains libres
            creneaux.append(Creneau(
                club=club_id,
                terrain=terrains.get(rid, f"Terrain {rid}"),
                date=s["date"],
                heure=s["startTime"][:5],
                duree_min=duree,
                prix_eur=None,
                interieur=None,
                lien=lien,
            ))
    return creneaux


def collecter(club, jours: list[date], client: Client) -> list[Creneau]:
    p = club.params
    lien = lien_reservation(p["alias"])
    entetes = {"Origin": "https://my.big-captain.com", "Referer": "https://my.big-captain.com/"}
    base = f"{API}/{p['tenant']}/bookings"
    liste = client.get_json(f"{base}/disciplines/{p['discipline']}/resources", entetes=entetes)
    terrains = {t["id"]: nettoyer_nom(t["name"]) for t in liste.get("data", [])}
    if not terrains:
        raise ValueError("aucun terrain renvoyé")
    creneaux = []
    for duree in (int(d) for d in p.get("durees", "90").split("+")):
        for jour in jours:
            reponse = client.get_json(
                f"{base}/available-slots",
                params={"disciplineId": p["discipline"], "date": jour.isoformat(),
                        "slotDuration": duree, "resourceIds[]": list(terrains)},
                entetes=entetes,
            )
            if "data" not in reponse:
                raise ValueError(f"réponse inattendue (clés : {list(reponse)[:5]})")
            creneaux += interpreter(reponse, club.id, terrains, duree, lien)
    return creneaux
