"""Client HTTP discret : pauses entre requêtes, en-têtes de navigateur, une reprise."""

from __future__ import annotations

import gzip
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

PAUSE_MIN = 1.5   # secondes entre deux requêtes
PAUSE_MAX = 3.5
DELAI_MAX = 25    # délai d'attente d'une réponse


class ErreurHttp(Exception):
    pass


def construire_url(url: str, params=None) -> str:
    """Adresse complète d'une requête. Sert aussi à retrouver une réponse envoyée par l'iPhone."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True, safe=":[]")
    return url


class Client:
    def __init__(self, pause=(PAUSE_MIN, PAUSE_MAX)):
        self.pause = pause
        self._dernier_appel = 0.0

    def _attendre(self):
        attente = random.uniform(*self.pause) - (time.monotonic() - self._dernier_appel)
        if attente > 0:
            time.sleep(attente)
        self._dernier_appel = time.monotonic()

    def get(self, url: str, params=None, entetes=None) -> bytes:
        url = construire_url(url, params)
        h = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-BE,fr;q=0.9,en;q=0.7",
            "Accept-Encoding": "gzip",
        }
        h.update(entetes or {})
        for essai in (1, 2):
            self._attendre()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=DELAI_MAX) as r:
                    corps = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        corps = gzip.decompress(corps)
                    return corps
            except urllib.error.HTTPError as e:
                if essai == 1 and (e.code == 429 or e.code >= 500):
                    time.sleep(10)
                    continue
                raise ErreurHttp(f"HTTP {e.code} sur {url}") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if essai == 1:
                    time.sleep(5)
                    continue
                raise ErreurHttp(f"{type(e).__name__} sur {url} : {e}") from e
        raise ErreurHttp(f"échec sur {url}")

    def get_json(self, url: str, params=None, entetes=None):
        corps = self.get(url, params, entetes)
        try:
            return json.loads(corps)
        except ValueError as e:
            raise ErreurHttp(f"réponse non JSON sur {url} : {corps[:120]!r}") from e

    def get_texte(self, url: str, params=None, entetes=None) -> str:
        return self.get(url, params, entetes).decode("utf-8", errors="replace")


class ClientRejoue:
    """Répond à partir de réponses déjà récupérées ailleurs (par le raccourci iPhone), sans réseau."""

    rejoue = True

    def __init__(self, reponses: dict[str, str]):
        self.reponses = reponses

    def get_texte(self, url: str, params=None, entetes=None) -> str:
        cle = construire_url(url, params)
        if cle not in self.reponses:
            raise ErreurHttp(f"réponse absente de l'envoi iPhone : {cle}")
        return self.reponses[cle]

    def get_json(self, url: str, params=None, entetes=None):
        texte = self.get_texte(url, params, entetes)
        try:
            return json.loads(texte)
        except ValueError as e:
            raise ErreurHttp(f"réponse non JSON dans l'envoi iPhone : {texte[:120]!r}") from e
