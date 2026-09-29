"""Sport-finder (www.sport-finder.com/api).

Paramètres dans config/clubs.csv :
  produit   identifiant de la location de terrain (URL .../booking/field_rental/<produit>/book)
  centre    identifiant du centre (pour lire les noms des terrains)
  slug      nom du centre dans l'URL sport-finder.com/fr/center/<slug>
"""

from __future__ import annotations

from datetime import date

from ..http import Client
from ..modele import Creneau, nettoyer_nom

PARAMETRES = ("produit", "centre", "slug")

SITE = "https://www.sport-finder.com"
PADEL = "68"
ENTETES = {"Accept": "application/ld+json, application/json"}


def lien_reservation(slug: str, produit: str) -> str:
    return f"{SITE}/fr/center/{slug}/booking/field_rental/{produit}/book?sport={PADEL}"


def lire_terrains(reponse: dict) -> dict[int, tuple[str, bool | None]]:
    terrains = {}
    for f in reponse.get("hydra:member", []):
        interieur = None
        for a in f.get("attributes", []):
            if a.get("definition", {}).get("code") == "resource_type":
                v = (a.get("value") or {}).get("value")
                interieur = False if v == "exterior" else True if v in ("interior", "indoor") else None
        terrains[f["id"]] = (nettoyer_nom(f.get("name")) or f"Terrain {f['id']}", interieur)
    return terrains


def interpreter(reponse: dict, club_id: str, terrains: dict, lien: str) -> list[Creneau]:
    creneaux = []
    for r in reponse.get("results", []):
        rid = r["resource"]["id"]
        nom, interieur = terrains.get(rid, (f"Terrain {rid}", None))
        jour, heure = r["start"].split("T")
        creneaux.append(Creneau(
            club=club_id,
            terrain=nom,
            date=jour,
            heure=heure[:5],
            duree_min=int(r["duration"]),
            prix_eur=float(r["price"]) if r.get("price") is not None else None,
            interieur=interieur,
            lien=lien,
        ))
    return creneaux


def collecter(club, jours: list[date], client: Client) -> list[Creneau]:
    p = club.params
    lien = lien_reservation(p["slug"], p["produit"])
    entetes = {**ENTETES, "Referer": lien}
    terrains = lire_terrains(client.get_json(
        f"{SITE}/api/fields",
        params={"center": p["centre"], "sports": PADEL, "product": p["produit"], "page": 1},
        entetes=entetes,
    ))
    creneaux = []
    for jour in jours:
        reponse = client.get_json(
            f"{SITE}/api/field_rentals/{p['produit']}/availabilities",
            params={"date": jour.isoformat(), "sport": PADEL},
            entetes=entetes,
        )
        if "results" not in reponse:
            raise ValueError(f"réponse inattendue (clés : {list(reponse)[:5]})")
        creneaux += interpreter(reponse, club.id, terrains, lien)
    return creneaux
