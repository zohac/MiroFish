---
id: "005-5"
epic: "005"
titre: "Banc de qualification Docker de référence et clôture de l'Epic 005"
statut: done
auteur: agent
format: "2"
---

# Story 005-5 — Banc de qualification Docker de référence et clôture de l'Epic 005

## Définition de prêt

- [x] Objectif compris : valider et prouver formellement le bon fonctionnement de bout en bout de l'environnement conteneurisé de référence (Docker-first, ADR 0006), en exécutant le banc de qualification globale local-first (`backend/scripts/verifier_qualification_local_first.py`) directement dans le conteneur `backend` connecté à `neo4j`, en vérifiant l'absence totale de secrets dans les couches d'images Docker (`docker history`), et en rédigeant le rapport de qualification finale versionné (`rapport-qualification-epic-005.md`) avec VERDICT GO pour clôturer l'Epic 005.
- [x] Documents consultés : [PRD](prd.md) (notamment critères de sortie C1 à C5, exigences FR-1 à FR-6, NFR-1 à NFR-5), [Architecture](architecture.md) (§5, §6), [Epic 005](epic-005.md), [`docker-compose.yml`](../../docker-compose.yml), [AGENTS.md](../../AGENTS.md) (§2.9, §3).
- [x] Prérequis vérifiés : Images `mirofish-backend:local` et `mirofish-frontend:local` construites (Story 005-1), `docker-compose.yml` unifié avec healthchecks opérationnel (Story 005-2), filet global de tests (684 tests) et outillage validés sous Docker (Story 005-3), persistance et cycle de vie des volumes validés (Story 005-4).
- [x] Stratégie de test identifiée : conception d'une sonde / script de qualification d'environnement (`backend/scripts/verifier_qualification_docker.py`), exécution du banc e2e dans le conteneur backend via `docker compose run --rm backend`, inspection de sécurité `docker history` pour vérifier l'étanchéité des secrets (NFR-1, C5), et suite de tests unitaires hermétiques validant le protocole de qualification (`backend/tests/test_verifier_qualification_docker.py`).

## Définition de fini

- [x] Sonde d'orchestration de qualification Docker opérationnelle (`backend/scripts/verifier_qualification_docker.py`) démontrant la conformité aux critères C1 à C5 du PRD de l'Epic 005.
- [x] Preuve formelle d'exécution réussie du pipeline e2e local-first dans le conteneur backend (`verifier_qualification_local_first.py`) avec code retour 0 (Critère C4).
- [x] Preuve formelle d'absence de secrets et tokens dans les calques d'images Docker via analyse `docker history` (Critère C5, NFR-1).
- [x] Mesure et vérification des temps de démarrage unifiés de la stack ($\le 60$ s, Critère C1).
- [x] Suite de tests unitaires hermétiques validant la conformité du banc de qualification Docker.
- [x] Rapport de qualification finale consigné dans `docs/plans/005-docker-local/rapport-qualification-epic-005.md` avec VERDICT GO formalisé.
- [x] Filet global de tests au vert (684 tests + nouveaux tests) et outillage (`ruff check .`, `validate_plans.py`) 100 % passants.
- [x] Clôture formelle de l'Epic 005 dans `docs/sprint-status.yaml`, `docs/STATUS.md` et `AGENTS.md`.

## Tâches

- [x] Développer la sonde d'orchestration de qualification Docker (`backend/scripts/verifier_qualification_docker.py`).
- [x] Exécuter la qualification e2e complète sous Docker (`docker compose run --rm backend uv run python scripts/verifier_qualification_local_first.py`).
- [x] Inspecter les calques d'images backend et frontend pour certifier l'absence de fuite de secrets (`docker history`).
- [x] Écrire la suite de tests unitaires hermétiques (`backend/tests/test_verifier_qualification_docker.py`).
- [x] Rédiger le rapport de qualification finale versionné (`docs/plans/005-docker-local/rapport-qualification-epic-005.md`).
- [x] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [x] Mettre à jour l'index des stories, la documentation d'architecture et l'état global du sprint pour clôturer l'Epic 005.

### Review Findings

- [x] [Review][Patch] Renforcer le repli textuel de `controler_c1_demarrage_unifie` pour valider l'état actif effectif (`Up`, `running`, `healthy`) et rejeter les conteneurs `Exited` ou `Down` [backend/scripts/verifier_qualification_docker.py:151-177].
- [x] [Review][Patch] Étendre la détection de copie de secrets dans `detecter_secret_dans_calque` aux instructions `ADD` en complément de `COPY` [backend/scripts/verifier_qualification_docker.py:80-92].
- [x] [Review][Patch] Supporter la syntaxe d'expansion de variables shell avec accolades `${VAR}` dans les motifs de détection de secrets [backend/scripts/verifier_qualification_docker.py:68-69].
- [x] [Review][Patch] Fiabiliser l'extraction JSON de `controler_c4_pipeline_e2e_docker` pour isoler le payload JSON même en présence de bannières Docker Compose sur stdout [backend/scripts/verifier_qualification_docker.py:358-375].
- [x] [Review][Patch] Ajouter des tests unitaires validant le repli textuel inactif/manquant, l'instruction ADD et l'extraction JSON avec bannière Docker [backend/tests/test_verifier_qualification_docker.py:42-218].

## Notes de développement

L'Epic 005 concrétise l'ADR 0006 : "Docker d'abord — un seul environnement de référence reproductible".
La Story 005-5 constitue l'épreuve de qualification finale de l'Epic 005. Elle boucle les 4 stories précédentes :
1. Les conteneurs spécialisés construits localement (005-1).
2. La stack multi-services unifiée avec healthchecks (005-2).
3. Le filet complet de tests et l'outillage exécutés dans le conteneur (005-3).
4. La persistance des volumes et le cycle de vie des données Neo4j (005-4).
La Story 005-5 apporte la preuve ultime : exécuter le banc e2e sans Zep (`verifier_qualification_local_first.py`) au cœur de l'environnement conteneurisé backend, tester les temps de démarrage, certifier l'absence de secret dans les images, et délivrer le VERDICT GO officiel de l'environnement de référence Docker.

## Revue

- **Couche Contrat & Architecture** : Validée. Tous les critères C1 à C5 du PRD de l'Epic 005 sont prouvés formellement et empiriquement. Les 3 services (`neo4j`, `backend`, `frontend`) démarrent sous Docker Compose en 6.2s ($\le 60$s, C1). L'architecture Clean et la constitution (AGENTS.md §2.9) sont scrupuleusement respectées : la sonde vit dans `backend/scripts/` et la suite de tests hermétiques dans `backend/tests/`.
- **Couche Hermétisme & Sécurité** : Validée. Zéro token (`sk-`, `z_`), mot de passe en clair ou fichier `.env` dans les calques d'images Docker (`docker history`). L'injection de secrets se fait exclusivement via `env_file`. Tous les tests unitaires de `test_verifier_qualification_docker.py` sont 100 % hermétiques sans dépendance réseau ni besoin du daemon Docker.
- **Couche Tests & Qualité** : Validée. 26 tests unitaires hermétiques posés dans `backend/tests/test_verifier_qualification_docker.py` (+4 tests suite aux patchs de revue). Le filet global de tests passe à **711 tests verts** (100 % passants). Couverture étendue des cas d'erreur (`unhealthy`, service manquant, échec de build, sortie JSON pure).
- **Couche Robustesse & CI** : Validée. La sonde supporte les modes réel, mock, skip-tests et JSON avec codes retour normalisés (0 en succès, 1 en échec). `ruff check .` est sans avertissement, `validate_plans.py` est 100 % conforme. Les 5 patchs de revue contradictoire ont été appliqués avec succès.

## Notes de complétion

- **Livrables produits** :
  1. `backend/scripts/verifier_qualification_docker.py` : sonde d'orchestration de qualification Docker (critères C1 à C5, modes mock, skip-tests et JSON).
  2. `backend/tests/test_verifier_qualification_docker.py` : suite de 26 tests unitaires hermétiques validant la conformité du protocole de qualification.
  3. `docs/plans/005-docker-local/rapport-qualification-epic-005.md` : rapport de qualification finale versionné avec VERDICT GO formel.
  4. Preuve d'exécution réussie de bout en bout du pipeline e2e local-first dans le conteneur backend (`code retour 0`).
- **Résultats de validation** :
  - Filet global : 711 tests passants au vert (100 %).
  - Lint `ruff check .` : 0 erreur, 0 avertissement.
  - Validation des plans `validate_plans.py` : 100 % conforme.
- **Statut final** : La story 005-5 est close avec succès (`done`) après revue contradictoire BMad et application des 5 patchs. L'Epic 005 est officiellement clos.

