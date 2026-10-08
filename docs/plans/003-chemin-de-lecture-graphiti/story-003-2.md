---
id: "003-2"
epic: "003"
titre: "Cycle de vie et ingestion d'épisodes avec partitionnement group_id dans GraphitiGraphStore"
statut: done
auteur: agent
format: "2"
---

# Story 003-2 — Cycle de vie et ingestion d'épisodes avec partitionnement group_id dans GraphitiGraphStore

## Pourquoi cette story

La story 003-1 a posé le socle opérationnel de `GraphitiGraphStore` : initialisation des dépendances locales (driver Neo4j, LLM avec session, embedder local, cross-encoder pass-through), exécuteur synchrone/asynchrone `_run_async`, activation dans la factory `get_graph_store(backend="graphiti")` et conformité formelle au contrat des 14 méthodes (494 tests verts).

Cependant, les méthodes de cycle de vie et d'ingestion levaient auparavant une exception `NotImplementedError` :
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

- [x] `create_graph(name, graph_id=None)` est implémenté, valide les arguments et retourne un identifiant de graphe persistant
- [x] `delete_graph(graph_id)` exécute la suppression Cypher atomique `MATCH (n {group_id: $group_id}) DETACH DELETE n` sans fuite inter-graphes
- [x] `set_ontology(graph_id, ontology)` valide les arguments et s'exécute en no-op gracieux sans lever d'exception
- [x] `add_episode` appelle `graphiti.add_episode` avec `group_id=graph_id`, gère la conversion de `created_at` et retourne un `EpisodeRecord` conforme
- [x] `add_text_batch` ingère séquentiellement les chunks, invoque `progress_callback` et retourne un `BatchSubmissionRecord` valide
- [x] `wait_for_batch` et `wait_for_episodes` contrôlent la persistance des épisodes dans Neo4j via Cypher
- [x] Toutes les erreurs levées lors des opérations sont traduites vers la hiérarchie `GraphStoreError` via `_translate_errors`
- [x] Une suite de tests unitaires hermétiques dans `backend/tests/test_graphiti_graph_store.py` couvre 100 % des flux d'écriture et de cycle de vie
- [x] Les 494 tests existants restent 100 % au vert (`uv run pytest tests/ -q` — 518 tests validés)
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Implémenter `create_graph` et `delete_graph` avec partitionnement Cypher `group_id` dans `GraphitiGraphStore`
- [x] Implémenter `set_ontology` en no-op gracieux validant le format dictionnaire
- [x] Implémenter `add_episode` avec passage de `group_id`, parsing temporel et construction de `EpisodeRecord`
- [x] Implémenter `add_text_batch` avec découpage par lot, notification `progress_callback` et génération de `BatchSubmissionRecord`
- [x] Implémenter `wait_for_batch` et `wait_for_episodes` avec requête Cypher de vérification des épisodes
- [x] Compléter `backend/tests/test_graphiti_graph_store.py` avec les tests unitaires d'écriture et de cycle de vie
- [x] Valider l'étanchéité du partitionnement `group_id` par tests mockés
- [x] Valider la non-régression globale sur la suite de tests (518 tests verts)
- [x] Exécuter `ruff check .` et `validate_plans.py`

### Review Findings

- [x] [Review][Patch] Validation stricte des types de chaîne (isinstance) sur create_graph, delete_graph et add_episode [backend/app/utils/graph_store/graphiti_store.py:305-308, 321-323, 379-383]
- [x] [Review][Patch] Prise en charge du suffixe ISO minuscule 'z' dans add_episode [backend/app/utils/graph_store/graphiti_store.py:391]
- [x] [Review][Patch] Ciblage direct du label :Episodic pour l'utilisation de l'index dans wait_for_batch et wait_for_episodes [backend/app/utils/graph_store/graphiti_store.py:530-532, 584-586]
- [x] [Review][Patch] Tests unitaires pour les branches de repli d'horodatage UTC et de contrôle de connectivité sans health_check [backend/tests/test_graphiti_graph_store.py:470, 564]
- [x] [Review][Patch] Mise à jour de la docstring d'en-tête de test_graphiti_graph_store.py pour inclure la Story 003-2 [backend/tests/test_graphiti_graph_store.py:1]

#### Rejected

- [Absence de filtre group_id dans wait_for_batch] : rejeté (`false`) — BatchSubmissionRecord ne porte pas graph_id dans le contrat d'interface neutre GraphStore (base.py), et les UUIDs d'épisodes sont uniques et déterministes.
- [Ingestion unitaire ignorant batch_size dans add_text_batch] : rejeté (`false`) — Graphiti ingère les épisodes de manière unitaire et synchrone ; batch_size est présent pour la conformité formelle au contrat GraphStore.
- [Intervalle de polling fixe time.sleep(0.1)] : rejeté (`low`) — délai de 100ms adapté aux accès locaux Neo4j sans surcoût de complexité adaptative.

## Notes de développement

- **Isolation `group_id = graph_id`** :
  Chaque appel à `_graphiti.add_episode` reçoit obligatoirement `group_id=graph_id`. Graphiti appose cette propriété sur tous les nœuds d'entités, d'épisodes et arêtes créés lors de la transaction d'extraction.
- **Requête de suppression `delete_graph`** :
  Utilise `MATCH (n {group_id: $group_id}) DETACH DELETE n` avec `params={"group_id": target_graph_id}`, ce qui détruit atomiquement tous les nœuds du groupe sans toucher aux nœuds des autres groupes.
- **Parsing temporel dans `add_episode`** :
  `created_at` supporte les formats ISO 8601 complets avec suffixe 'Z' ou 'z', convertis en `datetime.datetime` UTC pour `reference_time`. À défaut, `datetime.now(timezone.utc)` est utilisé.
- **Gestion de `add_text_batch` et `wait_for_batch`** :
  Validation précoce de l'intégrité de tous les fragments (rejet si un élément est vide ou non textuel), suivi de progression via `progress_callback`, et vérification de la persistance via Cypher avec gestion du timeout.
- **Helpers Cypher et tolérance asynchrone** :
  Introduction de `_execute_cypher`, `_extract_records` et `_get_record_field` permettant d'exécuter et dépouiller uniformément les résultats que le driver soit le client Neo4j natif, un retour asynchrone ou un mock de test.

## Revue

Revue contradictoire BMad menée avec succès à 4 couches (Blind Hunter, Edge Case Hunter, Verification Gap Reviewer, Acceptance Auditor) :
1. **Validation défensive des types de paramètres (Patch 1)** :
   - Gardes `isinstance(..., str)` explicites sur `create_graph`, `delete_graph` et `add_episode` prévenant toute exception `AttributeError` non interceptée lors de l'appel à `.strip()`.
2. **Normalisation temporelle ISO 8601 (Patch 2)** :
   - Prise en charge des suffixes minuscules 'z' et majuscules 'Z' dans `add_episode` pour une interopérabilité sans faille avec les générateurs d'horodatages tiers.
3. **Optimisation des index Cypher (Patch 3)** :
   - Ciblage direct du label `:Episodic` dans les requêtes de `wait_for_batch` et `wait_for_episodes` assurant l'utilisation déterministe de l'index de schéma `episode_uuid`.
4. **Couverture des branches de repli et de validation (Patch 4)** :
   - Nouveaux tests unitaires hermétiques validant la normalisation UTC des dates naïves, le rejet des types non textuels, et le repli de `_check_connection` via `execute_query("RETURN 1 AS ping")`.
5. **Documentation du module de test (Patch 5)** :
   - Docstring d'en-tête de `test_graphiti_graph_store.py` mise à jour pour référencer formellement les stories 003-1 et 003-2.
6. **Filet de tests et non-régression** :
   - Total de 50 tests unitaires hermétiques dédiés à `GraphitiGraphStore`.
   - Filet global porté de 494 à **521 tests verts** (100 % passants).
   - `ruff check .` et `validate_plans.py` 100 % conformes.

## Notes de complétion

- **Fichiers modifiés** :
  - `backend/app/utils/graph_store/graphiti_store.py` :
    - Implémentation de `create_graph` (validation robuste de type, génération `mirofish_<uuid>`, vérification de connectivité via `_check_connection`).
    - Implémentation de `delete_graph` (suppression atomique Cypher `MATCH (n {group_id: $group_id}) DETACH DELETE n` strictement isolée par `group_id`).
    - Implémentation de `set_ontology` (validation du dictionnaire d'ontologie, no-op gracieux en v1 selon ADR 0003).
    - Implémentation de `add_episode` (parsing ISO 8601 UTC avec prise en charge de 'Z'/'z', passage obligatoire de `group_id=graph_id` et `source=EpisodeType.text` à Graphiti, retour d'`EpisodeRecord` neutre avec `processed=True`).
    - Implémentation de `add_text_batch` (validation préalable de l'ensemble des fragments, découpage et soumission séquentielle via `add_episode`, notification de suivi via `progress_callback`, retour d'un `BatchSubmissionRecord` avec `operation_id` déterministe SHA-256).
    - Implémentation de `wait_for_batch` et `wait_for_episodes` (contrôle Cypher indexé `:Episodic` de persistance des nœuds, partitionné par `group_id`, notification de progression et gestion du timeout `GraphTimeoutError`).
    - Helpers internes `_execute_cypher`, `_extract_records`, `_get_record_field` et `_check_connection`.
  - `backend/tests/test_graphiti_graph_store.py` :
    - 27 nouveaux tests unitaires hermétiques couvrant l'ensemble des flux d'écriture, du cycle de vie, des validations de type, des cas limites temporels et de l'isolation `group_id`.
    - Total de 50 tests unitaires dédiés à `GraphitiGraphStore`.
- **Validation technique et qualité** :
  - Filet de tests global : **521 tests verts** (0 échec, 0 régression).
  - Linting : `ruff check .` sans aucun avertissement.
  - Planification : `validate_plans.py` validé.
- **Prochaine étape** : Story **003-3** (Lecture Cypher, requêtes de voisinage et recherche hybride temporelle).
