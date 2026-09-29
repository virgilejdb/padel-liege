"""Anybuddy (agrégateur, www.anybuddyapp.com).

Paramètres dans config/clubs.csv :
  slug   nom du club dans l'URL anybuddyapp.com/fr-be/club/<slug>/padel

Une seule requête couvre toute la période. Les noms des terrains viennent de la page club.
"""

from __future__ import annotations

import re
from datetime import date

from ..http import Client
from ..modele import Creneau, nettoyer_nom

PARAMETRES = ("slug",)

SITE = "https://www.anybuddyapp.com"

_SERVICE = re.compile(r'"id":"([0-9a-f-]{36})","name":"((?:[^"\\]|\\.)*)"[^{}]*?"serviceTypeId":"padel-court-rental"[^{}]*?"resourceId":"([0-9a-f-]{36})"')
_RESSOURCE = re.compile(r'"id":"([0-9a-f-]{36})","name":"(?:[^"\\]|\\.)*","description":[^,]*,"resourceTypeId":"padel-court"')


def lien_reservation(slug: str) -> str:
    return f"{SITE}/fr-be/club/{slug}/padel"


def lire_terrains(html: str) -> dict[str, tuple[str, bool | None]]:
    """{service_id: (nom, intérieur)} des terrains de padel de la page club."""
    texte = html.replace('\\"', '"')
    interieur_par_ressource = {}
    for m in _RESSOURCE.finditer(texte):
        fin = texte.find("]}", m.end())
        carac = texte[m.end():fin]
        interieur_par_ressource[m.group(1)] = (
            True if '"id":"indoor"' in carac else False if '"id":"outdoor"' in carac else None)
    terrains = {}
    for sid, nom, rid in _SERVICE.findall(texte):
        terrains[sid] = (nettoyer_nom(nom), interieur_par_ressource.get(rid))
    return terrains


def interpreter(reponse: dict, club_id: str, terrains: dict, lien: str) -> list[Creneau]:
    creneaux = []
    for bloc in reponse.get("data", []):
        jour, heure = bloc["startDateTime"].split("T")
        for s in bloc.get("services", []):
            nom, interieur = terrains.get(s["id"], (None, None))
            if nom is None:
                nom = f"Terrain {s['id'][:4]}"
            prix = s.get("discountPrice", s.get("price"))
            creneaux.append(Creneau(
                club=club_id,
                terrain=nom,
                date=jour,
                heure=heure[:5],
                duree_min=int(s["duration"]),
                prix_eur=round(prix / 100, 2) if prix is not None else None,
                interieur=interieur,
                lien=lien,
            ))
    return creneaux


def collecter(club, jours: list[date], client: Client) -> list[Creneau]:
    slug = club.params["slug"]
    lien = lien_reservation(slug)
    terrains = lire_terrains(client.get_texte(lien, entetes={"Accept": "text/html,application/xhtml+xml"}))
    if not terrains:
        raise ValueError("aucun terrain de padel trouvé sur la page club")
    reponse = client.get_json(
        f"{SITE}/api/v1/availabilities",
        params={"clubSlug": slug, "dateFrom": jours[0].isoformat(),
                "dateTo": f"{jours[-1].isoformat()}T23:59", "activity": "padel"},
        entetes={"Referer": lien},
    )
    if "data" not in reponse:
        raise ValueError(f"réponse inattendue (clés : {list(reponse)[:5]})")
    return interpreter(reponse, club.id, terrains, lien)
