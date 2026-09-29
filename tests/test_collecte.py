"""Tests de la collecte : format du fichier publié et résistance aux pannes."""

import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from collecteur import __main__ as collecte
from collecteur.modele import FUSEAU, Creneau


def faux_creneau(club, jour, heure="21:00"):
    return Creneau(club=club, terrain="P1", date=jour.isoformat(), heure=heure, duree_min=90,
                   prix_eur=40.0, interieur=True, lien=f"https://{club}.exemple.be")


class Format(unittest.TestCase):
    def test_aller_retour(self):
        demain = (datetime.now(FUSEAU) + timedelta(days=1)).date()
        creneaux = [faux_creneau("a", demain).en_dict(), faux_creneau("a", demain, "22:00").en_dict(),
                    faux_creneau("b", demain).en_dict()]
        liens, lignes = collecte.encoder(creneaux)
        self.assertEqual(len(liens), 2)  # liens mis en commun
        self.assertEqual(collecte.decoder({"liens": liens, "creneaux": lignes}), creneaux)


class Pannes(unittest.TestCase):
    def lancer(self, dossier, plateformes):
        clubs = [collecte.Club("ok", "Club OK", "Liège", "fausse_ok", {}),
                 collecte.Club("ko", "Club KO", "Liège", "fausse_ko", {})]
        sortie = Path(dossier) / "creneaux.json"
        with mock.patch.object(collecte, "lire_clubs", return_value=clubs), \
             mock.patch.dict(collecte.PLATEFORMES, plateformes):
            code = collecte.main(["--sortie", str(sortie), "--jours", "2"])
        return code, json.loads(sortie.read_text(encoding="utf-8"))

    def test_une_panne_ne_vide_pas_la_page(self):
        demain = (datetime.now(FUSEAU) + timedelta(days=1)).date()
        ok = types.SimpleNamespace(collecter=lambda club, jours, client: [faux_creneau(club.id, demain)])

        def panne(club, jours, client):
            raise ConnectionError("site injoignable")
        ko = types.SimpleNamespace(collecter=panne)

        with tempfile.TemporaryDirectory() as d:
            # 1er passage : les deux clubs répondent.
            code, donnees = self.lancer(d, {"fausse_ok": ok, "fausse_ko": ok})
            self.assertEqual(code, 0)
            maj_ko = next(c for c in donnees["clubs"] if c["id"] == "ko")["derniere_maj_ok"]

            # 2e passage : le club « ko » tombe en panne.
            code, donnees = self.lancer(d, {"fausse_ok": ok, "fausse_ko": types.SimpleNamespace(collecter=panne)})
            self.assertEqual(code, 0)
            etats = {c["id"]: c for c in donnees["clubs"]}
            self.assertEqual(etats["ok"]["statut"], "ok")
            self.assertEqual(etats["ko"]["statut"], "erreur")
            self.assertIn("site injoignable", etats["ko"]["erreur"])
            self.assertEqual(etats["ko"]["derniere_maj_ok"], maj_ko)  # heure de la dernière réussite
            clubs_avec_creneaux = {c["club"] for c in collecte.decoder(donnees)}
            self.assertEqual(clubs_avec_creneaux, {"ok", "ko"})  # anciens créneaux conservés

            # Si tout échoue, le processus le signale (l'Action passe en rouge).
            code, _ = self.lancer(d, {"fausse_ok": types.SimpleNamespace(collecter=panne),
                                      "fausse_ko": types.SimpleNamespace(collecter=panne)})
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
