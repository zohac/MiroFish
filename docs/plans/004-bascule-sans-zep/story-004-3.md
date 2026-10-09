---
id: "004-3"
epic: "004"
titre: "Ingestion et construction de graphe de bout en bout avec GraphitiGraphStore"
statut: backlog
auteur: agent
format: "2"
---

# Story 004-3 — Ingestion et construction de graphe de bout en bout avec `GraphitiGraphStore`

## Définition de prêt

- [ ] Objectif compris : orchestrer et valider l'ingestion de documents et la construction d'un graphe de connaissances complet via `GraphBuilderService` et `GraphitiGraphStore` vers Neo4j local sans clé Zep.
- [ ] Documents consultés : [PRD](prd.md) (notamment critère C3 et FR-4), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/app/services/graph_builder.py`](file:///Users/simon/dev/MiroFish/backend/app/services/graph_builder.py), [`backend/app/api/graph.py`](file:///Users/simon/dev/MiroFish/backend/app/api/graph.py), [`backend/app/utils/graph_store/graphiti_store.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graph_store/graphiti_store.py), [`backend/app/utils/graph_store/factory.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graph_store/factory.py).
- [ ] Prérequis vérifiés : Stories 004-1 (LLM universel) et 004-2 (levée des gardes ZEP_API_KEY) closes et validées (601 tests verts). Instance Neo4j locale disponible via Docker (`docker compose -f docker-compose.neo4j.yml up -d`).
- [ ] Stratégie de test identifiée : tests unitaires hermétiques validant l'enchaînement complet de `_build_graph_worker` avec `GraphitiGraphStore` (création, découpage, soumission de batch, attente, complétion `TaskStatus.COMPLETED`, mise à jour du projet en `GRAPH_COMPLETED`) et protocole de vérification d'ingestion réelle sur document de test.

## Définition de fini

- [ ] `GraphBuilderService.build_graph_async()` et la tâche de fond de `/api/graph/build` s'exécutent de bout en bout avec `GraphitiGraphStore` sans lever d'exception liée à Zep Cloud ou `ZEP_API_KEY`.
- [ ] Le workflow asynchrone découpe le texte, soumet les lots d'épisodes, notifie les paliers de progression dans `TaskManager` (10% création, 15% ontologie, 20-60% chunks/lots, 60-90% indexation, 90% métadonnées, 100% complétion).
- [ ] Le projet passe avec succès à l'état `ProjectStatus.GRAPH_COMPLETED` avec `graph_id`, `node_count` et `edge_count` renseignés.
- [ ] La route `GET /api/graph/<graph_id>/data` renvoie la structure complète du graphe (nœuds et arêtes) consommable par l'interface utilisateur.
- [ ] Un protocole ou banc d'essai valide l'ingestion réelle d'un extrait de document produisant un graphe non vide (critère C3 : ≥ 5 nœuds, ≥ 3 arêtes) sous Neo4j local.
- [ ] Filet global de tests maintenu au vert (≥ 601 tests verts).
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement.

## Tâches

- [ ] Auditer le pipeline d'ingestion de `GraphBuilderService` et vérifier l'alignement des callbacks et de la sérialisation des batches avec `GraphitiGraphStore`.
- [ ] Vérifier la robustesse des callbacks de progression (`remember_graph`, `remember_batch`, `add_progress_callback`, `wait_progress_callback`) lors de l'exécution dans le thread de fond de `graph.py`.
- [ ] Écrire la suite de tests unitaires hermétiques simulant le cycle de vie complet de construction de graphe avec `GraphitiGraphStore` mocké.
- [ ] Écrire et exécuter le protocole de vérification d'ingestion réelle contre Neo4j local et OpenCode Go (validation du critère C3).
- [ ] Valider l'intégrité de la suite globale (`uv run pytest tests/ -q`), le lint (`uv run ruff check .`) et la structure de planification (`uv run python scripts/validate_plans.py`).

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

- **Couche Contrat & Architecture** : À compléter lors de la revue BMad.
- **Couche Hermétisme & Sécurité** : À compléter lors de la revue BMad.
- **Couche Tests & Qualité** : À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
