# Padel Liège

Tous les créneaux de padel libres des clubs autour de Liège, sur les 7 prochains jours, sur une seule page pensée pour le téléphone.

- La collecte (Python, bibliothèque standard uniquement) interroge chaque plateforme de réservation.
- Une GitHub Action la relance toutes les 30 minutes et publie la page et les données sur GitHub Pages.
- Aucun serveur, aucune base de données, aucun identifiant : seules des pages publiques sont lues.

## Clubs couverts

25 clubs sur 6 plateformes :

| Plateforme | Clubs |
|---|---|
| Doinsport | Bayards, Squash 22, RTC Cointe, Padel Passion (Herstal, Juprelle, Engis), Planet Padel (Ans, Saint-Georges), Padel Flémalle, Seraing TC, TPC Neupré, Just Padel, TC Trooz, Padel Tultay |
| Playtomic | Garrincha Wandre, Addict Padel Liers, Padel Square Awans, Beaufays |
| Sport-finder | Royal Baudouin, RTPC Grâce, Trenta Padel |
| Anybuddy | Chênée, Horizon Padel Fléron |
| MATCHi | Goose Padel Visé |
| Big Captain | TPC Embourg |

Non couverts, faute de réservation en ligne lisible sans compte : RTC Liège (padel « bientôt disponible »), Royal Fayenbois, Elite Soccer & Padel, Tennissimo, TPC Haut-Clocher.

## Utiliser la page

Ouvrez l'adresse GitHub Pages du dépôt sur le téléphone, puis ajoutez-la à l'écran d'accueil :

- iPhone (Safari) : bouton Partager, puis « Sur l'écran d'accueil ».
- Android (Chrome) : menu ⋮, puis « Ajouter à l'écran d'accueil ».

En haut, la pastille indique l'état des données. Elle passe en orange si un club n'a pas pu être actualisé ou si la dernière collecte date de plus de 90 minutes. Touchez-la pour voir le détail club par club. Les créneaux d'un club en panne restent affichés, avec la mention « Pas actualisé depuis… ».

Touchez une heure pour voir les terrains, les durées et les prix, puis « Réserver ». Le lien ouvre le planning du club, à la bonne date pour Playtomic et MATCHi. Sur les autres plateformes, il faut choisir le jour sur place.

## Organisation

```
config/clubs.csv            un club par ligne
collecteur/
  __main__.py               collecte de tous les clubs, écriture du JSON
  modele.py                 format commun d'un créneau et sa validation
  http.py                   client HTTP discret (pauses, en-têtes, une reprise)
  plateformes/<nom>.py      un adaptateur par plateforme
docs/                       la page publiée (index.html, manifeste, icônes)
docs/data/creneaux.json     produit par la collecte, jamais commité
tests/                      tests du format sur de vraies réponses enregistrées
outils/local.py             variante locale (collecte et page sur votre ordinateur)
.github/workflows/          collecte planifiée et maintien de la planification
```

Chaque adaptateur renvoie des créneaux au format commun : club, terrain, date, heure de début, durée, prix, intérieur ou extérieur (si connu) et lien de réservation.

## Ajouter un club

Si sa plateforme est déjà gérée, ajoutez une ligne à `config/clubs.csv` :

```
id,nom,commune,plateforme,parametres
mon-club,Mon Club,Liège,playtomic,tenant=<uuid>;slug=<slug>
```

- `id` : court, unique, sans espace.
- `parametres` : couples `clé=valeur` séparés par `;`. Les clés attendues figurent en tête de chaque fichier `collecteur/plateformes/<nom>.py` (variable `PARAMETRES`).
- Option valable partout : `interieur=oui` ou `interieur=non`, utilisée quand la plateforme ne le précise pas.

Où trouver les identifiants :

| Plateforme | Paramètres | Où les trouver |
|---|---|---|
| doinsport | `club`, `activites`, `site` | `site` = sous-domaine (`<site>.doinsport.club`). Ouvrez la page du club, onglet Réseau des outils de développement : `club` est l'UUID de la requête `/clubs/<uuid>`, et `activites` celui de `activities.id` dans la requête `plannings`. Plusieurs activités se séparent par `+`. Vérifiez le nom du club : un sous-domaine inconnu affiche un autre club. |
| playtomic | `tenant`, `slug` | `slug` = fin de l'URL `playtomic.com/fr/clubs/<slug>`. `tenant` = `tenant_id` dans la requête `api/clubs/availability`. |
| sportfinder | `produit`, `centre`, `slug` | `produit` dans l'URL `.../booking/field_rental/<produit>/book`. `centre` dans la requête `api/fields?center=...`. |
| anybuddy | `slug` | URL `anybuddyapp.com/fr-be/club/<slug>/padel`. |
| matchi | `facility`, `slug` | `slug` dans l'URL `matchi.se/facilities/<slug>`, `facility` dans la requête `book/listSlots`. |
| bigcaptain | `tenant`, `alias`, `discipline`, `durees` | `alias` dans l'URL `my.big-captain.com/site/<alias>`. Les autres dans les requêtes `api-mobile/v1/<tenant>/bookings/...`. |

Testez ensuite le club seul, sans toucher au fichier publié :

```
python -m collecteur --clubs mon-club --apercu
```

## Ajouter une plateforme

1. Créez `collecteur/plateformes/<nom>.py` avec :
   - `PARAMETRES` : les clés attendues dans `clubs.csv` ;
   - `collecter(club, jours, client)` : renvoie une liste de `Creneau` (voir `modele.py`). Passez toujours par `client.get_json` ou `client.get_texte`, qui espacent les requêtes.
   - Isolez la lecture de la réponse dans une fonction `interpreter(...)`, pour pouvoir la tester sans réseau.
2. Déclarez le module dans `collecteur/plateformes/__init__.py`.
3. Enregistrez une vraie réponse réduite dans `tests/echantillons/` et ajoutez un test dans `tests/test_format.py`.
4. Ajoutez le nom de la plateforme dans `PLATEFORMES` en haut du script de `docs/index.html` (nom affiché sur le bouton « Réserver »).

Heures : le format commun attend l'heure locale de Bruxelles. Convertissez si la plateforme répond en UTC (c'est le cas de Playtomic et MATCHi).

## Relancer la collecte à la main

Sur GitHub : onglet **Actions**, workflow **Collecte des créneaux**, bouton **Run workflow**. La page est à jour environ 6 minutes plus tard.

Sur votre ordinateur (Python 3.10 ou plus récent) :

```
python -m collecteur                      tous les clubs, écrit docs/data/creneaux.json
python -m collecteur --clubs bayards      un ou plusieurs clubs, séparés par des virgules
python -m collecteur --jours 2 --apercu   affiche un aperçu sans rien écrire
```

Sous Windows, remplacez `python` par `py`, et installez une fois la base des fuseaux horaires : `py -m pip install tzdata`.

## Tests

```
python -m unittest discover -s tests -t . -v
```

Ils vérifient, sur de vraies réponses enregistrées, que chaque adaptateur produit des créneaux au format commun, qu'un club en panne garde ses derniers créneaux sans vider la page, et que chaque ligne de `clubs.csv` a ses paramètres. L'Action les lance avant chaque collecte.

Pour vérifier les vrais sites (un club par plateforme, 2 jours) :

```
PADEL_DIRECT=1 python -m unittest tests.test_direct -v
```

En production, un site qui change de structure fait passer son club en erreur (pastille orange sur la page, détail de l'erreur dans le journal de l'Action), au lieu d'afficher des données fausses.

## Discrétion envers les sites

- Une requête toutes les 1,5 à 3,5 secondes par site. Les plateformes sont interrogées en parallèle, mais jamais deux requêtes à la fois vers le même site.
- En-têtes d'un navigateur ordinaire, une seule reprise en cas d'erreur, puis abandon jusqu'à la collecte suivante.
- Environ 190 requêtes par collecte pour 25 clubs, toutes les 30 minutes, dont 110 vers Doinsport (7 jours pour 14 clubs).

## Variante locale

Si une plateforme bloque les requêtes venant des serveurs de GitHub (ses clubs restent en erreur sur la page), la collecte peut tourner sur votre ordinateur avec la même page :

```
python outils/local.py
```

La commande collecte toutes les 30 minutes et sert la page sur `http://<adresse de l'ordinateur>:8000`, consultable depuis le téléphone connecté au même Wi-Fi. L'ordinateur doit rester allumé.

## Limites connues

- Anybuddy est un agrégateur : ses données peuvent avoir un léger retard sur le logiciel du club (Chênée, Fléron).
- MATCHi et Big Captain ne donnent pas les prix sans compte.
- Doinsport et Sport-finder ne permettent pas de passer la date dans le lien de réservation.
- GitHub ne garantit pas l'heure exacte des tâches planifiées : un retard de 5 à 15 minutes est courant.
