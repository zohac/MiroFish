---
id: "002-1"
epic: "002"
titre: "Définition de l'interface GraphStore, des modèles de données neutres et des exceptions"
statut: done
auteur: agent
format: "2"
---

# Story 002-1 — Définition de l'interface GraphStore, des modèles de données neutres et des exceptions

## Pourquoi cette story

L'Epic 002 a pour mission d'abstraire l'accès au graphe de connaissances avant d'intégrer
Graphiti (ADR 0001 et AGENTS.md §2.1 : *« On abstrait avant de bifurquer »*).
Aujourd'hui, 10 composants du backend appellent directement le SDK propriétaire `zep-cloud==3.25.0`
et manipulent des types propriétaires ou des dictionnaires hétérogènes.

Pour découpler le domaine métier sans introduire de bifurcations conditionnelles
(`if zep else graphiti`), la première étape indispensable est de poser le contrat d'interface
formel et les structures de données neutres :
1. Les modèles de données (`GraphNode`, `GraphEdge`, `GraphSearchResult`, `EpisodeRecord`,
   `BatchSubmissionRecord`, `GraphInfo`) doivent encapsuler l'ensemble des données
   manipulées par MiroFish sans aucune fuite de concepts propriétaires Zep.
2. L'interface `GraphStore` (classe abstraite pure `abc.ABC`) doit couvrir l'intégralité
   des opérations requises : cycle de vie du graphe, ontologie, ingestion unitaire et par lots,
   synchronisation/attente, parcours, lecture de voisinage et recherche sémantique.
3. La hiérarchie d'exceptions agnostiques (`GraphStoreError`, `GraphNotFoundError`,
   `GraphConnectionError`, `GraphTimeoutError`, `GraphValidationError`) doit permettre
   d'isoler les appelants des erreurs HTTP et SDK spécifiques (`zep_cloud.NotFoundError`,
   `ApiError`, `httpx.TimeoutException`).

Cette story pose ces fondations dans le package technique `backend/app/utils/graph_store/`
(Clean Architecture stricte : `api → services → utils`), accompagnée d'une suite de tests
unitaires hermétiques validant la conformité du contrat via une implémentation de référence
minimale en mémoire (`FakeGraphStore`).

## Définition de prêt

- [x] Contrat d'interface et signatures des 14 méthodes documentés dans [`architecture.md`](architecture.md) §3
- [x] Modèles de données neutres et méthodes de conversion spécifiés dans [`architecture.md`](architecture.md) §2
- [x] Hiérarchie d'exceptions spécifiée dans [`architecture.md`](architecture.md) §4
- [x] Critères de sortie C1 du PRD ([`prd.md`](prd.md)) pris en compte
- [x] Dépendances vers l'intérieur vérifiées : `app/utils/graph_store/` n'importe aucun module de `services/` ou `api/`
- [x] Zéro dépendance vers `zep-cloud` dans `base.py` et `errors.py`
- [x] Documents à consulter lus — [`epic-002.md`](epic-002.md), [`prd.md`](prd.md), [`architecture.md`](architecture.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md)

## Définition de fini

- [x] Le sous-package `backend/app/utils/graph_store/` est initialisé avec `__init__.py`
- [x] Le fichier `backend/app/utils/graph_store/errors.py` définit `GraphStoreError` et ses spécialisations (`GraphNotFoundError`, `GraphConnectionError`, `GraphTimeoutError`, `GraphValidationError`)
- [x] Le fichier `backend/app/utils/graph_store/base.py` implémente les dataclasses neutres `GraphNode`, `GraphEdge`, `GraphSearchResult`, `EpisodeRecord`, `BatchSubmissionRecord` et `GraphInfo`
- [x] Les méthodes utilitaires des modèles (`to_dict()`, `get_entity_type()`, `is_expired()`, `is_invalid()`, `to_text()`) sont implémentées et garantissent la rétrocompatibilité
- [x] La classe abstraite `GraphStore(ABC)` dans `base.py` définit les 14 méthodes abstraites formellement typées avec docstrings exhaustives
- [x] `backend/app/utils/graph_store/__init__.py` exporte proprement l'interface, les modèles et les exceptions
- [x] Aucun import de `zep_cloud` n'existe dans `backend/app/utils/graph_store/` (hors future `zep_store.py` de la story 002-2)
- [x] Une suite de tests unitaires hermétiques `backend/tests/test_graph_store_contract.py` teste l'instanciation de l'interface, un `FakeGraphStore`, les modèles neutres et les exceptions
- [x] Tous les tests existants (333 tests) restent 100 % au vert (`uv run pytest tests/ -q`)
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Créer le répertoire `backend/app/utils/graph_store/`
- [x] Implémenter la hiérarchie d'exceptions dans `backend/app/utils/graph_store/errors.py`
- [x] Implémenter les dataclasses neutres et l'interface abstraite `GraphStore` dans `backend/app/utils/graph_store/base.py`
- [x] Exposer les symboles publics dans `backend/app/utils/graph_store/__init__.py`
- [x] Créer la suite de tests `backend/tests/test_graph_store_contract.py`
  - [x] Test d'instanciation impossible de `GraphStore` direct (TypeError sur ABC)
  - [x] Test d'implémentation complète avec `FakeGraphStore` en mémoire
  - [x] Tests unitaires de `GraphNode` (`to_dict`, `get_entity_type`, immutabilité `frozen=True`)
  - [x] Tests unitaires de `GraphEdge` (`to_dict`, gestion temporelle `valid_at`, `expired_at`, drapeaux `is_expired`, `is_invalid`)
  - [x] Tests unitaires de `GraphSearchResult` (`to_dict`, `to_text` pour prompt LLM)
  - [x] Tests unitaires de `EpisodeRecord`, `BatchSubmissionRecord` et `GraphInfo`
  - [x] Tests unitaires de la hiérarchie d'héritage de `GraphStoreError`
  - [x] Test de pureté architecturale : absence de dépendance `zep_cloud` dans les modules de base
- [x] Valider la suite de tests globale (≥ 333 tests verts)
- [x] Exécuter `ruff check` et `validate_plans.py`

## Notes de développement

- **Conception Clean Architecture** :
  `base.py` et `errors.py` représentent le contrat pur. Ils ne dépendent d'aucun module tiers lourd
  (uniquement la bibliothèque standard Python : `abc`, `dataclasses`, `typing`).
- **Rétrocompatibilité avec [zep_entity_reader.py](../../backend/app/services/zep_entity_reader.py)** :
  `GraphNode` fournit `related_edges`, `related_nodes` et `get_entity_type()` pour permettre
  une substitution transparente d'`EntityNode` sans casser les dépendances aval.
- **Rétrocompatibilité avec [zep_tools.py](../../backend/app/services/zep_tools.py)** :
  `GraphSearchResult` fournit `to_text()` et `to_dict()`, et `GraphEdge` fournit `is_expired()`
  et `is_invalid()` qui correspondent exactement aux besoins du `ReportAgent`.
- **Pureté architecturale** :
  Un test automatisé par inspection d'arbre syntaxique (AST) vérifie qu'aucun import Zep n'apparaît
  dans les modules de base de `graph_store/`.

## Revue

Revue contradictoire menée par 4 couches indépendantes (*Blind Hunter*, *Edge Case Hunter*, *Verification Gap*, *Acceptance Auditor*).
Bilan du triage : 0 `decision-needed`, 7 `patch`, 0 `defer`, 0 rejeté.

### Constats de revue retenus (Patch)

- [x] [Review][Patch] Transformer `is_expired` et `is_invalid` en propriétés `@property` sur `GraphEdge` pour compatibilité stricte avec `zep_tools.py:1197` [`backend/app/utils/graph_store/base.py:86`]
- [x] [Review][Patch] Ajouter le paramètre optionnel `reranker: Optional[str] = None` à `GraphStore.search()` pour supporter le pilotage par les générateurs de personas et outils de rapport [`backend/app/utils/graph_store/base.py:385`]
- [x] [Review][Patch] Garantir la présence de `node_count`, `edge_count` et `graph_id` au premier niveau du dictionnaire retourné par `get_graph_data()` pour rétrocompatibilité avec `api/graph.py:775` [`backend/app/utils/graph_store/base.py:210`, `backend/tests/test_graph_store_contract.py:61`]
- [x] [Review][Patch] Étendre `GraphSearchResult.to_text()` pour formater les entités lorsque `facts` est vide mais que des nœuds sont présents [`backend/app/utils/graph_store/base.py:115`]
- [x] [Review][Patch] Ajouter la méthode `to_text()` sur `GraphNode` et `GraphEdge` pour parité avec `NodeInfo` et `EdgeInfo` [`backend/app/utils/graph_store/base.py:40`, `L94`]
- [x] [Review][Patch] Expliciter dans la docstring de `wait_for_batch` et `wait_for_episodes` que l'expiration du délai d'attente lève `GraphTimeoutError` [`backend/app/utils/graph_store/base.py:297`, `L315`]
- [x] [Review][Patch] Aligner le cycle de vie de la story dans `story-002-1.md` pour refléter l'étape de revue avant clôture formelle (AGENTS.md §2.8) [`docs/plans/002-interface-graphstore/story-002-1.md:5`]

### Rejets documentés

*Aucun constat rejeté : les 7 points soulevés par les couches de revue sont fondés sur des contrats de code existants ou la constitution.*

## Notes de complétion

La story 002-1 est achevée avec succès. Toutes les exigences ont été réalisées et validées par revue contradictoire à 4 couches :
- Création du package `backend/app/utils/graph_store/` avec `base.py`, `errors.py` et `__init__.py`.
- Zéro dépendance externe dans les contrats purs (uniquement standard library Python).
- 8 tests unitaires hermétiques validant le comportement contractuel complet via `FakeGraphStore` et garantissant l'isolation architecturale (AST).
- Suite de tests globale à 341 tests 100 % verts (+8 nouveaux tests, 0 régression).
- Revue contradictoire BMad passée : 7 correctifs (patch) appliqués avec succès (propriétés `@property` sur `GraphEdge`, `to_text()` sur `GraphNode`/`GraphEdge`, complétion de `GraphSearchResult.to_text()`, support de `reranker` dans `search()`, compteurs racine dans `get_graph_data()`, clarification `GraphTimeoutError` dans les docstrings).
- La base est prête pour l'implémentation concrète de `ZepGraphStore` dans la story 002-2.

