---
id: "003-1"
epic: "003"
titre: "Squelette de GraphitiGraphStore, initialisation des dépendances et activation dans la factory"
statut: done
auteur: agent
format: "2"
---

# Story 003-1 — Squelette de GraphitiGraphStore, initialisation des dépendances et activation dans la factory

## Pourquoi cette story

L'Epic 001 a prouvé que la chaîne locale Graphiti + Neo4j 5.26 + `all-MiniLM-L6-v2` + OpenCode Go fonctionne sans frais (Verdict GO validé). L'Epic 002 a ensuite posé l'interface neutre `GraphStore` et encapsulé l'implémentation existante `ZepGraphStore` (470 tests verts).

Cependant, à ce jour, la factory `get_graph_store(backend="graphiti")` levait une exception explicite `NotImplementedError` : aucun backend local n'était encore instanciable.

Pour concrétiser le support local-first sans régression et amorcer l'Epic 003 :
1. **Contrat d'interface C1** : `GraphitiGraphStore` doit hériter de la classe abstraite `GraphStore` et déclarer les 14 méthodes formelles du contrat pour être instanciable sans lever de `TypeError` Python (`Can't instantiate abstract class with abstract methods`). Les méthodes métier dont l'implémentation complète fait l'objet des stories 003-2 et 003-3 doivent être proprement stubbées avec des exceptions explicites.
2. **Assemblage des briques locales** : `GraphitiGraphStore` doit initialiser et connecter les composants éprouvés lors de l'Epic 001 :
   - Le driver Neo4j (`Neo4jDriver`) configuré avec les variables d'environnement (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`), avec support d'injection directe pour les tests ;
   - Le client LLM avec gestion de session et mode `json_object` (`MiroFishLLMClient` dans `backend/app/utils/graphiti_llm_client.py`) ;
   - L'embedder local `SentenceTransformerEmbedder` (`backend/app/utils/graphiti_embedder.py`, 384 dimensions) ;
   - Le cross-encoder local pass-through (`LocalPassthroughCrossEncoder`) interdisant tout appel externe ;
   - L'instance `Graphiti` configurée avec ces briques.
3. **Résolution de l'impédance Asynchrone / Synchrone** : `GraphStore` étant une interface synchrone alors que `graphiti-core` est nativement asynchrone (`async def`), `GraphitiGraphStore` doit intégrer un exécuteur de coroutines thread-safe (`_run_async`) évitant les collisions de boucle (`RuntimeError: This event loop is already running`) et préservant le pool de connexions du driver.
4. **Activation dans la factory** : La factory `get_graph_store()` (`backend/app/utils/graph_store/factory.py`) doit router `ZEP_BACKEND='graphiti'` vers `GraphitiGraphStore`, avec validation des paramètres et maintien du mécanisme d'override pour les tests.

Cette story pose le socle opérationnel dans `backend/app/utils/graph_store/graphiti_store.py`, accompagné d'une suite de tests unitaires hermétiques mockés (sans conteneur Neo4j requis).

## Définition de prêt

- [x] Contrat d'interface des 14 méthodes de `GraphStore` identifié dans [`base.py`](../../backend/app/utils/graph_store/base.py)
- [x] Composants de l'Epic 001 disponibles et testés : `MiroFishLLMClient`, `SentenceTransformerEmbedder`, override driver Neo4j 5.28.6
- [x] Problème d'impédance sync/async analysé : stratégie de pont de coroutines sans fuite de boucle identifiée
- [x] Critères de sortie C1, C5 et C6 du PRD ([`prd.md`](prd.md)) pris en compte
- [x] Règle de télémétrie locale rappelée : `GRAPHITI_TELEMETRY_ENABLED=false` respecté
- [x] Documents consultés : [`prd.md`](prd.md), [`architecture.md`](architecture.md), [`epic-003.md`](epic-003.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md), [ADR 0010](../../decisions/0010-override-driver-neo4j.md)

## Définition de fini

- [x] `backend/app/utils/graph_store/graphiti_store.py` est créé et implémente `GraphitiGraphStore(GraphStore)`
- [x] Les 14 méthodes du contrat `GraphStore` sont présentes avec leurs signatures exactes et typages stricts
- [x] `GraphitiGraphStore` s'instancie sans `TypeError` et initialise correctement ses composants (driver Neo4j, LLM, embedder, cross-encoder, Graphiti)
- [x] Les paramètres d'initialisation permettent l'injection de dépendances (driver factice, clients mockés) pour garantir des tests unitaires hermétiques
- [x] La passerelle synchrone / asynchrone `_run_async` est implémentée, thread-safe et protégée contre les boucles d'événements existantes
- [x] La factory `get_graph_store(backend="graphiti")` retourne une instance de `GraphitiGraphStore` et ne lève plus `NotImplementedError`
- [x] `backend/app/utils/graph_store/__init__.py` exporte `GraphitiGraphStore`
- [x] Une suite de tests unitaires hermétiques `backend/tests/test_graphiti_graph_store.py` couvre l'instanciation, la factory, la validation de configuration et l'exécution asynchrone
- [x] Les 470 tests existants restent 100 % au vert (`uv run pytest tests/ -q` -> 491 tests verts)
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Définir la classe `LocalPassthroughCrossEncoder` réutilisable pour éviter tout appel réseau lors du reranking
- [x] Créer `backend/app/utils/graph_store/graphiti_store.py` avec la classe `GraphitiGraphStore(GraphStore)`
  - [x] Implémenter le constructeur `__init__` avec résolution des variables d'environnement (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`) et support d'injection de dépendances
  - [x] Implémenter le gestionnaire d'exécution de coroutines thread-safe `_run_async`
  - [x] Déclarer les 14 méthodes de l'interface `GraphStore` avec signatures conformes (stubs documentés pointant vers les stories 003-2 et 003-3)
- [x] Modifier `backend/app/utils/graph_store/factory.py` pour instancier `GraphitiGraphStore` lorsque `selected_backend == "graphiti"`
- [x] Exposer `GraphitiGraphStore` dans `backend/app/utils/graph_store/__init__.py`
- [x] Créer la suite de tests unitaires `backend/tests/test_graphiti_graph_store.py` :
  - [x] Test d'instanciation de `GraphitiGraphStore` avec dépendances mockées
  - [x] Test de présence et de signature des 14 méthodes (absence de `TypeError` d'abstraction)
  - [x] Test de validation des variables d'environnement (`GraphValidationError` si mot de passe manquant en mode réel)
  - [x] Test d'activation de la factory `get_graph_store(backend="graphiti")`
  - [x] Test de l'aiguillage via variable d'environnement `ZEP_BACKEND=graphiti`
  - [x] Test du mécanisme d'override `override_graph_store` avec une instance de `GraphitiGraphStore`
  - [x] Test de robustesse de `_run_async` en environnement sans boucle et sous boucle active
- [x] Valider la non-régression sur le filet existant (491 tests verts, 0 régression)
- [x] Exécuter `ruff check .` et `validate_plans.py`

### Review Findings

- [x] [Review][Patch] Étendre le contrôle AST d'isolation aux modules graphiti_core et neo4j dans services et api [backend/tests/test_graph_store_isolation.py:47-53]
- [x] [Review][Patch] Compléter la validation précoce des paramètres (batch_size > 0, query non vide, scope valide) dans graphiti_store.py [backend/app/utils/graph_store/graphiti_store.py:328, 430]
- [x] [Review][Patch] Normaliser les scores du cross-encoder local pour borner l'intervalle à [0.0, 1.0] [backend/app/utils/graph_store/graphiti_store.py:46-48]
- [x] [Review][Patch] Inclure les erreurs de limitation de débit (RateLimit) dans la traduction vers GraphConnectionError [backend/app/utils/graph_store/graphiti_store.py:154-158]
- [x] [Review][Patch] Ajouter un test sans mock pour get_graph_store(backend="graphiti") sans mot de passe vérifiant GraphValidationError [backend/tests/test_graph_store_factory.py:166-184]
- [x] [Review][Defer] Absence de méthode de fermeture explicite du pool de connexions (close()) sur GraphStore et GraphitiGraphStore [backend/app/utils/graph_store/graphiti_store.py:110] — deferred: concerne l'interface commune GraphStore (base.py) partagée avec Zep, à évaluer si un cycle de vie de fermeture formel est requis

#### Rejected

- [Re-création de ThreadPoolExecutor dans _run_async] : rejeté (`false`) — sous Flask synchrone, asyncio.run est utilisé directement sans pool ; l'exécuteur n'est invoqué que dans les contextes de tests sous boucle active.
- [Mutation de os.environ GRAPHITI_TELEMETRY_ENABLED dans __init__] : rejeté (`false`) — requis pour neutraliser PostHog car graphiti-core ne lit la télémétrie que depuis l'environnement.
- [Absence d'arguments de connexion Neo4j dans get_graph_store] : rejeté (`false`) — la factory unifiée GraphStore lit la configuration d'infrastructure de manière homogène depuis l'environnement (FR-2 / C5).

## Notes de développement

- **Conception Clean Architecture et injection de dépendances** :
  Pour respecter AGENTS.md §2.2 (tests hermétiques sans conteneur obligatoire en CI), le constructeur de `GraphitiGraphStore` accepte optionnellement `driver`, `llm_client`, `embedder`, `cross_encoder` et `graphiti`. Si ces paramètres ne sont pas fournis, il lit la configuration Flask / environnement (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`) et initialise les implémentations par défaut.
- **Gestionnaire sync / async `_run_async`** :
  Les appels à `graphiti-core` étant asynchrones, `_run_async(coro)` inspecte l'état de la boucle courante via `asyncio.get_running_loop()`. Si aucune boucle n'est active dans le thread, `asyncio.run(coro)` est utilisé ; si une boucle tourne déjà (ex. sous `pytest-asyncio`), la coroutine est déléguée via un `ThreadPoolExecutor(max_workers=1)` pour ne jamais bloquer ni lever `RuntimeError: This event loop is already running`.
- **Désactivation de la télémétrie locale** :
  La variable d'environnement `GRAPHITI_TELEMETRY_ENABLED=false` est posée par défaut pour bloquer toute télémétrie sortante PostHog non désirée.

## Revue

Revue contradictoire BMad à 4 couches (Blind Hunter, Edge Case Hunter, Verification Gap Reviewer, Acceptance Auditor) menée avec succès :
1. **Isolation architecturale AST (NFR-2)** :
   - `test_graph_store_isolation.py` étendu pour interdire formellement `graphiti_core` et `neo4j` dans `services/` et `api/`.
2. **Robustesse et validation des entrées (Contrat C1)** :
   - Validation stricte de `batch_size > 0` dans `add_text_batch` et validation complète de `query`, `limit > 0` et `scope` dans `search` (levant `GraphValidationError`).
3. **Normalisation du cross-encoder local** :
   - Scores décroissants rigoureusement bornés dans `[0.0, 1.0]` (évitant les scores négatifs au-delà de 1000 passages).
4. **Gestion des exceptions et rate limiting** :
   - Traduction explicite des erreurs `RateLimit` vers `GraphConnectionError` dans `_translate_error`.
5. **Intégration factory sans mock** :
   - Test unitaire direct validant la levée de `GraphValidationError` lors de l'appel `get_graph_store(backend="graphiti")` sans `NEO4J_PASSWORD`.
6. **Filet de tests et non-régression** :
   - Filet porté à **494 tests verts** (+24 tests unitaires, 0 régression).
   - `ruff check .` et `validate_plans.py` 100 % conformes.

## Notes de complétion

- **Fichiers créés / modifiés** :
  - `backend/app/utils/graph_store/graphiti_store.py` : implémentation de `GraphitiGraphStore`, `LocalPassthroughCrossEncoder`, validation stricte des entrées et traduction fine des erreurs.
  - `backend/app/utils/graph_store/factory.py` : routage effectif de `selected_backend == 'graphiti'` vers `GraphitiGraphStore()`.
  - `backend/app/utils/graph_store/__init__.py` : export de `GraphitiGraphStore` et `LocalPassthroughCrossEncoder`.
  - `backend/tests/test_graphiti_graph_store.py` : 23 tests unitaires hermétiques validant l'instanciation, le contrat des 14 méthodes, l'injection de dépendances, la traduction d'erreurs (y compris RateLimit), la passerelle asynchrone et le cross-encoder borné.
  - `backend/tests/test_graph_store_factory.py` : tests d'activation factory avec et sans mock.
  - `backend/tests/test_graph_store_isolation.py` : extension du contrôle AST permanent interdisant `graphiti_core` et `neo4j` dans les couches métier.
- **Résultats de validation** :
  - Tests : 494 passants (0 échec, 0 régression).
  - Lint : `ruff check .` sans avertissement.
  - Planification : `validate_plans.py` conforme.
- **Prochaine étape** : Story 003-2 (Implémentation du cycle de vie et de l'ingestion d'épisodes avec partitionnement `group_id`).
