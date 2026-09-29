"""Met à jour config/terrains_playtomic.json (noms des terrains Playtomic, utilisés en mode iPhone).

À lancer depuis votre ordinateur (Playtomic refuse les serveurs de GitHub), quand un club
change ses terrains, puis commitez le fichier :

    py outils/terrains_playtomic.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collecteur.__main__ import lire_clubs  # noqa: E402
from collecteur.http import Client  # noqa: E402
from collecteur.plateformes import playtomic  # noqa: E402


def main():
    client = Client()
    resultat = {}
    for club in lire_clubs():
        if club.plateforme != "playtomic":
            continue
        html = client.get_texte(f"{playtomic.SITE}/fr/clubs/{club.params['slug']}",
                                entetes={"Accept": "text/html,application/xhtml+xml"})
        terrains = playtomic.lire_terrains(html)
        if not terrains:
            raise SystemExit(f"{club.id} : aucun terrain trouvé, fichier non modifié")
        resultat[club.params["tenant"]] = {rid: {"nom": nom, "interieur": interieur}
                                           for rid, (nom, interieur) in terrains.items()}
        print(f"{club.id:12} {len(terrains)} terrains")
    playtomic.TERRAINS_CONNUS.write_text(json.dumps(resultat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("écrit :", playtomic.TERRAINS_CONNUS)


if __name__ == "__main__":
    main()
