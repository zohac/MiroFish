# Epic 005 — Environnement Docker de référence (Docker-first)

- **Statut** : `in-progress` · **Dépend de** : 001, 002, 003, 004 · **Bloque** : 006, 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'Epic 001 a prouvé la faisabilité de la chaîne Graphiti + Neo4j 5.26 + OpenCode Go en conteneur isolé.  
> L'Epic 002 a isolé MiroFish derrière l'interface `GraphStore` (470 tests verts).  
> L'Epic 003 a concrétisé le backend local `GraphitiGraphStore`, validé le chemin de lecture et réussi l'épreuve d'intégration réelle Neo4j (562 tests verts).  
> L'Epic 004 a franchi le pas de la bascule local-first complète sans Zep Cloud (632 tests verts).  
>
> **L'Epic 005 concrétise l'ADR 0006 (« Docker d'abord : un seul environnement de référence »)** : il unifie l'application complète (Neo4j, Backend Flask, Frontend Vue) au sein d'une configuration Docker Compose reproductible, autonome, prête pour la production et pour le développement.

**Artefacts de ce dossier** — [`prd.md`](prd.md) (quoi, pourquoi, critères chiffrés) ·
[`architecture.md`](architecture.md) (comment, modèles et flux de données) · ce fichier (le contrat
d'ingénierie) · `story-005-<n>.md` (une story démarrée = un fichier markdown).

---

## Le problème en une phrase

L'application MiroFish dispose aujourd'hui d'un `docker-compose.yml` qui pointe sur l'image amont obsolète sans nos modifications, sans Neo4j, et force le développement sur l'environnement de l'hôte, créant une dualité source de dérive alors que l'ADR 0006 et la constitution exigent que Docker soit l'environnement de référence unique et reproductible.

---

## Objectif

1. Définir des `Dockerfile` reproductibles pour le `backend` (Python 3.11, `uv sync --locked`) et le `frontend` (Node 20, `pnpm install --frozen-lockfile`) construits à partir de notre code source du fork `local-first`.
2. Absorber `docker-compose.neo4j.yml` dans un `docker-compose.yml` unique unifié orchestrant les 3 services (`neo4j`, `backend`, `frontend`) sur un réseau dédié avec healthchecks et volume nommé persistant `neo4j_data`.
3. Valider l'exécution intégrale du filet de 632 tests dans le conteneur de référence (`docker compose run --rm backend uv run pytest tests/ -q`).
4. Vérifier la persistance des données et graphes après redémarrage des conteneurs (`docker compose down && docker compose up -d`).
5. Livrer un banc de qualification Docker validant le flux e2e complet conteneurisé et 0 secret dans les images.

---

## Exigences fonctionnelles

| # | Exigence |
|---|---|
| FR-1 | Découpage des Dockerfiles : images spécialisées pour le backend (`python:3.11-slim`, `uv:0.9.26`) et le frontend (`node:20-slim`, `pnpm`), avec mise en cache optimisée des couches de dépendances. |
| FR-2 | Compose unifié multi-services : `docker-compose.yml` orchestrant `neo4j`, `backend` et `frontend` sur le réseau `mirofish_network`. |
| FR-3 | Absorption de Neo4j : intégration de `neo4j:5.26.31-community` avec healthcheck Bolt (`cypher-shell`), volume persistant `neo4j_data` et mot de passe extrait de `.env`. |
| FR-4 | Ordonnancement conditionnel : démarrage du `backend` subordonné à l'état `healthy` de `neo4j`, et démarrage du `frontend` subordonné à l'état `healthy` du `backend`. |
| FR-5 | Résolution réseau et variables : résolution interne `bolt://neo4j:7687` pour le backend et `http://backend:5001` pour le frontend, tout en maintenant les accès hôtes `7687`, `7474`, `5001`, `3000`. |
| FR-6 | Exécution de l'outillage dans Docker : support complet des commandes `docker compose run --rm backend uv run pytest tests/ -q` et scripts CLI. |

---

## Exigences non fonctionnelles

| # | Exigence | Pourquoi |
|---|---|---|
| NFR-1 | Zéro secret dans les images | Conforme à AGENTS.md §2.4 : `.env` exclu par `.dockerignore`, injection exclusive via `env_file: .env`. |
| NFR-2 | Reproductibilité absolue | Versions fixées sans tag flottant (`neo4j:5.26.31-community`, `uv:0.9.26`, Python 3.11, pnpm verrouillé). |
| NFR-3 | Persistance des données | Volume nommé `neo4j_data` préservé lors d'un cycle `docker compose down` normal (sans `-v`). |
| NFR-4 | Tolérance aux collisions de ports | Ports hôtes paramétrables (`FRONTEND_PORT`, `FLASK_PORT`) pour cohabiter avec d'autres projets sur 3000/3001. |
| NFR-5 | Performance et réactivité | Stack démarrée en $\le 60\text{ s}$ sur machine standard. |

---

## UX requirements

- Pour l'utilisateur final et le développeur : `docker compose up -d` démarre toute la suite MiroFish en une commande unique.
- L'interface web est directement accessible sur `http://localhost:3000` (ou le port configuré) sans manipulation supplémentaire.

---

## Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 005-1 | Dockerfiles dédiés backend et frontend construits depuis les sources locales | `done` | `story-005-1.md` |
| 005-2 | `docker-compose.yml` unifié avec Neo4j, Backend, Frontend et Healthchecks | `done` | `story-005-2.md` |
| 005-3 | Validation du filet global de tests (664 tests) et outillage sous Docker | `done` | `story-005-3.md` |
| 005-4 | Persistance des données Neo4j et cycle de vie des volumes | `backlog` | `story-005-4.md` |
| 005-5 | Banc de qualification Docker de référence et clôture de l'Epic 005 | `backlog` | `story-005-5.md` |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 005-1 | Given le code source du dépôt, when `docker build` est lancé pour le backend et le frontend, then les dépendances sont installées via `uv sync --locked` et `pnpm install --frozen-lockfile` ; les images sont générées sans erreur et sans secret inclus. |
| 005-2 | Given le fichier `docker-compose.yml`, when `docker compose up -d` est exécuté, then les 3 services `neo4j`, `backend` et `frontend` démarrent sur `mirofish_network` ; `backend` attend que Neo4j soit `healthy` ; les ports hôtes sont exposés sans conflit. |
| 005-3 | Given la stack Docker démarrée, when `docker compose run --rm backend uv run pytest tests/ -q` est exécuté, then 100 % des tests (671 tests) passent au vert dans le conteneur ; `ruff check` et `validate_plans.py` s'exécutent sans erreur. |
| 005-4 | Given un graphe créé dans Neo4j sous Docker, when un cycle `docker compose down && docker compose up -d` (sans `-v`) est exécuté, then les nœuds et arêtes du graphe sont 100 % préservés dans le volume `neo4j_data`. |
| 005-5 | Given l'environnement Docker unifié opérationnel, when le script de qualification e2e est lancé dans le conteneur backend, then le pipeline complet s'exécute avec code retour 0 ; l'inspection des images confirme 0 secret ; l'Epic 005 est clos. |

---

## Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`prd.md`](prd.md) | Objectifs et critères chiffrés C1 à C5 de l'Epic 005 |
| [`architecture.md`](architecture.md) | Topologie réseau, ordonnancement des services, diagrammes Mermaid |
| [ADR 0006](../../decisions/0006-docker-first.md) | Docker d'abord : un seul environnement de référence |
| [ADR 0008](../../decisions/0008-pnpm-seul.md) | pnpm uniquement et frozen lockfile |
| [`docker-compose.neo4j.yml`](file:///Users/simon/dev/MiroFish/docker-compose.neo4j.yml) | Configuration de référence de Neo4j 5.26 Community et healthcheck Bolt |
| [`Dockerfile`](file:///Users/simon/dev/MiroFish/Dockerfile) | Dockerfile monolithique amont à restructurer |
| [`docker-compose.yml`](file:///Users/simon/dev/MiroFish/docker-compose.yml) | Compose amont à refondre |
| [`AGENTS.md`](file:///Users/simon/dev/MiroFish/AGENTS.md) | Constitution, commandes Docker cibles (§3) et gestion des secrets (§2.4) |

---

## Décisions liées

- **ADR 0006** : Docker d'abord : un seul environnement de référence.
- **ADR 0008** : pnpm seul pour la partie frontend.
