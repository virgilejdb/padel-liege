"""Playtomic (proxy public de playtomic.com).

Paramètres dans config/clubs.csv :
  tenant   UUID du club (tenant_id)
  slug     nom du club dans l'URL playtomic.com/fr/clubs/<slug>

Attention : les heures renvoyées sont en UTC.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from ..http import Client, construire_url
from ..modele import FUSEAU, Creneau, nettoyer_nom

PARAMETRES = ("tenant", "slug")

SITE = "https://playtomic.com"
TERRAINS_CONNUS = Path(__file__).resolve().parents[2] / "config" / "terrains_playtomic.json"

_RESSOURCE = re.compile(r'\{"resourceId":"([^"]+)","name":"((?:[^"\\]|\\.)*)","sport":"([A-Z_]+)","features":\[([^\]]*)\]')


def lien_reservation(slug: str, jour: date) -> str:
    return f"{SITE}/fr/clubs/{slug}?date={jour.isoformat()}"


def lire_terrains(html: str) -> dict[str, tuple[str, bool | None]]:
    """Extrait {resource_id: (nom, intérieur)} des terrains de padel de la page club."""
    texte = html.replace('\\"', '"')
    terrains = {}
    for rid, nom, sport, features in _RESSOURCE.findall(texte):
        if sport != "PADEL":
            continue
        interieur = True if '"indoor"' in features else False if '"outdoor"' in features else None
        # « Terrain 3 | À la recherche d'un partenaire » : on garde la partie avant « | ».
        nom = nom.split("|")[0]
        terrains[rid] = (nettoyer_nom(nom), interieur)
    return terrains


def _prix(texte) -> float | None:
    m = re.match(r"\s*([\d.,]+)\s*EUR", str(texte or ""))
    return float(m.group(1).replace(",", ".")) if m else None


def interpreter(reponse: list, club_id: str, slug: str, terrains: dict) -> list[Creneau]:
    creneaux = []
    for bloc in reponse:
        nom, interieur = terrains.get(bloc["resource_id"], (None, None))
        if nom is None:
            continue  # terrain d'un autre sport ou inconnu de la page club
        for s in bloc.get("slots", []):
            utc = datetime.fromisoformat(f"{bloc['start_date']}T{s['start_time']}").replace(tzinfo=timezone.utc)
            local = utc.astimezone(FUSEAU)
            creneaux.append(Creneau(
                club=club_id,
                terrain=nom,
                date=local.date().isoformat(),
                heure=local.strftime("%H:%M"),
                duree_min=int(s["duration"]),
                prix_eur=_prix(s.get("price")),
                interieur=interieur,
                lien=lien_reservation(slug, local.date()),
            ))
    return creneaux


def terrains_connus(tenant: str) -> dict[str, tuple[str, bool | None]]:
    """Noms des terrains enregistrés dans config/terrains_playtomic.json (mode iPhone)."""
    try:
        donnees = json.loads(TERRAINS_CONNUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {rid: (t["nom"], t["interieur"]) for rid, t in donnees.get(tenant, {}).items()}


def _disponibilites(p: dict, jour: date) -> tuple[str, dict]:
    return f"{SITE}/api/clubs/availability", {"tenant_id": p["tenant"], "date": jour.isoformat(), "sport_id": "PADEL"}


def requetes(club, jours: list[date]) -> list[str]:
    """Adresses à interroger depuis l'iPhone (sans la page club, remplacée par les terrains connus)."""
    return [construire_url(*_disponibilites(club.params, j)) for j in jours]


def collecter(club, jours: list[date], client: Client) -> list[Creneau]:
    p = club.params
    page = f"{SITE}/fr/clubs/{p['slug']}"
    if getattr(client, "rejoue", False):
        terrains = terrains_connus(p["tenant"])
    else:
        terrains = lire_terrains(client.get_texte(page, entetes={"Accept": "text/html,application/xhtml+xml"}))
    if not terrains:
        raise ValueError("aucun terrain de padel trouvé sur la page club")
    creneaux = []
    for jour in jours:
        url, params = _disponibilites(p, jour)
        reponse = client.get_json(url, params=params, entetes={"Referer": page})
        if not isinstance(reponse, list):
            raise ValueError(f"réponse inattendue : {str(reponse)[:100]}")
        creneaux += interpreter(reponse, club.id, p["slug"], terrains)
    return creneaux
