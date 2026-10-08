---
id: "003-1"
epic: "003"
titre: "Squelette de GraphitiGraphStore, initialisation des dépendances et activation dans la factory"
statut: in-progress
auteur: agent
format: "2"
---

# Story 003-1 — Squelette de GraphitiGraphStore, initialisation des dépendances et activation dans la factory

## Pourquoi cette story

L'Epic 001 a prouvé que la chaîne locale Graphiti + Neo4j 5.26 + `all-MiniLM-L6-v2` + OpenCode Go fonctionne sans frais (Verdict GO validé). L'Epic 002 a ensuite posé l'interface neutre `GraphStore` et encapsulé l'implémentation existante `ZepGraphStore` (470 tests verts).

Cependant, à ce jour, la factory `get_graph_store(backend="graphiti")` lève une exception explicite `NotImplementedError` : aucun backend local n'est encore instanciable.

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

- [ ] `backend/app/utils/graph_store/graphiti_store.py` est créé et implémente `GraphitiGraphStore(GraphStore)`
- [ ] Les 14 méthodes du contrat `GraphStore` sont présentes avec leurs signatures exactes et typages stricts
- [ ] `GraphitiGraphStore` s'instancie sans `TypeError` et initialise correctement ses composants (driver Neo4j, LLM, embedder, cross-encoder, Graphiti)
- [ ] Les paramètres d'initialisation permettent l'injection de dépendances (driver factice, clients mockés) pour garantir des tests unitaires hermétiques
- [ ] La passerelle synchrone / asynchrone `_run_async` est implémentée, thread-safe et protégée contre les boucles d'événements existantes
- [ ] La factory `get_graph_store(backend="graphiti")` retourne une instance de `GraphitiGraphStore` et ne lève plus `NotImplementedError`
- [ ] `backend/app/utils/graph_store/__init__.py` exporte `GraphitiGraphStore`
- [ ] Une suite de tests unitaires hermétiques `backend/tests/test_graphiti_graph_store.py` couvre l'instanciation, la factory, la validation de configuration et l'exécution asynchrone
- [ ] Les 470 tests existants restent 100 % au vert (`uv run pytest tests/ -q`)
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Définir la classe `LocalPassthroughCrossEncoder` réutilisable pour éviter tout appel réseau lors du reranking
- [ ] Créer `backend/app/utils/graph_store/graphiti_store.py` avec la classe `GraphitiGraphStore(GraphStore)`
  - [ ] Implémenter le constructeur `__init__` avec résolution des variables d'environnement (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`) et support d'injection de dépendances
  - [ ] Implémenter le gestionnaire d'exécution de coroutines thread-safe `_run_async`
  - [ ] Déclarer les 14 méthodes de l'interface `GraphStore` avec signatures conformes (stubs documentés pointant vers les stories 003-2 et 003-3)
- [ ] Modifier `backend/app/utils/graph_store/factory.py` pour instancier `GraphitiGraphStore` lorsque `selected_backend == "graphiti"`
- [ ] Exposer `GraphitiGraphStore` dans `backend/app/utils/graph_store/__init__.py`
- [ ] Créer la suite de tests unitaires `backend/tests/test_graphiti_graph_store.py` :
  - [ ] Test d'instanciation de `GraphitiGraphStore` avec dépendances mockées
  - [ ] Test de présence et de signature des 14 méthodes (absence de `TypeError` d'abstraction)
  - [ ] Test de validation des variables d'environnement (`GraphValidationError` si mot de passe manquant en mode réel)
  - [ ] Test d'activation de la factory `get_graph_store(backend="graphiti")`
  - [ ] Test de l'aiguillage via variable d'environnement `ZEP_BACKEND=graphiti`
  - [ ] Test du mécanisme d'override `override_graph_store` avec une instance de `GraphitiGraphStore`
  - [ ] Test de robustesse de `_run_async` en environnement sans boucle et sous boucle active
- [ ] Valider la non-régression sur le filet existant (≥ 470 tests verts)
- [ ] Exécuter `ruff check .` et `validate_plans.py`

## Notes de développement

- **Conception Clean Architecture et injection de dépendances** :
  Pour respecter AGENTS.md §2.2 (tests hermétiques sans conteneur obligatoire en CI), le constructeur de `GraphitiGraphStore` doit accepter optionnellement `driver`, `llm_client`, `embedder` et `cross_encoder`. Si ces paramètres ne sont pas fournis, il lit la configuration Flask / environnement et initialise les implémentations par défaut.
- **Gestionnaire sync / async** :
  Les appels à `graphiti-core` étant asynchrones, `_run_async(coro)` doit inspecter l'état de la boucle courante (`asyncio.get_running_loop()`). Si aucune boucle n'est active dans le thread, `asyncio.run(coro)` peut être utilisé ; si une boucle tourne déjà (ex. sous `pytest-asyncio`), la coroutine doit être déléguée via un `ThreadPoolExecutor` ou exécutée de façon thread-safe pour ne jamais bloquer ni lever `RuntimeError`.
- **Désactivation de la télémétrie** :
  S'assurer que la variable d'environnement `GRAPHITI_TELEMETRY_ENABLED=false` est posée avant l'import ou l'instanciation de `Graphiti`.

## Revue

À renseigner lors de la phase de revue contradictoire.

## Notes de complétion

À renseigner lors de la clôture de la story.
