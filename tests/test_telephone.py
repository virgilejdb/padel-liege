"""Mode iPhone : les adresses publiées pour le raccourci doivent correspondre exactement
à celles que les adaptateurs relisent ensuite dans l'envoi."""

import json
import unittest
from datetime import date, datetime
from pathlib import Path

from collecteur.__main__ import Club, collecter_club, lire_clubs
from collecteur.http import ClientRejoue
from collecteur.modele import FUSEAU
from collecteur.plateformes import PLATEFORMES, matchi, playtomic, sportfinder

ECH = Path(__file__).parent / "echantillons"
AVANT = datetime(2026, 9, 29, 0, 0, tzinfo=FUSEAU)  # avant les créneaux des échantillons


def lire(nom):
    return (ECH / nom).read_text(encoding="utf-8")


class Rejeu(unittest.TestCase):
    def rejouer(self, club, jour, reponses_par_ordre):
        urls = PLATEFORMES[club.plateforme].requetes(club, [jour])
        self.assertEqual(len(urls), len(reponses_par_ordre))
        client = ClientRejoue(dict(zip(urls, reponses_par_ordre)))
        return collecter_club(club, [jour], client, AVANT)

    def test_playtomic_avec_terrains_connus(self):
        club = Club("awans", "Awans", "Awans", "playtomic",
                    {"tenant": "6b99ad95-24cb-41e6-8e02-aeac1f365a7f", "slug": "padel-square-awans"})
        self.assertTrue(playtomic.terrains_connus(club.params["tenant"]), "config/terrains_playtomic.json incomplet")
        cr = self.rejouer(club, date(2026, 9, 30), [lire("playtomic_availability.json")])
        self.assertTrue(cr)
        self.assertTrue(all(c.terrain.startswith("Awans T") for c in cr))

    def test_sportfinder(self):
        club = Club("baudouin", "Baudouin", "Liège", "sportfinder",
                    {"produit": "190", "centre": "19051", "slug": "royal-baudouin-tennis-padel-club"})
        cr = self.rejouer(club, date(2026, 10, 1),
                          [lire("sportfinder_fields.json"), lire("sportfinder_availabilities.json")])
        self.assertTrue(cr)
        self.assertEqual({c.terrain for c in cr} - {"P1", "P2"}, set())

    def test_matchi_espaces_reduits(self):
        # Le raccourci remplace les suites d'espaces par un seul espace avant l'envoi.
        import re
        club = Club("goose", "Goose", "Visé", "matchi", {"facility": "1252", "slug": "goosepadelvise"})
        html = re.sub(r"\s+", " ", lire("matchi_slots.html"))
        cr = self.rejouer(club, date(2026, 10, 1), [html])
        self.assertTrue(cr)

    def test_reponse_manquante(self):
        club = Club("goose", "Goose", "Visé", "matchi", {"facility": "1252", "slug": "goosepadelvise"})
        with self.assertRaises(Exception):
            collecter_club(club, [date(2026, 10, 1)], ClientRejoue({}), AVANT)

    def test_clubs_iphone_ont_une_liste_d_adresses(self):
        for club in lire_clubs():
            if club.via_telephone:
                with self.subTest(club=club.id):
                    module = PLATEFORMES[club.plateforme]
                    self.assertTrue(hasattr(module, "requetes"), f"{club.plateforme} sans requetes()")
                    self.assertTrue(module.requetes(club, [date(2026, 10, 1)]))
                    if club.plateforme == "playtomic":
                        self.assertTrue(playtomic.terrains_connus(club.params["tenant"]),
                                        "lancer outils/terrains_playtomic.py")


class FormatsEnvoi(unittest.TestCase):
    """L'action « Créer une archive » de Raccourcis peut produire plusieurs formats."""

    ENVOI = {"jours": ["2026-10-01"], "reponses": {"https://exemple.be/a": "b"}}

    def lire(self, contenu: bytes):
        import tempfile
        from collecteur.__main__ import lire_envoi_telephone
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "envoi.gz"
            p.write_bytes(contenu)
            return lire_envoi_telephone(p)

    def test_formats(self):
        import gzip, io, tarfile, zipfile
        texte = json.dumps(self.ENVOI).encode()
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode="w:gz") as t:
            info = tarfile.TarInfo("Texte.txt"); info.size = len(texte)
            t.addfile(info, io.BytesIO(texte))
        zp = io.BytesIO()
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("Texte.txt", texte)
        for nom, contenu in [("json", texte), ("gz", gzip.compress(texte)), ("tar.gz", tar.getvalue()),
                             ("zip", zp.getvalue()), ("bom", b"\xef\xbb\xbf" + texte)]:
            with self.subTest(format=nom):
                self.assertEqual(self.lire(contenu), self.ENVOI)

    def test_envoi_vide_ignore(self):
        import gzip
        self.assertIsNone(self.lire(gzip.compress(b"{}")))


if __name__ == "__main__":
    unittest.main()
