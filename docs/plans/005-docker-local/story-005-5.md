---
id: "005-5"
epic: "005"
titre: "Banc de qualification Docker de référence et clôture de l'Epic 005"
statut: backlog
auteur: agent
format: "2"
---

# Story 005-5 — Banc de qualification Docker de référence et clôture de l'Epic 005

## Définition de prêt

- [ ] Objectif compris : valider et prouver formellement le bon fonctionnement de bout en bout de l'environnement conteneurisé de référence (Docker-first, ADR 0006), en exécutant le banc de qualification globale local-first (`backend/scripts/verifier_qualification_local_first.py`) directement dans le conteneur `backend` connecté à `neo4j`, en vérifiant l'absence totale de secrets dans les couches d'images Docker (`docker history`), et en rédigeant le rapport de qualification finale versionné (`rapport-qualification-epic-005.md`) avec VERDICT GO pour clôturer l'Epic 005.
- [ ] Documents consultés : [PRD](prd.md) (notamment critères de sortie C1 à C5, exigences FR-1 à FR-6, NFR-1 à NFR-5), [Architecture](architecture.md) (§5, §6), [Epic 005](epic-005.md), [`docker-compose.yml`](../../docker-compose.yml), [AGENTS.md](../../AGENTS.md) (§2.9, §3).
- [ ] Prérequis vérifiés : Images `mirofish-backend:local` et `mirofish-frontend:local` construites (Story 005-1), `docker-compose.yml` unifié avec healthchecks opérationnel (Story 005-2), filet global de tests (684 tests) et outillage validés sous Docker (Story 005-3), persistance et cycle de vie des volumes validés (Story 005-4).
- [ ] Stratégie de test identifiée : conception d'une sonde / script de qualification d'environnement (`backend/scripts/verifier_qualification_docker.py`), exécution du banc e2e dans le conteneur backend via `docker compose run --rm backend`, inspection de sécurité `docker history` pour vérifier l'étanchéité des secrets (NFR-1, C5), et suite de tests unitaires hermétiques validant le protocole de qualification (`backend/tests/test_verifier_qualification_docker.py`).

## Définition de fini

- [ ] Sonde d'orchestration de qualification Docker opérationnelle (`backend/scripts/verifier_qualification_docker.py`) démontrant la conformité aux critères C1 à C5 du PRD de l'Epic 005.
- [ ] Preuve formelle d'exécution réussie du pipeline e2e local-first dans le conteneur backend (`verifier_qualification_local_first.py`) avec code retour 0 (Critère C4).
- [ ] Preuve formelle d'absence de secrets et tokens dans les calques d'images Docker via analyse `docker history` (Critère C5, NFR-1).
- [ ] Mesure et vérification des temps de démarrage unifiés de la stack ($\le 60$ s, Critère C1).
- [ ] Suite de tests unitaires hermétiques validant la conformité du banc de qualification Docker.
- [ ] Rapport de qualification finale consigné dans `docs/plans/005-docker-local/rapport-qualification-epic-005.md` avec VERDICT GO formalisé.
- [ ] Filet global de tests au vert (684 tests + nouveaux tests) et outillage (`ruff check .`, `validate_plans.py`) 100 % passants.
- [ ] Clôture formelle de l'Epic 005 dans `docs/sprint-status.yaml`, `docs/STATUS.md` et `AGENTS.md`.

## Tâches

- [ ] Développer la sonde d'orchestration de qualification Docker (`backend/scripts/verifier_qualification_docker.py`).
- [ ] Exécuter la qualification e2e complète sous Docker (`docker compose run --rm backend uv run python scripts/verifier_qualification_local_first.py`).
- [ ] Inspecter les calques d'images backend et frontend pour certifier l'absence de fuite de secrets (`docker history`).
- [ ] Écrire la suite de tests unitaires hermétiques (`backend/tests/test_verifier_qualification_docker.py`).
- [ ] Rédiger le rapport de qualification finale versionné (`docs/plans/005-docker-local/rapport-qualification-epic-005.md`).
- [ ] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [ ] Mettre à jour l'index des stories, la documentation d'architecture et l'état global du sprint pour clôturer l'Epic 005.

## Notes de développement

L'Epic 005 concrétise l'ADR 0006 : "Docker d'abord — un seul environnement de référence reproductible".
La Story 005-5 constitue l'épreuve de qualification finale de l'Epic 005. Elle boucle les 4 stories précédentes :
1. Les conteneurs spécialisés construits localement (005-1).
2. La stack multi-services unifiée avec healthchecks (005-2).
3. Le filet complet de tests et l'outillage exécutés dans le conteneur (005-3).
4. La persistance des volumes et le cycle de vie des données Neo4j (005-4).
La Story 005-5 apporte la preuve ultime : exécuter le banc e2e sans Zep (`verifier_qualification_local_first.py`) au cœur de l'environnement conteneurisé backend, tester les temps de démarrage, certifier l'absence de secret dans les images, et délivrer le VERDICT GO officiel de l'environnement de référence Docker.

## Revue

- **Couche Contrat & Architecture** : À compléter lors de la revue BMad.
- **Couche Hermétisme & Sécurité** : À compléter lors de la revue BMad.
- **Couche Tests & Qualité** : À compléter lors de la revue BMad.
- **Couche Robustesse & CI** : À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
