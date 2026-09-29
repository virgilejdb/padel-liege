"""Doinsport (api-v3.doinsport.club).

Paramètres dans config/clubs.csv :
  club        UUID du club Doinsport
  activites   UUID des activités padel, séparés par « + » (plusieurs pour les clubs
              qui séparent intérieur et extérieur)
  site        sous-domaine de la marque blanche (ex. bayardsclub), pour le lien
"""

from __future__ import annotations

from datetime import date

from ..http import Client
from ..modele import Creneau, nettoyer_nom

PARAMETRES = ("club", "activites", "site")

API = "https://api-v3.doinsport.club"


def lien_reservation(site: str, club: str, activite: str) -> str:
    # La date n'est pas transmissible par l'URL (état interne de l'application).
    return f"https://{site}.doinsport.club/select-booking?guid={club}&activitySelectedId={activite}"


def interpreter(reponse: dict, club_id: str, jour: date, lien: str) -> list[Creneau]:
    """Transforme une réponse de /clubs/playgrounds/plannings/<jour> en créneaux libres."""
    creneaux = []
    for terrain in reponse.get("hydra:member", []):
        nom = nettoyer_nom(terrain.get("name"))
        interieur = terrain.get("indoor")
        for activite in terrain.get("activities", []):
            for slot in activite.get("slots", []):
                for prix in slot.get("prices", []):
                    if not prix.get("bookable"):
                        continue
                    ppp = prix.get("pricePerParticipant")
                    n = prix.get("participantCount") or 1
                    creneaux.append(Creneau(
                        club=club_id,
                        terrain=nom,
                        date=jour.isoformat(),
                        heure=slot["startAt"][:5],
                        duree_min=int(prix["duration"]) // 60,
                        prix_eur=round(ppp * n / 100, 2) if ppp is not None else None,
                        interieur=interieur if isinstance(interieur, bool) else None,
                        lien=lien,
                    ))
    return creneaux


def collecter(club, jours: list[date], client: Client) -> list[Creneau]:
    p = club.params
    activites = p["activites"].split("+")
    entetes = {
        "Origin": f"https://{p['site']}.doinsport.club",
        "Referer": f"https://{p['site']}.doinsport.club/",
    }
    creneaux = []
    for activite in activites:
        lien = lien_reservation(p["site"], p["club"], activite)
        for jour in jours:
            reponse = client.get_json(
                f"{API}/clubs/playgrounds/plannings/{jour.isoformat()}",
                params={
                    "club.id": p["club"],
                    "from": "00:00",
                    "to": "23:59:59",
                    "activities.id": activite,
                    "bookingType": "unique",
                },
                entetes=entetes,
            )
            if "hydra:member" not in reponse:
                raise ValueError(f"réponse inattendue (clés : {list(reponse)[:5]})")
            creneaux += interpreter(reponse, club.id, jour, lien)
    return creneaux
