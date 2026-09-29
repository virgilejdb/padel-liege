"""Tests hors ligne : chaque adaptateur, appliqué à une vraie réponse enregistrée,
doit produire des créneaux au format commun.

    python -m unittest discover -s tests -v
"""

import json
import unittest
from datetime import date
from pathlib import Path

from collecteur.__main__ import lire_clubs
from collecteur.modele import Creneau, nettoyer_nom, valider
from collecteur.plateformes import PLATEFORMES, anybuddy, bigcaptain, doinsport, matchi, playtomic, sportfinder

ECH = Path(__file__).parent / "echantillons"


def lire(nom):
    texte = (ECH / nom).read_text(encoding="utf-8")
    return json.loads(texte) if nom.endswith(".json") else texte


class FormatCommun(unittest.TestCase):
    def verifier(self, creneaux, minimum=1):
        self.assertGreaterEqual(len(creneaux), minimum, "aucun créneau extrait : structure changée ?")
        for c in creneaux:
            self.assertIsInstance(c, Creneau)
            self.assertEqual(valider(c), [], c)

    def test_doinsport(self):
        cr = doinsport.interpreter(lire("doinsport_planning.json"), "x", date(2026, 10, 1), "https://exemple.be")
        self.verifier(cr)
        self.assertTrue(all(c.date == "2026-10-01" for c in cr))
        # Prix total du terrain = prix par joueur x nombre de joueurs, en euros.
        self.assertTrue(all(c.prix_eur and c.prix_eur >= 5 for c in cr))

    def test_playtomic_conversion_utc(self):
        terrains = playtomic.lire_terrains(lire("playtomic_page.html"))
        self.assertEqual(len(terrains), 6)
        self.assertEqual(terrains["f5753e99-bb43-437f-a9cf-05ec678b616e"], ("Awans T1 - Double", True))
        cr = playtomic.interpreter(lire("playtomic_availability.json"), "awans", "padel-square-awans", terrains)
        self.verifier(cr)
        # 04:00 UTC le 30/09 = 06:00 à Bruxelles (heure d'été).
        self.assertIn("06:00", {c.heure for c in cr})
        self.assertTrue(all(c.lien.endswith("?date=" + c.date) for c in cr))

    def test_playtomic_nom_avec_barre(self):
        html = r'{\"resourceId\":\"a\",\"name\":\"Terrain 3 | À la recherche\",\"sport\":\"PADEL\",\"features\":[\"outdoor\"]}'
        self.assertEqual(playtomic.lire_terrains(html), {"a": ("Terrain 3", False)})

    def test_sportfinder(self):
        terrains = sportfinder.lire_terrains(lire("sportfinder_fields.json"))
        self.assertEqual(terrains[392], ("P1", False))
        cr = sportfinder.interpreter(lire("sportfinder_availabilities.json"), "baudouin", terrains, "https://exemple.be")
        self.verifier(cr)

    def test_anybuddy(self):
        terrains = anybuddy.lire_terrains(lire("anybuddy_page.html"))
        self.assertEqual(sorted(n for n, _ in terrains.values()), ["Court 1", "Court 2", "Court 3"])
        cr = anybuddy.interpreter(lire("anybuddy_availabilities.json"), "chenee", terrains, "https://exemple.be")
        self.verifier(cr)
        self.assertFalse(any(c.terrain.startswith("Terrain ") for c in cr), "service inconnu de la page club")

    def test_matchi(self):
        cr = matchi.interpreter(lire("matchi_slots.html"), "goose", "goosepadelvise")
        self.verifier(cr)
        exterieur = [c for c in cr if c.terrain == "Extérieur"]
        self.assertTrue(exterieur and all(c.interieur is False for c in exterieur))
        self.assertTrue(all(c.duree_min == 90 for c in cr))

    def test_bigcaptain_terrains_libres_seulement(self):
        terrains = {5963: "Padel 1", 5964: "Padel 2", 5965: "Padel 3"}
        rep = lire("bigcaptain_slots.json")
        cr = bigcaptain.interpreter(rep, "embourg", terrains, 90, "https://exemple.be")
        self.verifier(cr)
        attendu = sum(len(s["resources"]) for s in rep["data"] if s["canBeBooked"] and s["numOfAvailabilites"])
        self.assertEqual(len(cr), attendu)


class Validation(unittest.TestCase):
    BON = dict(club="c", terrain="P1", date="2026-10-01", heure="09:00", duree_min=90,
               prix_eur=40.0, interieur=True, lien="https://exemple.be")

    def test_creneau_correct(self):
        self.assertEqual(valider(Creneau(**self.BON)), [])

    def test_creneaux_incorrects(self):
        for champ, valeur in [("heure", "9h"), ("date", "01/10/2026"), ("duree_min", 0),
                              ("prix_eur", -3), ("interieur", "oui"), ("lien", "ftp://x"), ("terrain", " ")]:
            with self.subTest(champ=champ):
                self.assertNotEqual(valider(Creneau(**{**self.BON, champ: valeur})), [])

    def test_nettoyer_nom(self):
        self.assertEqual(nettoyer_nom("Mghoghi P\\u0026amp;V  "), "Mghoghi P&V")


class Configuration(unittest.TestCase):
    def test_chaque_club_a_une_plateforme_et_ses_parametres(self):
        clubs = lire_clubs()
        self.assertGreater(len(clubs), 0)
        for club in clubs:
            with self.subTest(club=club.id):
                self.assertIn(club.plateforme, PLATEFORMES)
                manquants = set(PLATEFORMES[club.plateforme].PARAMETRES) - set(club.params)
                self.assertFalse(manquants, f"paramètres manquants : {manquants}")


if __name__ == "__main__":
    unittest.main()
