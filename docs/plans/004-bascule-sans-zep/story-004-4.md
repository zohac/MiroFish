---
id: "004-4"
epic: "004"
titre: "Extraction d'entités, génération de personas et configuration de simulation sans Zep"
statut: backlog
auteur: agent
format: "2"
---

# Story 004-4 — Extraction d'entités, génération de personas et configuration de simulation sans Zep

## Définition de prêt

- [ ] Objectif compris : orchestrer et valider l'extraction d'entités depuis le graphe local `GraphitiGraphStore`, la génération de personas OASIS (Reddit / Twitter) et la production de la configuration de simulation multi-agents sans clé ni dépendance Zep Cloud.
- [ ] Documents consultés : [PRD](prd.md) (notamment critère C4 et FR-5), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/app/services/zep_entity_reader.py`](file:///Users/simon/dev/MiroFish/backend/app/services/zep_entity_reader.py), [`backend/app/services/oasis_profile_generator.py`](file:///Users/simon/dev/MiroFish/backend/app/services/oasis_profile_generator.py), [`backend/app/services/simulation_config_generator.py`](file:///Users/simon/dev/MiroFish/backend/app/services/simulation_config_generator.py), [`backend/app/services/simulation_manager.py`](file:///Users/simon/dev/MiroFish/backend/app/services/simulation_manager.py), [`backend/app/api/simulation.py`](file:///Users/simon/dev/MiroFish/backend/app/api/simulation.py).
- [ ] Prérequis vérifiés : Stories 004-1 (LLM universel), 004-2 (levée des gardes ZEP_API_KEY) et 004-3 (ingestion et construction de graphe e2e) validées et closes (614 tests verts). Instance Neo4j locale opérationnelle.
- [ ] Stratégie de test identifiée : tests unitaires hermétiques simulant l'extraction d'entités et la génération de profils personas / config de simulation avec store local mocké, et banc d'épreuve validant la production d'au moins 3 personas typés (critère C4).

## Définition de fini

- [ ] `ZepEntityReader` extrait les entités et relations typées depuis `GraphitiGraphStore` en local sans lever d'exception liée à Zep Cloud ou `ZEP_API_KEY`.
- [ ] `SimulationConfigGenerator` génère une configuration de simulation valide (`simulation_config.json`) paramétrée pour le modèle LLM local configuré.
- [ ] `OasisProfileGenerator` génère au moins 3 personas typés enrichis par les données du graphe local (`reddit_profiles.json`, `twitter_profiles.csv`), satisfaisant formellement le critère C4 du PRD.
- [ ] La route `POST /api/simulation/create` initialise la simulation et prépare ses artefacts sans exigence de clé Zep Cloud.
- [ ] Filet global de tests maintenu au vert (≥ 614 tests verts).
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement.

## Tâches

- [ ] Auditer `zep_entity_reader.py`, `oasis_profile_generator.py` et `simulation_config_generator.py` pour valider l'étanchéité des flux de lecture et d'enrichissement avec `GraphitiGraphStore`.
- [ ] Vérifier la transmission et l'exploitation des labels d'entités (`:Entity` et types d'ontologie) et des arêtes lors de l'instanciation des personas et de leurs prompts système.
- [ ] Écrire la suite de tests unitaires hermétiques couvrant la génération de configuration et de personas avec un `GraphStore` local mocké.
- [ ] Écrire et exécuter le protocole de vérification de génération de personas sur graphe local (validation du critère C4 : ≥ 3 personas typés).
- [ ] Valider l'intégrité de la suite globale (`uv run pytest tests/ -q`), le lint (`uv run ruff check .`) et la structure de planification (`uv run python scripts/validate_plans.py`).

## Notes de développement

La Story 004-4 réalise le pont entre le graphe de connaissances local construit lors de la Story 004-3 et le moteur de simulation multi-agents `camel-oasis`.

Dans l'architecture MiroFish originale, la préparation de simulation interrogeait Zep Cloud pour extraire les nœuds et arêtes d'un graphe, puis synthétisait des profils d'agents (personas) dotés de personnalités, de rôles et de mémoires initiales basées sur les faits du graphe.
Avec `GraphitiGraphStore` désormais opérationnel et les entités persistées dans Neo4j local, la Story 004-4 assure :
1. L'extraction fiable des entités et relations par `ZepEntityReader` via le contrat abstrait `GraphStore`.
2. La déduction de la configuration de simulation (`SimulationConfigGenerator`) : nombre de tours, plateformes actives (Twitter / Reddit), dynamique sociale.
3. La génération des personas (`OasisProfileGenerator`) : création des profils JSON et CSV reflétant les nœuds du graphe.
4. La satisfaction du critère C4 du PRD : génération d'au moins 3 personas typés sans aucun appel ni clé Zep Cloud.

## Revue

- **Couche Contrat & Architecture** : À compléter lors de la revue BMad.
- **Couche Hermétisme & Sécurité** : À compléter lors de la revue BMad.
- **Couche Tests & Qualité** : À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
