---
id: "005-1"
epic: "005"
titre: "Dockerfiles dédiés backend et frontend construits depuis les sources locales"
statut: done
auteur: agent
format: "2"
---

# Story 005-1 — Dockerfiles dédiés backend et frontend construits depuis les sources locales

## Définition de prêt

- [x] Objectif compris : concevoir les Dockerfiles dédiés pour le backend (`backend/Dockerfile`) et le frontend (`frontend/Dockerfile`), assurant une construction autonome et reproductible depuis les sources locales de notre fork `local-first`, avec cache optimal des dépendances (`uv.lock` et `pnpm-lock.yaml`) et 0 secret dans les images.
- [x] Documents consultés : [PRD](prd.md) (notamment critères C1, C2 et C5), [Architecture](architecture.md), [Epic 005](epic-005.md), [`Dockerfile`](file:///Users/simon/dev/MiroFish/Dockerfile), [ADR 0006](../../decisions/0006-docker-first.md), [ADR 0008](../../decisions/0008-pnpm-seul.md), [AGENTS.md](file:///Users/simon/dev/MiroFish/AGENTS.md) (§2.4, §2.5, §2.9).
- [x] Prérequis vérifiés : Codebase locale fonctionnelle (632 tests verts), `backend/uv.lock` synchronisé avec `backend/pyproject.toml`, `pnpm-lock.yaml` synchronisé avec `package.json`, `.dockerignore` prêt à exclure `.env` et les dossiers temporaires.
- [x] Stratégie de test identifiée : validation de la constructibilité des images via `docker build`, vérification du cache de couches, suite de tests unitaires hermétiques validant la structure des Dockerfiles et l'absence d'exposition de secrets, contrôle d'inspection d'image.

## Définition de fini

- [x] `backend/Dockerfile` autonome basé sur `python:3.11-slim`, copiant `uv` depuis `ghcr.io/astral-sh/uv:0.9.26`, installant les dépendances Python via `uv sync --locked`, sans Node.js ni dépendances frontend superflues.
- [x] `frontend/Dockerfile` autonome basé sur `node:20-slim`, avec `pnpm` activé via corepack conformément à l'ADR 0008, installant les dépendances via `pnpm install --frozen-lockfile`, sans dépendances Python ni PyTorch.
- [x] Cache de couches Docker optimal : les manifestes de dépendances (`uv.lock`, `pyproject.toml`, `package.json`, `pnpm-lock.yaml`) sont copiés et installés avant la copie du code source applicatif pour accélérer les reconstructions.
- [x] Fichiers `.dockerignore` configurés pour exclure formellement `.env`, `.venv`, `node_modules`, `__pycache__`, `.git`, `.pytest_cache` et tout fichier temporaire (AGENTS.md §2.4).
- [x] 0 secret présent dans les images construites (vérifié par inspection `docker history` ou analyse statique).
- [x] Tests de non-régression et de structure de plan (`validate_plans.py`, `ruff check`) passants sans avertissement.

## Tâches

- [x] Concevoir le `backend/Dockerfile` spécialisé avec `python:3.11-slim` et `uv sync --locked`.
- [x] Concevoir le `frontend/Dockerfile` spécialisé avec `node:20-slim` et `pnpm install --frozen-lockfile`.
- [x] Mettre en place et consolider les fichiers `.dockerignore` (racine, backend, frontend) pour interdire toute inclusion de secrets ou d'environnements hôtes.
- [x] Valider la construction locale des images `mirofish-backend:local` et `mirofish-frontend:local`.
- [x] Développer une suite de tests unitaires hermétiques validant la conformité des directives Dockerfiles et des fichiers `.dockerignore` (`backend/tests/test_docker_build_config.py`).
- [x] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [x] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

## Notes de développement

Dans le dépôt amont, un unique `Dockerfile` à la racine regroupait Python 3.11 et Node.js dans un même conteneur, démarrant le backend et le frontend via `CMD ["pnpm", "run", "dev"]`.

Cette approche présentait de sérieux inconvénients :
1. **Poids et temps de build excessifs** : le conteneur mélangeait le runtime Python (incluant PyTorch, sentence-transformers, graphiti-core) et l'environnement Node/npm complet.
2. **Couplage de cycle de vie** : impossible de redémarrer le backend sans couper le frontend, et impossible de lancer un conteneur dédié uniquement aux tests unitaires backend sans instancier tout l'écosystème Node.
3. **Divergence avec la cible Docker-first** : l'ADR 0006 et la constitution exigent que Docker Compose orchestre des services bien distincts (`backend`, `frontend`, `neo4j`) permettant d'exécuter `docker compose run --rm backend uv run pytest tests/ -q`.

La Story 005-1 a posé la première pierre fondamentale de l'Epic 005 :
- Conception de `backend/Dockerfile` : basé sur `python:3.11-slim`, injection de `uv 0.9.26`, dépendances compilées (`gcc`, `python3-dev` pour les extensions C comme `psutil`), `uv sync --locked`, et copie partagée des locales.
- Conception de `frontend/Dockerfile` : basé sur `node:20-slim`, `corepack` avec `pnpm@10.23.0`, `pnpm --dir frontend install --frozen-lockfile`, et copie partagée des locales.
- Consolidation rigoureuse de `.dockerignore` à la racine, dans `backend/` et dans `frontend/` (0 secret, 0 venv, 0 artefact d'hôte).
- Validation réelle des builds locaux (`mirofish-backend:local` et `mirofish-frontend:local`) avec exécution de tests de sanity check (`uv run python -c "from app import create_app"`).
- Implémentation d'une suite de 19 tests unitaires hermétiques (`backend/tests/test_docker_build_config.py`).

## Revue

- **Couche Contrat & Architecture** : Conforme aux ADR 0006, 0008 et aux spécifications de l'Architecture Epic 005. Découpage strict des images par responsabilité sans pollution croisée.
- **Couche Hermétisme & Sécurité** : 0 secret copié, `.env` et variantes strictement exclus à 3 niveaux de `.dockerignore`. Aucun mot de passe ni clé en dur dans les Dockerfiles. Étanchéité stricte éprouvée : absence d'outils Node dans backend et absence d'outils Python dans frontend.
- **Couche Tests & Qualité** : 19 tests unitaires ajoutés couvrant la présence, la base image, l'ordonnancement de cache, les dépendances C, l'absence d'outils croisés, les ports, commandes et exclusions. Suite de 651 tests au vert (632 existants + 19 nouveaux).
- **Couche Robustesse & Performance** : Cache de couches optimisé en copiant les manifestes de lock avant le code source applicatif.

## Notes de complétion

1. `backend/Dockerfile` et `frontend/Dockerfile` sont créés, validés et construits avec succès en local.
2. Les fichiers `.dockerignore` assurent l'étanchéité absolue vis-à-vis des secrets et des artefacts temporaires.
3. Les 19 tests unitaires dédiés passent au vert, `ruff check` et `validate_plans.py` passent sans erreur.
4. Story 005-1 close avec succès, prête pour la Story 005-2 (`docker-compose.yml` unifié avec Neo4j, Backend, Frontend et Healthchecks).
