---
id: "004-2"
epic: "004"
titre: "Levée des gardes ZEP_API_KEY dans les routes API et les services métiers"
statut: backlog
auteur: agent
format: "2"
---

# Story 004-2 — Levée des gardes ZEP_API_KEY dans les routes API et les services métiers

## Définition de prêt

- [ ] Objectif compris : lever les gardes bloquants sur `ZEP_API_KEY` dans les routes API (`backend/app/api/graph.py`, `backend/app/api/simulation.py`) et assouplir les services métiers pour que MiroFish fonctionne à 100 % sans clé Zep lorsque `ZEP_BACKEND='graphiti'`, tout en préservant le contrôle d'erreur lorsque `ZEP_BACKEND='cloud'`.
- [ ] Documents consultés : [PRD](prd.md), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/app/config.py`](file:///Users/simon/dev/MiroFish/backend/app/config.py), [`backend/app/api/graph.py`](file:///Users/simon/dev/MiroFish/backend/app/api/graph.py), [`backend/app/api/simulation.py`](file:///Users/simon/dev/MiroFish/backend/app/api/simulation.py), [`backend/app/services/graph_builder.py`](file:///Users/simon/dev/MiroFish/backend/app/services/graph_builder.py), [`backend/app/services/zep_entity_reader.py`](file:///Users/simon/dev/MiroFish/backend/app/services/zep_entity_reader.py), [`backend/app/utils/graph_store/factory.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graph_store/factory.py).
- [ ] Réversibilité et non-régression vérifiées : en mode `ZEP_BACKEND='cloud'`, l'absence de `ZEP_API_KEY` doit continuer de renvoyer l'erreur appropriée (NFR-1, C1). En mode `graphiti`, l'absence de clé est nominale et ne doit jamais bloquer.
- [ ] Stratégie de test identifiée : tests hermétiques des routes Flask et des services validant l'exécution sans clé Zep en mode `graphiti` et le rejet explicite en mode `cloud`.

## Définition de fini

- [ ] Les gardes `if not Config.ZEP_API_KEY:` dans `backend/app/api/graph.py` (notamment `/build`, `/data`, `/delete`) ne bloquent plus les requêtes lorsque `ZEP_BACKEND == 'graphiti'`.
- [ ] Les gardes `if not Config.ZEP_API_KEY:` dans `backend/app/api/simulation.py` (notamment `/entities/<graph_id>`, `/entities/<graph_id>/<entity_uuid>`, `/entities/<graph_id>/by-type/<entity_type>`) ne bloquent plus les requêtes lorsque `ZEP_BACKEND == 'graphiti'`.
- [ ] `GraphBuilderService` accepte formellement `api_key=None` et délègue l'instanciation du store à `get_graph_store(api_key=None)`.
- [ ] `ZepEntityReader`, `OasisProfileGenerator`, `ZepGraphMemoryManager` et `zep_tools` tolèrent l'absence de clé Zep en mode `graphiti`.
- [ ] Des tests de routes Flask vérifient le fonctionnement nominal sans clé en mode `graphiti` et l'erreur explicite en mode `cloud`.
- [ ] Filet global de tests maintenu au vert (≥ 577 tests).
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement.

## Tâches

- [ ] Définir un helper de conditionnement ou conditionner les gardes de clé au backend actif (`ZEP_BACKEND == 'cloud'`) dans `backend/app/api/graph.py`.
- [ ] Conditionner les gardes de clé au backend actif dans `backend/app/api/simulation.py`.
- [ ] Aligner les instanciations de `GraphBuilderService` dans `backend/app/api/graph.py` pour transmettre `Config.ZEP_API_KEY` sans exiger sa présence lorsque le store Graphiti est actif.
- [ ] Vérifier la robustesse de `ZepEntityReader` et des générateurs lors de l'initialisation sans `ZEP_API_KEY`.
- [ ] Écrire la suite de tests unitaires et d'API dédiée validant le comportement des routes avec et sans `ZEP_API_KEY` pour les deux backends.
- [ ] Valider la suite de tests complète (`uv run pytest tests/ -q`), le lint (`uv run ruff check .`) et la conformité des plans (`uv run python scripts/validate_plans.py`).

## Notes de développement

Dans l'architecture historique héritée de MiroFish, le SDK Zep Cloud était supposé universellement disponible. Plusieurs routes API bloquaient immédiatement la requête avec un code HTTP 500 ou 400 (`api.zepApiKeyMissing`) si `Config.ZEP_API_KEY` était absent ou vide.

Depuis la mise en place de l'interface `GraphStore` (Epic 002) et de `GraphitiGraphStore` (Epic 003), le backend de graphe peut opérer en mode 100 % local sans aucun compte ni clé cloud Zep.

La factory `get_graph_store()` sait déjà instancier `GraphitiGraphStore()` sans clé lorsque `ZEP_BACKEND='graphiti'`. La levée des gardes inconditionnels dans l'API et les services métier permet d'ouvrir ce chemin sans régression pour les utilisateurs de Zep Cloud (qui restent protégés par le contrôle lorsque `ZEP_BACKEND='cloud'`).

## Revue

- **Couche Contrat & Architecture** : À compléter lors de la revue BMad.
- **Couche Hermétisme & Sécurité** : À compléter lors de la revue BMad.
- **Couche Tests & Qualité** : À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
