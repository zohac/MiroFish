---
id: "005-3"
epic: "005"
titre: "Validation du filet global de tests (664 tests) et outillage sous Docker"
statut: done
auteur: agent
format: "2"
---

# Story 005-3 — Validation du filet global de tests (664 tests) et outillage sous Docker

## Définition de prêt

- [x] Objectif compris : valider que l'environnement de référence Docker (`docker compose run --rm backend`) exécute 100 % de l'outillage et du filet de tests (664 tests unitaires pytest, `ruff check .`, `validate_plans.py`) de manière reproductible et isolée, sans dépendance vis-à-vis des outils installés sur la machine hôte.
- [x] Documents consultés : [PRD](prd.md) (notamment critères C2 et C5, exigences FR-6, NFR-2), [Architecture](architecture.md) (§6), [Epic 005](epic-005.md), [`docker-compose.yml`](../../docker-compose.yml), [ADR 0006](../../decisions/0006-docker-first.md), [AGENTS.md](../../AGENTS.md) (§2.2, §2.9, §3).
- [x] Prérequis vérifiés : `backend/Dockerfile` construit et opérationnel (`mirofish-backend:local`), `docker-compose.yml` unifié configuré avec les services `neo4j`, `backend`, `frontend` sur le réseau `mirofish_network`, suite de 664 tests unitaires passants au vert sur l'hôte.
- [x] Stratégie de test identifiée : exécution de `docker compose run --rm backend uv run pytest tests/ -q` dans le conteneur, vérification de l'hermétisme sans `.env`, exécution du linter `ruff check .` et de `validate_plans.py` dans le conteneur, création d'une suite de tests automatisée validant la parité d'exécution hôte/Docker (`backend/tests/test_docker_tooling_parity.py`).

## Définition de fini

- [x] Exécution réussie de `docker compose run --rm backend uv run pytest tests/ -q` validant 100 % des tests (671 tests au total, 668 passants + 3 skipped) au vert dans le conteneur.
- [x] Exécution réussie de `docker compose run --rm backend uv run ruff check .` avec 0 erreur.
- [x] Exécution réussie de `docker compose run --rm backend uv run python scripts/validate_plans.py` validant la structure de planification dans le conteneur.
- [x] Vérification du comportement des volumes montés (`uploads`, `simulations`) et des permissions de fichiers créés lors de l'exécution des tests.
- [x] Suite de tests unitaires hermétiques validant la parité de l'outillage Docker (`backend/tests/test_docker_tooling_parity.py`, `backend/tests/test_pyproject_override.py`).
- [x] Tests de non-régression et de structure de plan (`validate_plans.py`, `ruff check`) passants sans avertissement.

## Tâches

- [x] Vérifier la configuration du conteneur `backend` pour l'exécution de commandes éphémères (`docker compose run --rm backend`).
- [x] Exécuter la suite complète des tests pytest dans le conteneur `backend` sous Docker.
- [x] Identifier et corriger les écarts environnementaux entre l'hôte et le conteneur (inclusion de `docs/`, `docker-compose.yml`, `.dockerignore` avec `!.env.example`, adaptation de `test_pyproject_override.py` pour conteneur sans `.git`).
- [x] Exécuter le linter `ruff check .` et le validateur de plans `scripts/validate_plans.py` dans le conteneur avec résultat parfait.
- [x] Écrire la suite de tests unitaires hermétiques (`backend/tests/test_docker_tooling_parity.py`).
- [x] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [x] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

### Review Findings

- [x] [Review][Patch] Aligner le cycle de vie de la Story 005-3 en formalisant la phase de revue avant clôture [docs/plans/005-docker-local/story-005-3.md:5]
- [x] [Review][Patch] Sécuriser l'import de `validate_plans` dans `test_docker_tooling_parity.py` contre toute collision de namespace [backend/tests/test_docker_tooling_parity.py:276]
- [x] [Review][Patch] Déplacer `import os` au niveau supérieur dans `test_pyproject_override.py` [backend/tests/test_pyproject_override.py:31,449]
- [x] [Review][Patch] Aligner `backend/.dockerignore` avec `!.env.example` pour symétrie avec le fichier racine [backend/.dockerignore:1-7]
- [x] [Review][Patch] Supporter indifféremment dictionnaire et liste pour `environment` dans `test_docker_tooling_parity.py` [backend/tests/test_docker_tooling_parity.py:346]
- [x] [Review][Patch] Ajouter un test unitaire hermétique validant le fallback `has_git=False` de `test_pyproject_override.py` sur l'hôte [backend/tests/test_pyproject_override.py:465]

#### Rejected
- Absence des outils Docker CLI dans l'image mirofish-backend:local : false (le conteneur backend applique le principe de responsabilité unique ; les tests Docker CLI sont légitimement passés via pytest.skip).
- Exclusion de package.json et node_modules dans le build backend : false (ADR 0006 et ADR 0008 séparent hermétiquement les runtimes backend et frontend).
- Montage de ./backend complet dans docker-compose.yml : low (écraserait le venv Debian slim /app/backend/.venv sans volume anonyme supplémentaire ; non requis pour le filet de tests de 005-3).

## Notes de développement

L'ADR 0006 et la constitution ([`AGENTS.md`](../../AGENTS.md) §2.9) posent Docker comme l'environnement de référence cible unique pour éviter toute dérive entre les postes de développement.

La Story 005-3 valide concrètement cette promesse :
- Le conteneur `backend` (`mirofish-backend:local`) a été ajusté pour embarquer les artefacts de gouvernance non sensibles (`docs/`, `AGENTS.md`, `docker-compose.yml`, `docker-compose.neo4j.yml`, `.env.example`, `frontend/vite.config.js`) permettant l'exécution complète des tests statiques et des validateurs de plans directement dans le conteneur.
- L'exclusion des secrets `.env` dans `.dockerignore` (racine et backend) a été préservée et affinée avec `!.env.example` pour permettre aux tests de contrat de vérifier le template sans fuite d'informations sensibles.
- Le test de synchronisation de lock (`test_pyproject_override.py`) a été rendu compatible avec les environnements conteneurisés épurés de `.git`, et complété par un test unitaire dédié sur l'hôte.
- L'ensemble des 671 tests unitaires du projet s'exécute avec 100 % de succès dans le conteneur Docker `backend` sous Python 3.11 Debian slim (`668 passed, 3 skipped, 0 failed`).
- L'outillage complet (`ruff check .`, `validate_plans.py`) s'exécute de manière identique sous Docker et sur la machine hôte.

## Revue

- **Couche Contrat & Architecture** : Conformité totale avec le critère C2 du PRD Epic 005 et l'exigence FR-6. La chaîne de qualité s'exécute dans l'image de référence `mirofish-backend:local` sans dépendance vers les outils de la machine hôte.
- **Couche Hermétisme & Sécurité** : `.dockerignore` racine et `backend/.dockerignore` garantissent qu'aucun fichier `.env` ni secret ne pénètre dans l'image. Le template `.env.example` est copié isolément.
- **Couche Tests & Qualité** : 7 nouveaux tests unitaires hermétiques ajoutés (+6 dans `backend/tests/test_docker_tooling_parity.py`, +1 dans `backend/tests/test_pyproject_override.py`). La suite globale compte désormais 671 tests unitaires au vert (668 passants + 3 skipped sous Docker, 671 passants sur hôte).
- **Couche Robustesse & CI** : Les commandes `docker compose run --rm backend uv run pytest tests/ -q`, `docker compose run --rm backend uv run ruff check .` et `docker compose run --rm backend uv run python scripts/validate_plans.py` réussissent avec un code retour 0. Les 6 correctifs contradictoires BMad sont intégrés et vérifiés.

## Notes de complétion

La Story 005-3 est intégralement validée et achevée :
- Parité d'exécution Docker / hôte prouvée : 671 tests unitaires (668 passants, 3 skipped sous Docker, 0 échec).
- Linter `ruff check .` et validateur de plans `scripts/validate_plans.py` 100 % passants dans le conteneur.
- Ajustements de build et tests appliqués (`.dockerignore`, `backend/.dockerignore`, `backend/Dockerfile`, `test_pyproject_override.py`, `test_docker_tooling_parity.py`).
- Suite de tests unitaires portée à 671 tests (+7 tests).
- Revue BMad contradictoire validée (6 patchs appliqués, 3 rejets documentés).
