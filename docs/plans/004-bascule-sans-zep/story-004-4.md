---
id: "004-4"
epic: "004"
titre: "Extraction d'entités, génération de personas et configuration de simulation sans Zep"
statut: done
auteur: agent
format: "2"
---

# Story 004-4 — Extraction d'entités, génération de personas et configuration de simulation sans Zep

## Définition de prêt

- [x] Objectif compris : orchestrer et valider l'extraction d'entités depuis le graphe local `GraphitiGraphStore`, la génération de personas OASIS (Reddit / Twitter) et la production de la configuration de simulation multi-agents sans clé ni dépendance Zep Cloud.
- [x] Documents consultés : [PRD](prd.md) (notamment critère C4 et FR-5), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/app/services/zep_entity_reader.py`](file:///Users/simon/dev/MiroFish/backend/app/services/zep_entity_reader.py), [`backend/app/services/oasis_profile_generator.py`](file:///Users/simon/dev/MiroFish/backend/app/services/oasis_profile_generator.py), [`backend/app/services/simulation_config_generator.py`](file:///Users/simon/dev/MiroFish/backend/app/services/simulation_config_generator.py), [`backend/app/services/simulation_manager.py`](file:///Users/simon/dev/MiroFish/backend/app/services/simulation_manager.py), [`backend/app/api/simulation.py`](file:///Users/simon/dev/MiroFish/backend/app/api/simulation.py).
- [x] Prérequis vérifiés : Stories 004-1 (LLM universel), 004-2 (levée des gardes ZEP_API_KEY) et 004-3 (ingestion et construction de graphe e2e) validées et closes (614 tests verts). Instance Neo4j locale opérationnelle.
- [x] Stratégie de test identifiée : tests unitaires hermétiques simulant l'extraction d'entités et la génération de profils personas / config de simulation avec store local mocké, et banc d'épreuve validant la production d'au moins 3 personas typés (critère C4).

## Définition de fini

- [x] `ZepEntityReader` extrait les entités et relations typées depuis `GraphitiGraphStore` en local sans lever d'exception liée à Zep Cloud ou `ZEP_API_KEY`.
- [x] `SimulationConfigGenerator` génère une configuration de simulation valide (`simulation_config.json`) paramétrée pour le modèle LLM local configuré.
- [x] `OasisProfileGenerator` génère au moins 3 personas typés enrichis par les données du graphe local (`reddit_profiles.json`, `twitter_profiles.csv`), satisfaisant formellement le critère C4 du PRD.
- [x] La route `POST /api/simulation/create` initialise la simulation et prépare ses artefacts sans exigence de clé Zep Cloud.
- [x] Filet global de tests maintenu au vert (622 tests verts, ≥ 614 tests exigés).
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement.

## Tâches

- [x] Auditer `zep_entity_reader.py`, `oasis_profile_generator.py` et `simulation_config_generator.py` pour valider l'étanchéité des flux de lecture et d'enrichissement avec `GraphitiGraphStore`.
- [x] Vérifier la transmission et l'exploitation des labels d'entités (`:Entity` et types d'ontologie) et des arêtes lors de l'instanciation des personas et de leurs prompts système.
- [x] Écrire la suite de tests unitaires hermétiques couvrant la génération de configuration et de personas avec un `GraphStore` local mocké.
- [x] Écrire et exécuter le protocole de vérification de génération de personas sur graphe local (validation du critère C4 : ≥ 3 personas typés).
- [x] Valider l'intégrité de la suite globale (`uv run pytest tests/ -q`), le lint (`uv run ruff check .`) et la structure de planification (`uv run python scripts/validate_plans.py`).

### Review Findings

- [x] [Review][Patch] Encapsulation GraphStore et fiabilisation du nettoyage dans verifier_personas_simulation_graphiti.py [backend/scripts/verifier_personas_simulation_graphiti.py:210,224,370]
- [x] [Review][Patch] Remplacement du monkeypatch __init__ par override_graph_store dans les tests unitaires [backend/tests/test_personas_simulation_graphiti.py:363]
- [x] [Review][Patch] Tests hermétiques d'échec du banc de vérification et cas d'erreur de la route /api/simulation/create [backend/tests/test_verifier_personas_protocol.py:35, backend/tests/test_personas_simulation_graphiti.py:411]
- [x] [Review][Patch] Nettoyage de code mort et fiabilisation des arguments CLI dans verifier_personas_simulation_graphiti.py [backend/scripts/verifier_personas_simulation_graphiti.py:272,405]

#### Rejected

- [IndexError potentiel sur twitter_rows[0]] : rejeté (`false`) — Réfuté par la garde `assert len(twitter_rows) >= 3` immédiatement antérieure.

## Notes de développement

La Story 004-4 réalise le pont entre le graphe de connaissances local construit lors de la Story 004-3 et le moteur de simulation multi-agents `camel-oasis`.

Dans l'architecture MiroFish originale, la préparation de simulation interrogeait Zep Cloud pour extraire les nœuds et arêtes d'un graphe, puis synthétisait des profils d'agents (personas) dotés de personnalités, de rôles et de mémoires initiales basées sur les faits du graphe.
Avec `GraphitiGraphStore` désormais opérationnel et les entités persistées dans Neo4j local, la Story 004-4 assure :
1. L'extraction fiable des entités et relations par `ZepEntityReader` via le contrat abstrait `GraphStore`.
2. La déduction de la configuration de simulation (`SimulationConfigGenerator`) : nombre de tours, plateformes actives (Twitter / Reddit), dynamique sociale.
3. La génération des personas (`OasisProfileGenerator`) : création des profils JSON et CSV reflétant les nœuds du graphe.
4. La satisfaction du critère C4 du PRD : génération d'au moins 3 personas typés sans aucun appel ni clé Zep Cloud.

## Revue

- **Couche Contrat & Architecture** : Validée. `ZepEntityReader`, `OasisProfileGenerator` et `SimulationConfigGenerator` dialoguent exclusivement avec l'interface neutre `GraphStore`. Aucune conditionnelle `if zep else graphiti` n'existe dans ces services. Le banc de test `verifier_personas_simulation_graphiti.py` utilise strictement le contrat public `store.add_episode()` et l'injection officielle `override_graph_store()`.
- **Couche Hermétisme & Sécurité** : Validée. 0 clé `ZEP_API_KEY` exigée en mode `ZEP_BACKEND='graphiti'`. Les tests unitaires s'exécutent de façon 100 % hermétique avec `InMemoryMockStore`, `override_graph_store` et des mocks LLM sans appel réseau externe. La restauration de `Config.ZEP_BACKEND` et `Config.ZEP_API_KEY` dans le bloc `finally` est garantie même en cas d'erreur de fermeture du store.
- **Couche Tests & Qualité** : Validée. 10 nouveaux tests unitaires automatisés ajoutés dans `test_personas_simulation_graphiti.py` et `test_verifier_personas_protocol.py` (filet global : 624 tests verts). Le banc de qualification `backend/scripts/verifier_personas_simulation_graphiti.py` s'exécute avec succès contre Neo4j local et valide formellement le critère C4 du PRD (4 personas typés générés, formats Reddit JSON et Twitter CSV conformes, `simulation_config.json` valide). Les 4 patchs de revue BMad ont été intégrés et validés.

## Notes de complétion

- **Livrables produits** :
  1. Banc d'épreuve et de qualification réel : `backend/scripts/verifier_personas_simulation_graphiti.py`.
  2. Suite de tests unitaires hermétiques : `backend/tests/test_personas_simulation_graphiti.py`.
  3. Suite de tests de protocole et client LLM mocké : `backend/tests/test_verifier_personas_protocol.py`.
- **Validation du critère C4 du PRD** :
  - `C4_extraction_entites_reussie` : Validé (extraction de 4 entités typées avec relations et faits).
  - `C4_seuil_personas_atteint` : Validé (4 personas générés, seuil exigé ≥ 3).
  - `C4_format_reddit_json_valide` : Validé (`reddit_profiles.json` conforme avec `user_id`, `username`, `name`, `bio`, `persona`, `gender`, `mbti`).
  - `C4_format_twitter_csv_valide` : Validé (`twitter_profiles.csv` conforme aux en-têtes OASIS `user_id`, `name`, `username`, `user_char`, `description`).
  - `C4_config_simulation_valide` : Validé (`simulation_config.json` produit avec `time_config`, `agent_configs`, `event_config`, `twitter_config`, `reddit_config`).
  - `C4_zero_cle_zep_exigee` : Validé (0 appel / 0 clé Zep exigée).
  - `C4_nettoyage_propre` : Validé (purge systématique du graphe et des répertoires temporaires).
- **Métriques qualité** :
  - 624 tests pytest au vert (0 échec, 0 régression).
  - Linter Ruff 100 % conforme (`All checks passed!`).
  - Validateur de planification `validate_plans.py` conforme.
