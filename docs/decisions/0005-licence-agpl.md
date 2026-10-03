# 0005 — Licence : rester local ; exposer en réseau implique de publier les sources

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

MiroFish est sous **AGPL-3.0** (`LICENSE`, confirmé par
`pyproject.toml`). Graphiti est Apache-2.0 — permissive, donc sans
incompatibilité.

La section 13 de l'AGPL impose de mettre le code source complet à disposition
des autres utilisateurs lorsqu'on exécute une version **modifiée** en **mode
réseau**. Les trois conditions sont **cumulatives** : modifié + réseau + autres
utilisateurs. En usage strictement local, la clause ne se déclenche jamais.

Or MiroFish est un moteur de prédiction d'opinion : le genre d'outil qu'on a
envie d'exposer en démo sur un VPS ou un LAN. C'est exactement le cas qui
déclenche la clause.

## Décision

**Usage local par défaut.** Aucune exposition réseau tant que la publication
des sources n'a pas été décidée explicitement.

Si une exposition a lieu : le code reste AGPL et les sources sont publiées.
Un fork **reste obligatoirement AGPL** — il ne peut pas être repasser en MIT
ni fermé.

## Conséquences

**Positives**

- Aucun impératif juridique sur le travail en cours : usage, modification,
  fork personnel sans obligation.
- Les décisions restent publiques par défaut (le dépôt est déjà public).

**Négatives**

- Une démo publique = une publication du code. Il faut le décider avant, pas
  après.
- Aucun chemin vers une licence plus permissive sans repartir d'une base
  compatible.

## Alternatives rejetées

- **Repasser le fork en MIT** — impossible : c'est une violation de l'AGPL, et
  l'amont est AGPL.
- **Garder un fork fermé** — illégal sous AGPL dès qu'il est exposé en réseau.