---
id: "004-3"
epic: "004"
titre: "Ingestion et construction de graphe de bout en bout avec GraphitiGraphStore"
statut: done
auteur: agent
format: "2"
---

# Story 004-3 — Ingestion et construction de graphe de bout en bout avec `GraphitiGraphStore`

## Définition de prêt

- [x] Objectif compris : orchestrer et valider l'ingestion de documents et la construction d'un graphe de connaissances complet via `GraphBuilderService` et `GraphitiGraphStore` vers Neo4j local sans clé Zep.
- [x] Documents consultés : [PRD](prd.md) (notamment critère C3 et FR-4), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/app/services/graph_builder.py`](file:///Users/simon/dev/MiroFish/backend/app/services/graph_builder.py), [`backend/app/api/graph.py`](file:///Users/simon/dev/MiroFish/backend/app/api/graph.py), [`backend/app/utils/graph_store/graphiti_store.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graph_store/graphiti_store.py), [`backend/app/utils/graph_store/factory.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graph_store/factory.py).
- [x] Prérequis vérifiés : Stories 004-1 (LLM universel) et 004-2 (levée des gardes ZEP_API_KEY) closes et validées (601 tests verts). Instance Neo4j locale disponible via Docker (`docker compose -f docker-compose.neo4j.yml up -d`).
- [x] Stratégie de test identifiée : tests unitaires hermétiques validant l'enchaînement complet de `_build_graph_worker` avec `GraphitiGraphStore` (création, découpage, soumission de batch, attente, complétion `TaskStatus.COMPLETED`, mise à jour du projet en `GRAPH_COMPLETED`) et protocole de vérification d'ingestion réelle sur document de test.

## Définition de fini

- [x] `GraphBuilderService.build_graph_async()` et la tâche de fond de `/api/graph/build` s'exécutent de bout en bout avec `GraphitiGraphStore` sans lever d'exception liée à Zep Cloud ou `ZEP_API_KEY`.
- [x] Le workflow asynchrone découpe le texte, soumet les lots d'épisodes, notifie les paliers de progression dans `TaskManager` (10% création, 15% ontologie, 20-60% chunks/lots, 60-90% indexation, 90% métadonnées, 100% complétion).
- [x] Le projet passe avec succès à l'état `ProjectStatus.GRAPH_COMPLETED` avec `graph_id`, `node_count` et `edge_count` renseignés.
- [x] La route GET /api/graph/data/<graph_id> renvoie la structure complète du graphe (nœuds et arêtes) consommable par l'interface utilisateur.
- [x] Un protocole ou banc d'essai valide l'ingestion réelle d'un extrait de document produisant un graphe non vide (critère C3 : ≥ 5 nœuds, ≥ 3 arêtes) sous Neo4j local.
- [x] Filet global de tests maintenu au vert (≥ 601 tests verts).
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement.

## Tâches

- [x] Auditer le pipeline d'ingestion de `GraphBuilderService` et vérifier l'alignement des callbacks et de la sérialisation des batches avec `GraphitiGraphStore`.
- [x] Vérifier la robustesse des callbacks de progression (`remember_graph`, `remember_batch`, `add_progress_callback`, `wait_progress_callback`) lors de l'exécution dans le thread de fond de `graph.py`.
- [x] Écrire la suite de tests unitaires hermétiques simulant le cycle de vie complet de construction de graphe avec `GraphitiGraphStore` mocké.
- [x] Écrire et exécuter le protocole de vérification d'ingestion réelle contre Neo4j local et OpenCode Go (validation du critère C3).
- [x] Valider l'intégrité de la suite globale (`uv run pytest tests/ -q`), le lint (`uv run ruff check .`) et la structure de planification (`uv run python scripts/validate_plans.py`).

### Review Findings

- [x] [Review][Patch] Test unitaire hermétique de bout en bout pour GraphBuilderService.build_graph_async() [backend/tests/test_graph_builder_e2e.py:950]
- [x] [Review][Patch] Purge du graphe temporaire dans le bloc finally de verifier_ingestion_graphiti.py en cas d'erreur [backend/scripts/verifier_ingestion_graphiti.py:522]
- [x] [Review][Patch] Sauvegarde et restauration des configurations globales Config dans verifier_ingestion_graphiti.py [backend/scripts/verifier_ingestion_graphiti.py:369]
- [x] [Review][Patch] Test de non-régression de la gestion des erreurs dans test_verifier_ingestion_graphiti.py [backend/tests/test_verifier_ingestion_graphiti.py:125]
- [x] [Review][Patch] Correction de la coquille d'URL de route dans le critère de story (/data/<graph_id>) [docs/plans/004-bascule-sans-zep/story-004-3.md:24]

#### Rejected

- [Accès direct aux index Neo4j via store._driver dans le script de validation] : rejeté (`low`) — Standard pour les scripts de vérification technique directe.
- [Argument CLI --mock-llm redondant dans argparse] : rejeté (`low`) — Sans impact sur le fonctionnement de l'outil CLI.

## Notes de développement

La Story 004-3 constitue le cœur opérationnel de l'Epic 004 (« Construire un graphe en local sans clé Zep »).

Après avoir configuré le LLM universel (Story 004-1) et levé les gardes de clé bloquants dans les routes API et services métiers (Story 004-2), il s'agit désormais de prouver que le pipeline complet d'ingestion s'exécute avec succès en local :
1. Réception de la requête `/api/graph/build` avec un `project_id`.
2. Découpage du texte source en fragments (`TextProcessor.split_text`).
3. Création du graphe dans `GraphitiGraphStore` (`create_graph`).
4. Enregistrement de l'ontologie (`set_ontology`).
5. Ingestion par lots (`add_text_batch` / `wait_for_batch`) pilotant les sessions d'extraction et d'indexation locale dans Neo4j.
6. Récupération des métadonnées du graphe (`get_graph_info`, `get_graph_data`).
7. Mise à jour de l'état du projet en `ProjectStatus.GRAPH_COMPLETED`.

Le respect du critère C3 du PRD (graphe local non vide avec ≥ 5 nœuds et ≥ 3 arêtes) validera l'aptitude de MiroFish à construire son graphe de connaissances sans aucun appel cloud.

## Revue

- **Couche Contrat & Architecture** : Le découplage complet est confirmé : `GraphBuilderService` orchestre l'ingestion via le contrat abstrait `GraphStore`, consommé de manière identique par l'API et par les workers asynchrones. La route `GET /api/graph/data/<graph_id>` restitue fidèlement nœuds, arêtes, métadonnées et statistiques consommables par le frontend Vue.js. Les callbacks de progression sont adaptés de manière robuste pour les deux signatures `(msg, ratio)` et `(status, cur, tot)`.
- **Couche Hermétisme & Sécurité** : 0 fuite de secret ni d'API key dans le diff ou les sorties. Les tests unitaires sous pytest sont 100 % hermétiques et isolés avec `MockE2EGraphitiStore`. Le banc d'ingestion réelle `backend/scripts/verifier_ingestion_graphiti.py` utilise un nommage déterministe, restaure l'état global `Config` en sortie et isole les graphes de test avec purge automatique via `delete_graph` même en cas d'exception levée.
- **Couche Tests & Qualité** : 13 nouveaux tests unitaires hermétiques ajoutés (`test_graph_builder_e2e.py` et `test_verifier_ingestion_graphiti.py`), couvrant l'API, les workers, `build_graph_async()` et les chemins d'erreur du banc, portant le filet global à 614 tests pytest verts. Le banc d'ingestion réelle valide formellement le critère C3 du PRD sous Neo4j 5.26 local (6 nœuds ≥ 5, 4 arêtes ≥ 3). Lint `ruff` et validation `validate_plans.py` au vert.

## Notes de complétion

Story 004-3 menée à bien et validée :
1. Implémentation de la suite complète de tests de bout en bout dans [`backend/tests/test_graph_builder_e2e.py`](file:///Users/simon/dev/MiroFish/backend/tests/test_graph_builder_e2e.py), couvrant l'exécution de `build_graph_async()`, du worker asynchrone, les transitions d'état du projet (`ONTOLOGY_GENERATED` → `GRAPH_BUILDING` → `GRAPH_COMPLETED`), la gestion des erreurs (`FAILED`), la reconstruction avec `force=True` et la récupération des données via l'API.
2. Implémentation du banc de vérification d'ingestion réelle dans [`backend/scripts/verifier_ingestion_graphiti.py`](file:///Users/simon/dev/MiroFish/backend/scripts/verifier_ingestion_graphiti.py), confirmant le critère C3 avec 6 nœuds et 4 arêtes sous Neo4j local, avec gestion étanche des nettoyages.
3. Implémentation des tests de non-régression du script dans [`backend/tests/test_verifier_ingestion_graphiti.py`](file:///Users/simon/dev/MiroFish/backend/tests/test_verifier_ingestion_graphiti.py), couvrant succès et échecs.
4. Revue de code contradictoire BMad (4 couches) réalisée et 5 correctifs appliqués. Filet global de tests porté à 614 tests verts (+13 tests). Validations `ruff` et `validate_plans.py` impeccables.

