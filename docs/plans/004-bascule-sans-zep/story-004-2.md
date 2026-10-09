---
id: "004-2"
epic: "004"
titre: "Levée des gardes ZEP_API_KEY dans les routes API et les services métiers"
statut: done
auteur: agent
format: "2"
---

# Story 004-2 — Levée des gardes ZEP_API_KEY dans les routes API et les services métiers

## Définition de prêt

- [x] Objectif compris : lever les gardes bloquants sur `ZEP_API_KEY` dans les routes API (`backend/app/api/graph.py`, `backend/app/api/simulation.py`) et assouplir les services métiers pour que MiroFish fonctionne à 100 % sans clé Zep lorsque `ZEP_BACKEND='graphiti'`, tout en préservant le contrôle d'erreur lorsque `ZEP_BACKEND='cloud'`.
- [x] Documents consultés : [PRD](prd.md), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/app/config.py`](file:///Users/simon/dev/MiroFish/backend/app/config.py), [`backend/app/api/graph.py`](file:///Users/simon/dev/MiroFish/backend/app/api/graph.py), [`backend/app/api/simulation.py`](file:///Users/simon/dev/MiroFish/backend/app/api/simulation.py), [`backend/app/services/graph_builder.py`](file:///Users/simon/dev/MiroFish/backend/app/services/graph_builder.py), [`backend/app/services/zep_entity_reader.py`](file:///Users/simon/dev/MiroFish/backend/app/services/zep_entity_reader.py), [`backend/app/utils/graph_store/factory.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graph_store/factory.py).
- [x] Réversibilité et non-régression vérifiées : en mode `ZEP_BACKEND='cloud'`, l'absence de `ZEP_API_KEY` doit continuer de renvoyer l'erreur appropriée (NFR-1, C1). En mode `graphiti`, l'absence de clé est nominale et ne doit jamais bloquer.
- [x] Stratégie de test identifiée : tests hermétiques des routes Flask et des services validant l'exécution sans clé Zep en mode `graphiti` et le rejet explicite en mode `cloud`.

## Définition de fini

- [x] Les gardes `if not Config.ZEP_API_KEY:` dans `backend/app/api/graph.py` (notamment `/build`, `/data`, `/delete`) ne bloquent plus les requêtes lorsque `ZEP_BACKEND == 'graphiti'`.
- [x] Les gardes `if not Config.ZEP_API_KEY:` dans `backend/app/api/simulation.py` (notamment `/entities/<graph_id>`, `/entities/<graph_id>/<entity_uuid>`, `/entities/<graph_id>/by-type/<entity_type>`) ne bloquent plus les requêtes lorsque `ZEP_BACKEND == 'graphiti'`.
- [x] `GraphBuilderService` accepte formellement `api_key=None` et délègue l'instanciation du store à `get_graph_store(api_key=None)`.
- [x] `ZepEntityReader`, `OasisProfileGenerator`, `ZepGraphMemoryManager` et `zep_tools` tolèrent l'absence de clé Zep en mode `graphiti`.
- [x] Des tests de routes Flask vérifient le fonctionnement nominal sans clé en mode `graphiti` et l'erreur explicite en mode `cloud`.
- [x] Filet global de tests maintenu au vert (≥ 577 tests).
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement.

## Tâches

- [x] Définir un helper de conditionnement ou conditionner les gardes de clé au backend actif (`ZEP_BACKEND == 'cloud'`) dans `backend/app/api/graph.py`.
- [x] Conditionner les gardes de clé au backend actif dans `backend/app/api/simulation.py`.
- [x] Aligner les instanciations de `GraphBuilderService` dans `backend/app/api/graph.py` pour transmettre `Config.ZEP_API_KEY` sans exiger sa présence lorsque le store Graphiti est actif.
- [x] Vérifier la robustesse de `ZepEntityReader` et des générateurs lors de l'initialisation sans `ZEP_API_KEY`.
- [x] Écrire la suite de tests unitaires et d'API dédiée validant le comportement des routes avec et sans `ZEP_API_KEY` pour les deux backends.
- [x] Valider la suite de tests complète (`uv run pytest tests/ -q`), le lint (`uv run ruff check .`) et la conformité des plans (`uv run python scripts/validate_plans.py`).

### Review Findings

- [x] [Review][Patch] Robustesse fail-closed de Config.requires_zep_api_key() face aux valeurs vides ou invalides [backend/app/config.py:90]
- [x] [Review][Patch] Complétude des tests unitaires de casse et de robustesse de requires_zep_api_key [backend/tests/test_zep_api_key_guards.py:445]
- [x] [Review][Patch] Tests symétriques en mode cloud sans clé pour ZepEntityReader, ZepGraphMemoryUpdater et ZepToolsService [backend/tests/test_zep_api_key_guards.py:718]

#### Rejected

- [Nommage résiduel _delete_cloud_graph_if_present dans graph.py] : rejeté (`low`) — Helper interne privé sans impact sur le contrat d'API ni risque de régression.
- [Docstring de la route /delete/<graph_id> mentionnant spécifiquement Zep] : rejeté (`low`) — Commentaire informatif en chinois, non contractuel.
- [Initialisation de api_key dans GraphBuilderService.__init__] : rejeté (`false`) — Réfuté, l'évaluation de repli `api_key or Config.ZEP_API_KEY` fonctionne de manière idiomatique.

## Notes de développement

Dans l'architecture historique héritée de MiroFish, le SDK Zep Cloud était supposé universellement disponible. Plusieurs routes API bloquaient immédiatement la requête avec un code HTTP 500 ou 400 (`api.zepApiKeyMissing`) si `Config.ZEP_API_KEY` était absent ou vide.

Depuis la mise en place de l'interface `GraphStore` (Epic 002) et de `GraphitiGraphStore` (Epic 003), le backend de graphe peut opérer en mode 100 % local sans aucun compte ni clé cloud Zep.

La méthode helper `Config.requires_zep_api_key()` a été introduite dans `backend/app/config.py` et intégrée dans `Config.validate()` : elle n'exige la clé que si le backend configuré est `'cloud'`.

Dans les routes API (`backend/app/api/graph.py` et `backend/app/api/simulation.py`), les gardes inconditionnels ont été remplacés par `if Config.requires_zep_api_key() and not Config.ZEP_API_KEY:`. Ainsi, en mode `graphiti`, aucune clé n'est demandée, tandis qu'en mode `cloud`, la protection d'erreur existante (HTTP 500 `api.zepApiKeyMissing`) reste parfaitement active.

Dans `backend/app/services/graph_builder.py`, `__init__` a été clarifié et documenté pour expliciter que `api_key` est facultatif et délègue dynamiquement à `get_graph_store()`.

Une suite de 24 tests unitaires et d'API dédiée (`backend/tests/test_zep_api_key_guards.py`) a été ajoutée pour verrouiller le comportement des deux modes.

## Revue

- **Couche Contrat & Architecture** : Validée. Zéro import direct de SDK cloud dans les services et routes API (confirmé par `test_graph_store_isolation.py`). Aucune bifurcation `if zep else graphiti` dans les services. La logique de conditionnement est centralisée dans `Config.requires_zep_api_key()` selon les principes Clean Architecture et DRY, avec comportement fail-closed sécurisé.
- **Couche Hermétisme & Sécurité** : Validée. Aucun secret ni token dans le code. Les tests unitaires utilisent `monkeypatch` et `override_graph_store` avec `DummyStore` en mémoire, garantissant une étanchéité totale vis-à-vis du réseau et des fichiers `.env`.
- **Couche Tests & Qualité** : Validée. 24 tests spécifiques couvrant tous les cas de garde pour `graph.py`, `simulation.py`, `Config` et les 5 services métiers (y compris les rejets symétriques sans clé en mode cloud). Filet global de tests porté de 577 à 601 tests 100 % verts. Linter `ruff check .` impeccable.

## Notes de complétion

La Story 004-2 est achevée avec succès :
1. **Helper centralisé et non-régression** : `Config.requires_zep_api_key()` isole le contrôle d'exigence de la clé Zep avec comportement fail-closed. Le mode `cloud` continue d'exiger `ZEP_API_KEY` (avec erreur explicite si manquante), tandis que le mode `graphiti` fonctionne sans clé Zep.
2. **Levée des gardes API** :
   - `backend/app/api/graph.py` : `/build`, `/data/<graph_id>` et `/delete/<graph_id>` ne bloquent plus les requêtes sans clé Zep en mode `graphiti`.
   - `backend/app/api/simulation.py` : `/entities/<graph_id>`, `/entities/<graph_id>/<entity_uuid>` et `/entities/<graph_id>/by-type/<entity_type>` acceptent les requêtes sans clé Zep en mode `graphiti`.
3. **Services métiers agnostiques** : `GraphBuilderService`, `ZepEntityReader`, `OasisProfileGenerator`, `ZepGraphMemoryUpdater` et `ZepToolsService` s'instancient sans exiger de clé et résolvent le store local via `get_graph_store()`.
4. **Validation et qualité** :
   - 24 tests unitaires et d'API hermétiques créés dans `backend/tests/test_zep_api_key_guards.py`.
   - Filet global de tests porté de 577 à **601 tests 100 % verts** (+24 tests).
   - Contrôle d'isolation AST `tests/test_graph_store_isolation.py` 100 % vert (0 import Zep direct dans services/ et api/, 0 bifurcation conditionnelle).
   - Linter `ruff check .` et validateur de plans `validate_plans.py` impeccables.
