"""Collecte des créneaux libres de tous les clubs de config/clubs.csv.

    python -m collecteur                      tous les clubs, 7 jours
    python -m collecteur --clubs bayards      un ou plusieurs clubs (séparés par des virgules)
    python -m collecteur --jours 2 --apercu   sans écrire le JSON, affiche un résumé

Les clubs marqués via=telephone ne sont jamais interrogés d'ici : leurs réponses arrivent
du raccourci iPhone (option --telephone).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import logging
import os
import sys
import tarfile
import traceback
import urllib.request
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from .http import Client, ClientRejoue
from .modele import FUSEAU, Creneau, valider
from .plateformes import PLATEFORMES

RACINE = Path(__file__).resolve().parent.parent
CONFIG = RACINE / "config" / "clubs.csv"
SORTIE = RACINE / "docs" / "data" / "creneaux.json"

log = logging.getLogger("collecteur")


@dataclass
class Club:
    id: str
    nom: str
    commune: str
    plateforme: str
    params: dict

    @property
    def via_telephone(self) -> bool:
        return self.params.get("via") == "telephone"


def lire_clubs(chemin: Path = CONFIG) -> list[Club]:
    clubs = []
    with open(chemin, encoding="utf-8", newline="") as f:
        for ligne in csv.DictReader(f):
            if not ligne["id"] or ligne["id"].startswith("#"):
                continue
            params = {}
            for morceau in (ligne.get("parametres") or "").split(";"):
                if "=" in morceau:
                    k, v = morceau.split("=", 1)
                    params[k.strip()] = v.strip()
            clubs.append(Club(ligne["id"].strip(), ligne["nom"].strip(), ligne["commune"].strip(),
                              ligne["plateforme"].strip().lower(), params))
    ids = [c.id for c in clubs]
    doublons = {i for i in ids if ids.count(i) > 1}
    if doublons:
        raise SystemExit(f"identifiants en double dans {chemin.name} : {doublons}")
    return clubs


def collecter_club(club: Club, jours, client, maintenant: datetime) -> list[Creneau]:
    module = PLATEFORMES.get(club.plateforme)
    if module is None:
        raise ValueError(f"plateforme inconnue : {club.plateforme}")
    # Paramètre optionnel interieur=oui|non, utilisé quand la plateforme ne le précise pas.
    defaut = {"oui": True, "non": False}.get(club.params.get("interieur", "").lower())
    vus, resultat = set(), []
    for c in module.collecter(club, jours, client):
        if c.debut() < maintenant or c.cle() in vus:
            continue
        if c.interieur is None and defaut is not None:
            c = replace(c, interieur=defaut)
        vus.add(c.cle())
        resultat.append(c)
    problemes = {p for c in resultat for p in valider(c)}
    if problemes:
        # Un format inattendu signale un changement du site : on préfère l'échec visible.
        raise ValueError("format inattendu : " + "; ".join(sorted(problemes)[:3]))
    return sorted(resultat, key=lambda c: (c.date, c.heure, c.terrain, c.duree_min))


# Format du fichier publié : compact, pour rester léger sur téléphone.
COLONNES = ["club", "terrain", "date", "heure", "duree_min", "prix_eur", "interieur", "lien"]


def encoder(creneaux: list[dict]) -> tuple[list, list]:
    """Transforme les créneaux en lignes compactes, les liens étant mis en commun dans une table."""
    liens, index, lignes = [], {}, []
    for c in creneaux:
        if c["lien"] not in index:
            index[c["lien"]] = len(liens)
            liens.append(c["lien"])
        lignes.append([c[k] for k in COLONNES[:-1]] + [index[c["lien"]]])
    return liens, lignes


def decoder(donnees: dict) -> list[dict]:
    colonnes, liens = donnees.get("colonnes", COLONNES), donnees.get("liens", [])
    resultat = []
    for ligne in donnees.get("creneaux", []):
        c = dict(zip(colonnes, ligne))
        c["lien"] = liens[c["lien"]]
        resultat.append(c)
    return resultat


def lire_precedent(source: str) -> dict:
    """Dernier fichier publié (chemin local ou URL), pour garder les données des clubs en panne."""
    try:
        if source.startswith("https://"):
            with urllib.request.urlopen(urllib.request.Request(source, headers={"Cache-Control": "no-cache"}),
                                        timeout=20) as r:
                return json.loads(r.read())
        return json.loads(Path(source).read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("état précédent illisible (%s) : %s", source, e)
        return {}


def lire_envoi_telephone(chemin: Path | None) -> dict | None:
    """Réponses récupérées par le raccourci iPhone : JSON brut, ou archive .gz, .tar.gz ou .zip
    (selon ce que produit l'action « Créer une archive » de Raccourcis)."""
    if not chemin or not chemin.exists():
        return None
    try:
        brut = chemin.read_bytes()
        if brut[:2] == b"\x1f\x8b":
            brut = gzip.decompress(brut)
        if brut[257:262] == b"ustar":
            with tarfile.open(fileobj=io.BytesIO(brut)) as tar:
                brut = next(tar.extractfile(m) for m in tar.getmembers() if m.isfile()).read()
        elif brut[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(brut)) as z:
                brut = z.read(next(n for n in z.namelist() if not n.endswith("/")))
        envoi = json.loads(brut.decode("utf-8-sig"))
        if not isinstance(envoi.get("reponses"), dict) or not envoi.get("jours"):
            raise ValueError("clés « jours » et « reponses » attendues")
        return envoi
    except Exception as e:
        log.error("envoi iPhone illisible (%s) : %s", chemin, e)
        return None


def ecrire_requetes_telephone(chemin: Path, clubs: list[Club], jours, horodatage: str):
    """Liste des adresses que le raccourci iPhone doit interroger (publiée avec la page)."""
    urls = []
    for club in clubs:
        if club.via_telephone:
            urls += PLATEFORMES[club.plateforme].requetes(club, jours)
    chemin.write_text(json.dumps({"genere_le": horodatage, "jours": [j.isoformat() for j in jours],
                                  "requetes": urls}, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("écrit : %s (%d adresses pour l'iPhone)", chemin, len(urls))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m collecteur")
    ap.add_argument("--clubs", help="identifiants de clubs, séparés par des virgules")
    ap.add_argument("--jours", type=int, default=7)
    ap.add_argument("--sortie", type=Path, default=SORTIE)
    ap.add_argument("--precedent", help="fichier ou URL du dernier JSON publié (par défaut : --sortie)")
    ap.add_argument("--telephone", type=Path, help="fichier envoyé par le raccourci iPhone")
    ap.add_argument("--telephone-date", help="heure de l'envoi iPhone (ISO), par défaut celle du fichier")
    ap.add_argument("--seulement-telephone", action="store_true",
                    help="ne traite que les clubs iPhone, les autres gardent leur dernier état")
    ap.add_argument("--apercu", action="store_true", help="affiche un résumé sans écrire le JSON")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    tous = lire_clubs()
    clubs = tous
    if args.clubs:
        voulus = {x.strip() for x in args.clubs.split(",")}
        inconnus = voulus - {c.id for c in tous}
        if inconnus:
            raise SystemExit(f"clubs inconnus : {inconnus}")
        clubs = [c for c in tous if c.id in voulus]
    if args.seulement_telephone:
        clubs = [c for c in clubs if c.via_telephone]

    maintenant = datetime.now(FUSEAU)
    horodatage = maintenant.isoformat(timespec="seconds")
    maintenant_txt = maintenant.strftime("%Y-%m-%dT%H:%M")
    jours = [(maintenant + timedelta(days=i)).date() for i in range(args.jours)]

    precedent = lire_precedent(args.precedent or str(args.sortie))
    etat_precedent = {c["id"]: c for c in precedent.get("clubs", [])}
    creneaux_precedents = defaultdict(list)
    for c in decoder(precedent) if precedent.get("version") == 2 else []:
        if f"{c['date']}T{c['heure']}" >= maintenant_txt:
            creneaux_precedents[c["club"]].append(c)

    envoi = lire_envoi_telephone(args.telephone)
    date_envoi = None
    if envoi:
        brute = args.telephone_date or datetime.fromtimestamp(args.telephone.stat().st_mtime, FUSEAU).isoformat()
        date_envoi = datetime.fromisoformat(brute).astimezone(FUSEAU).isoformat(timespec="seconds")
        log.info("envoi iPhone du %s : %d réponses", date_envoi, len(envoi["reponses"]))

    resultats: dict[str, tuple] = {}

    def traiter(groupe: list[Club], client, jours_groupe):
        for club in groupe:
            try:
                cr = collecter_club(club, jours_groupe, client, maintenant)
                resultats[club.id] = ("ok", cr, None)
                log.info("%-18s %5d créneaux", club.id, len(cr))
            except Exception as e:  # une panne isolée ne doit pas arrêter les autres clubs
                resultats[club.id] = ("erreur", None, f"{type(e).__name__}: {e}"[:300])
                log.error("%-18s ÉCHEC %s", club.id, e)
                log.debug(traceback.format_exc())

    par_plateforme = defaultdict(list)
    par_telephone = []
    for c in clubs:
        if c.via_telephone:
            par_telephone.append(c)
        else:
            par_plateforme[c.plateforme].append(c)
    if envoi:
        # Les clubs iPhone sont relus à partir des réponses envoyées, sans aucune requête d'ici.
        traiter(par_telephone, ClientRejoue(envoi["reponses"]), [date.fromisoformat(j) for j in envoi["jours"]])
    with ThreadPoolExecutor(max_workers=len(par_plateforme) or 1) as pool:
        # un client par plateforme : pauses respectées site par site
        list(pool.map(lambda g: traiter(g, Client(), jours), par_plateforme.values()))

    sortie_clubs, sortie_creneaux = [], []
    for club in tous:
        ancien = etat_precedent.get(club.id, {})
        via = "telephone" if club.via_telephone else None
        if club.id not in resultats:
            # Club non demandé (--clubs), ou club iPhone sans envoi : on reprend l'état précédent.
            if ancien or via:
                base = ancien or {"plateforme": club.plateforme, "statut": "attente",
                                  "derniere_maj_ok": None, "derniere_tentative": None, "erreur": None}
                sortie_clubs.append({**base, "id": club.id, "nom": club.nom, "commune": club.commune,
                                     "via": via, "nb_creneaux": len(creneaux_precedents.get(club.id, []))})
                sortie_creneaux += creneaux_precedents.get(club.id, [])
            continue
        statut, cr, erreur = resultats[club.id]
        if statut == "ok":
            lignes = [c.en_dict() for c in cr]
            maj = date_envoi if via else horodatage
        else:
            # On garde les derniers créneaux connus encore à venir ; la page les signale comme anciens.
            lignes = creneaux_precedents.get(club.id, [])
            maj = ancien.get("derniere_maj_ok")
        sortie_creneaux += lignes
        sortie_clubs.append({
            "id": club.id,
            "nom": club.nom,
            "commune": club.commune,
            "plateforme": club.plateforme,
            "via": via,
            "statut": statut,
            "derniere_maj_ok": maj,
            "derniere_tentative": horodatage,
            "erreur": erreur,
            "nb_creneaux": len(lignes),
        })

    # Logo du club s'il a été téléchargé (outils/logos.py) ; sinon la page affiche ses initiales.
    for c in sortie_clubs:
        c["logo"] = f"logos/{c['id']}.png" if (RACINE / "docs" / "logos" / f"{c['id']}.png").exists() else None

    liens, lignes = encoder(sortie_creneaux)
    donnees = {"version": 2, "genere_le": horodatage, "jours": [j.isoformat() for j in jours],
               "clubs": sortie_clubs, "colonnes": COLONNES, "liens": liens, "creneaux": lignes}

    nb_ok = sum(1 for s, _, _ in resultats.values() if s == "ok")
    log.info("%d/%d clubs actualisés, %d créneaux au total", nb_ok, len(resultats), len(sortie_creneaux))

    if args.apercu:
        for c in sortie_creneaux[:15]:
            print(c)
    else:
        args.sortie.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.sortie.with_suffix(".tmp")
        tmp.write_text(json.dumps(donnees, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, args.sortie)
        log.info("écrit : %s (%d Ko)", args.sortie, args.sortie.stat().st_size // 1024)
        ecrire_requetes_telephone(args.sortie.parent / "telephone-requetes.json", tous, jours, horodatage)

    # Échec du processus seulement si aucun club interrogé n'a pu être actualisé.
    return 0 if nb_ok or not resultats else 1


if __name__ == "__main__":
    sys.exit(main())
