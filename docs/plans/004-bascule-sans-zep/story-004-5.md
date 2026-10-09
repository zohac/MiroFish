---
id: "004-5"
epic: "004"
titre: "Banc de qualification globale local-first et clôture de l'Epic 004"
statut: done
auteur: agent
format: "2"
---

# Story 004-5 — Banc de qualification globale local-first et clôture de l'Epic 004

## Définition de prêt

- [x] Objectif compris : concevoir, exécuter et consigner le banc d'épreuve de qualification globale validant le flux applicatif complet de bout en bout (documents → graphe local Neo4j → personas OASIS → simulation multi-agents → rapport) sans Zep Cloud, et clore formellement l'Epic 004.
- [x] Documents consultés : [PRD](prd.md) (notamment critères de sortie C1 à C5), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/scripts/verifier_ingestion_graphiti.py`](file:///Users/simon/dev/MiroFish/backend/scripts/verifier_ingestion_graphiti.py), [`backend/scripts/verifier_personas_simulation_graphiti.py`](file:///Users/simon/dev/MiroFish/backend/scripts/verifier_personas_simulation_graphiti.py), [`backend/app/services/simulation_manager.py`](file:///Users/simon/dev/MiroFish/backend/app/services/simulation_manager.py), [`backend/app/services/simulation_runner.py`](file:///Users/simon/dev/MiroFish/backend/app/services/simulation_runner.py).
- [x] Prérequis vérifiés : Stories 004-1 (LLM universel), 004-2 (levée des gardes ZEP_API_KEY), 004-3 (ingestion et graphe e2e) et 004-4 (personas et simulation e2e) validées et closes (624 tests verts). Instance Neo4j locale opérationnelle (`docker-compose.neo4j.yml`).
- [x] Stratégie de test identifiée : script de qualification globale automatisé (`backend/scripts/verifier_qualification_local_first.py`) orchestrant le cycle de vie complet, tests unitaires hermétiques associés, rapport de synthèse consolidé validant 100 % des critères C1 à C5 du PRD.

## Définition de fini

- [x] Un script de qualification de bout en bout (`backend/scripts/verifier_qualification_local_first.py`) valide l'intégralité du cycle local-first sans aucune variable `ZEP_API_KEY`.
- [x] Les 5 critères de sortie du PRD sont formellement satisfaits et mesurés :
  - C1 : 0 blocage lié à `ZEP_API_KEY` sur les routes de l'API (`api/graph.py`, `api/simulation.py`).
  - C2 : Paramétrabilité LLM universelle opérationnelle avec OpenCode Go / modèles locaux, 0 en-tête propriétaire hors `opencode.ai`.
  - C3 : Graphe de connaissances construit dans Neo4j avec ≥ 5 nœuds et ≥ 3 arêtes.
  - C4 : Extraction et génération d'au moins 3 personas typés (Reddit JSON et Twitter CSV conformes OASIS).
  - C5 : Filet global de tests maintenu au vert (≥ 624 tests verts).
- [x] Suite de tests unitaires hermétiques validant le comportement du script de qualification et son formatage de rapport.
- [x] Rapport de validation finale rédigé et versionné (`docs/plans/004-bascule-sans-zep/rapport-qualification-epic-004.md`).
- [x] `docs/STATUS.md`, `AGENTS.md` et `docs/sprint-status.yaml` mis à jour pour acter la clôture de l'Epic 004.
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement.

## Tâches

- [x] Concevoir le banc de qualification globale `backend/scripts/verifier_qualification_local_first.py` chaînant ingestion de document, extraction, personas et initialisation de simulation.
- [x] Ajouter les options CLI d'exécution (`--mock-llm`, `--real-llm`, `--keep-graph`, `--keep-artifacts`) et la purge étanche systématique des ressources de test.
- [x] Écrire la suite de tests unitaires hermétiques couvrant le protocole de qualification globale (`backend/tests/test_verifier_qualification_protocol.py`).
- [x] Exécuter le banc de qualification contre Neo4j local et consigner les résultats dans `docs/plans/004-bascule-sans-zep/rapport-qualification-epic-004.md`.
- [x] Réaliser la revue contradictoire BMad (4 couches) et appliquer les correctifs nécessaires.
- [x] Synchroniser la documentation d'état et acter la clôture de l'Epic 004 dans `sprint-status.yaml` et `STATUS.md`.

## Notes de développement

La Story 004-5 représente le point d'orgue de l'Epic 004 (« Construire un graphe en local sans clé Zep »).

Après les étapes de socle technique :
1. Story 004-1 : paramétrabilité universelle du LLM et isolation des en-têtes.
2. Story 004-2 : levée des gardes bloquants `ZEP_API_KEY` dans l'API et les services.
3. Story 004-3 : ingestion et construction de graphe de bout en bout avec `GraphitiGraphStore`.
4. Story 004-4 : extraction d'entités, personas OASIS et configuration de simulation sans Zep.

La Story 004-5 rassemble l'ensemble de ces briques au sein d'un banc de qualification unique et reproductible, vérifiant la promesse fondatrice du mode « local-first » :
**documents bruts → graphe de connaissances Neo4j → personas crédibles → configuration de simulation multi-agents → rapport, sans aucun appel ni dépendance à un service cloud propriétaire (0 € de coût récurrent, 0 fuite de données).**

## Revue

- **Couche Contrat & Architecture** : Conforme aux principes de Clean Architecture. Les interfaces `GraphStore`, `TaskManager` et `SimulationManager` sont respectées sans injection de logique conditionnelle amont/aval (`if zep else graphiti`). Le cycle complet est orchestré de bout en bout avec `store=GraphitiGraphStore`.
- **Couche Hermétisme & Sécurité** : 0 fuite de secret (`ZEP_API_KEY=None`), neutralité stricte des en-têtes LLM (aucun en-tête propriétaire transmis hors `opencode.ai`), gestion de cycle de vie et purge complète du sous-graphe et des artefacts temporaires dans un bloc `finally` garanti. Ordre de bascule de l'indicateur `graph_cleaned_up` sécurisé après assertion de purge.
- **Couche Tests & Qualité** : Revue contradictoire BMad 4 couches réalisée avec 5 patchs intégrés (suppression du code mort sur le check 400 de C1, renforcement de l'assertion de raisonnement C2, conservation du préfixe `qualif-004-` dans `builder.create_graph`, sécurisation de l'indicateur de purge, et comblement du verification gap via tests unitaires d'échec de seuil de nœuds C3 et de sortie `--json`). Suite hermétique portée de 5 à 7 tests unitaires (`test_verifier_qualification_protocol.py`), filet global porté de 624 à 632 tests verts (+8 tests).

## Notes de complétion

La Story 004-5 et l'Epic 004 sont intégralement validés et clos avec succès :
1. **Script de qualification globale** : `backend/scripts/verifier_qualification_local_first.py` implémenté, revu contradictoirement (5 patchs BMad) et exécuté avec succès contre Neo4j local.
2. **Critères C1 à C5 formellement satisfaits** :
   - C1 : 100 % des routes de l'API Flask s'exécutent sans `ZEP_API_KEY` (`Config.requires_zep_api_key() == False`), absence de code 400 vérifiée.
   - C2 : Paramétrabilité LLM universelle (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT`) et neutralité d'hôte validées.
   - C3 : Graphe Neo4j réel construit (6 nœuds, 4 arêtes, partitionnement `group_id`).
   - C4 : 6 personas Reddit JSON et 6 personas Twitter CSV OASIS conformes générés avec `simulation_config.json` complet.
   - C5 : Filet global porté à 632 tests unitaires et d'intégration (100 % verts).
3. **Rapport de qualification finale** : Rédigé et consigné dans [`docs/plans/004-bascule-sans-zep/rapport-qualification-epic-004.md`](rapport-qualification-epic-004.md).
4. **Validations techniques** : `ruff check` et `validate_plans.py` passent avec 0 erreur.
