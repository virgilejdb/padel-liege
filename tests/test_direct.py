"""Test en direct : interroge un vrai club par plateforme (2 jours) et valide le format.

Désactivé par défaut pour rester discret. Pour le lancer :
    PADEL_DIRECT=1 python -m unittest tests.test_direct -v
"""

import os
import unittest
from datetime import datetime, timedelta

from collecteur.__main__ import collecter_club, lire_clubs
from collecteur.http import Client
from collecteur.modele import FUSEAU

UN_CLUB_PAR_PLATEFORME = {}
for _c in lire_clubs():
    UN_CLUB_PAR_PLATEFORME.setdefault(_c.plateforme, _c)


@unittest.skipUnless(os.environ.get("PADEL_DIRECT") == "1", "PADEL_DIRECT=1 pour interroger les vrais sites")
class Direct(unittest.TestCase):
    def test_une_collecte_par_plateforme(self):
        maintenant = datetime.now(FUSEAU)
        jours = [(maintenant + timedelta(days=i)).date() for i in (1, 2)]
        for plateforme, club in UN_CLUB_PAR_PLATEFORME.items():
            with self.subTest(plateforme=plateforme, club=club.id):
                cr = collecter_club(club, jours, Client(), maintenant)  # lève une erreur si format invalide
                self.assertGreater(len(cr), 0, "aucun créneau sur 2 jours : à vérifier à la main")


if __name__ == "__main__":
    unittest.main()
