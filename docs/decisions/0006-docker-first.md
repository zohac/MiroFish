# 0006 — Docker d'abord : un seul environnement de référence

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

Le dépôt amont fournit une image unique (`Dockerfile` : `python:3.11`, `uv`,
`npm ci`, un seul conteneur qui lance le backend et le frontend) et un
`docker-compose.yml` d'un seul service.

En parallèle, le développement local utilise un venv `uv` dans
`backend/.venv` plus `node_modules`. Cela crée **deux environnements** qui ne
peuvent pas ne pas diverger : versions de dépendances, lock, versions de
Node, résolutions de modules.

Le besoin est simple : un environnement **reproductible en permanence**, pas
« reproductible si on pense à installer les mêmes choses ».

Contrainte à ne pas oublier : les ports 3000 et 3001 sont déjà occupés par des
conteneurs d'un autre projet.

## Décision

**Si Docker est disponible, c'est l'environnement de référence.** Toute
commande passe par `docker compose`.

Le mode sans Docker reste possible — dépannage, boucle rapide — mais il est
**explicite**, et on ne mélange pas les deux dans une même session.

Règles associées :

- Le code est monté en volume en développement ; l'image reste la référence
  des dépendances (`uv sync --frozen`).
- Les données persistantes vivent dans des **volumes nommés** (Neo4j), jamais
  dans le cycle de vie d'un conteneur.
- Les secrets arrivent par `env_file: .env` — **jamais** `COPY .env` dans
  l'image.
- `docker compose down` sans `-v` conserve les données ; **`down -v` détruit
  le graphe** et ne doit être lancé que sciemment.
- Aucune modification manuelle d'un conteneur ou d'une image : tout passe par
  les fichiers du dépôt.

## Conséquences

**Positives**

- Un seul endroit où les versions sont figées : l'image et le lock.
- La CI peut construire la même image que le poste local (étape suivante :
  epic 005).
- Le mot de passe Neo4j et les identifiants restent hors du dépôt.

**Négatives**

- Tant que l'image amont reste en mode dev (`CMD pnpm run dev`) et que le
  compose ne contient pas Neo4j, **le compose n'est pas encore la
  référence** : cette décision ne devient exécutable qu'à l'epic 005.
- Point plus fin, et facile à rater : le `docker-compose.yml` pointe
  aujourd'hui `image: ghcr.io/666ghj/mirofish:latest`, c'est-à-dire l'**image
  amont**. Elle ne contient aucune de nos modifications. Il faudra passer à
  `build: .` pour que Docker soit réellement notre environnement de référence.
- Les volumes montés sur macOS sont lents, et le projet embarque `torch` —
  à mesurer.
- Le build est plus lent qu'un `pytest` local.

## Alternatives rejetées

- **Local comme référence, Docker pour la livraison** — c'est l'état actuel :
  deux environnements, divergence garantie.
- **Entretenir les deux en parallèle** — le coût est doublé et la divergence
  n'est jamais rattrapée.
- **Nix ou `devenv`** — Trop lourd pour le gain attendu ici, et l'écart avec
  un fichier `Dockerfile` déjà fourni par l'amont n'est pas justifié.
- **Docker ignoré au profit d'un gestionnaire de versions** — le lock est déjà
  la bonne réponse au niveau Python ; le problème vient du reste (Node,
  services), pas de Python.