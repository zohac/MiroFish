---
id: "003-2"
epic: "003"
titre: "Cycle de vie et ingestion d'épisodes avec partitionnement group_id dans GraphitiGraphStore"
statut: in-progress
auteur: agent
format: "2"
---

# Story 003-2 — Cycle de vie et ingestion d'épisodes avec partitionnement group_id dans GraphitiGraphStore

## Pourquoi cette story

La story 003-1 a posé le socle opérationnel de `GraphitiGraphStore` : initialisation des dépendances locales (driver Neo4j, LLM avec session, embedder local, cross-encoder pass-through), exécuteur synchrone/asynchrone `_run_async`, activation dans la factory `get_graph_store(backend="graphiti")` et conformité formelle au contrat des 14 méthodes (494 tests verts).

Cependant, les méthodes de cycle de vie et d'ingestion lèvent actuellement une exception `NotImplementedError` :
- `create_graph`
- `delete_graph`
- `set_ontology`
- `add_episode`
- `add_text_batch`
- `wait_for_batch`
- `wait_for_episodes`

Pour permettre aux pipelines amonts d'ingérer des documents et d'enrichir la mémoire de simulation (`graph_builder.py`, `zep_graph_memory_updater.py`) sans dépendre du cloud Zep :
1. **Partitionnement strict par `group_id` (Critère C2, NFR-3)** :
   Dans une instance Neo4j partagée, l'isolation étanche entre simulations distinctes repose sur l'équivalence fondamentale `group_id = graph_id`. Chaque nœud (`:Entity`, `:Episode`), arête (`:RELATION`) et requête doit être scopé par `group_id`.
2. **Cycle de vie du graphe** :
   - `create_graph(name, graph_id=None)` doit initialiser l'identifiant logique (génération d'un identifiant formaté si non fourni) et vérifier la disponibilité de la connexion.
   - `delete_graph(graph_id)` doit exécuter la suppression Cypher ciblée et atomique (`MATCH (n {group_id: $group_id}) DETACH DELETE n`), sans jamais toucher aux entités des autres graphes.
   - `set_ontology(graph_id, ontology)` doit constituer un no-op gracieux (ADR 0003, v1 sans ontologie dynamique) validant la structure des arguments.
3. **Ingestion unitaire et par lots** :
   - `add_episode` doit déléguer l'extraction structurée et l'encodage vectoriel à `graphiti.add_episode(..., group_id=graph_id)` via `_run_async`, puis restituer un `EpisodeRecord` neutre.
   - `add_text_batch` doit ingérer les fragments découpés, supporter le suivi d'avancement via `progress_callback` et retourner un `BatchSubmissionRecord`.
   - `wait_for_batch` et `wait_for_episodes` doivent contrôler la persistance effective des épisodes dans la base Neo4j.

Cette story livre l'ensemble des méthodes d'écriture et de gestion du cycle de vie avec une suite de tests unitaires mockés hermétiques.

## Définition de prêt

- [x] Contrat d'interface et signatures des 7 méthodes de cycle de vie et d'ingestion définies dans [`base.py`](../../backend/app/utils/graph_store/base.py)
- [x] Socle `GraphitiGraphStore`, gestionnaire `_run_async` et factory validés en story 003-1 (494 tests verts)
- [x] Signature de `Graphiti.add_episode` vérifiée (`name`, `episode_body`, `source_description`, `reference_time`, `group_id`)
- [x] Requête Cypher de suppression étanche validée dans l'architecture : `MATCH (n {group_id: $group_id}) DETACH DELETE n`
- [x] Règle de partitionnement `group_id = graph_id` (PRD C2, NFR-3) documentée
- [x] Documents consultés : [`prd.md`](prd.md), [`architecture.md`](architecture.md), [`epic-003.md`](epic-003.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md)

## Définition de fini

- [ ] `create_graph(name, graph_id=None)` est implémenté, valide les arguments et retourne un identifiant de graphe persistant
- [ ] `delete_graph(graph_id)` exécute la suppression Cypher atomique `MATCH (n {group_id: $group_id}) DETACH DELETE n` sans fuite inter-graphes
- [ ] `set_ontology(graph_id, ontology)` valide les arguments et s'exécute en no-op gracieux sans lever d'exception
- [ ] `add_episode` appelle `graphiti.add_episode` avec `group_id=graph_id`, gère la conversion de `created_at` et retourne un `EpisodeRecord` conforme
- [ ] `add_text_batch` ingère séquentiellement les chunks, invoque `progress_callback` et retourne un `BatchSubmissionRecord` valide
- [ ] `wait_for_batch` et `wait_for_episodes` contrôlent la persistance des épisodes dans Neo4j via Cypher
- [ ] Toutes les erreurs levées lors des opérations sont traduites vers la hiérarchie `GraphStoreError` via `_translate_errors`
- [ ] Une suite de tests unitaires hermétiques dans `backend/tests/test_graphiti_graph_store.py` couvre 100 % des flux d'écriture et de cycle de vie
- [ ] Les 494 tests existants restent 100 % au vert (`uv run pytest tests/ -q`)
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Implémenter `create_graph` et `delete_graph` avec partitionnement Cypher `group_id` dans `GraphitiGraphStore`
- [ ] Implémenter `set_ontology` en no-op gracieux validant le format dictionnaire
- [ ] Implémenter `add_episode` avec passage de `group_id`, parsing temporel et construction de `EpisodeRecord`
- [ ] Implémenter `add_text_batch` avec découpage par lot, notification `progress_callback` et génération de `BatchSubmissionRecord`
- [ ] Implémenter `wait_for_batch` et `wait_for_episodes` avec requête Cypher de vérification des épisodes
- [ ] Compléter `backend/tests/test_graphiti_graph_store.py` avec les tests unitaires d'écriture et de cycle de vie
- [ ] Valider l'étanchéité du partitionnement `group_id` par tests mockés
- [ ] Valider la non-régression globale sur la suite de tests
- [ ] Exécuter `ruff check .` et `validate_plans.py`

## Notes de développement

- **Isolation `group_id = graph_id`** :
  Chaque appel à `_graphiti.add_episode` doit explicitement recevoir `group_id=graph_id`. Graphiti appose automatiquement cette propriété sur tous les nœuds d'entités, d'épisodes et arêtes créés lors de la transaction d'extraction.
- **Requête de suppression `delete_graph`** :
  Utilise `self._driver.execute_query("MATCH (n {group_id: $group_id}) DETACH DELETE n", params={"group_id": graph_id})` enveloppé dans `_run_async` et `_translate_errors`.
- **Parsing temporel dans `add_episode`** :
  Si `created_at` est fourni sous forme de chaîne ISO 8601, le convertir en `datetime.datetime` UTC pour `reference_time`. À défaut, utiliser `datetime.now(timezone.utc)`.
- **Gestion de `add_text_batch` et `wait_for_batch`** :
  Graphiti traitant les épisodes de manière synchrone lors de `add_episode`, l'ingestion par lot exécute les ajouts chunk par chunk avec suivi de progression, puis retourne un `BatchSubmissionRecord` dont le statut est immédiatement consommable.

## Revue

*(Section complétée lors de la revue contradictoire BMad à l'issue de l'implémentation de la story).*

## Notes de complétion

*(Section complétée lors de la clôture de la story).*
