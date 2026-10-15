---
id: "010-3"
epic: "010"
titre: "Thread-safety SentenceTransformers et drain mémoire résilient"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 010-3 — Thread-safety SentenceTransformers et drain mémoire résilient

Lot C, priorité **P1**. En tant qu'utilisateur de MiroFish, je veux que la vidange asynchrone des activités de simulation vers le graphe de connaissances Neo4j ne plante pas sur des erreurs de concurrence PyTorch (`Cannot copy out of meta tensor`) et que les défaillances résiduelles sur des lots d'épisodes secondaires n'empêchent jamais la simulation de passer à l'état `COMPLETED` et de générer son rapport, afin de fiabiliser totalement l'ingestion mémoire du graphe sans bloquer la fin de la simulation.

Cette story répond directement à l'exigence fonctionnelle **FR-4** (tolérance aux fautes lors du drain mémoire) de l'Epic 010, contribue au critère de sortie **C4** (zéro crash d'embeddings concurrents sur SentenceTransformers et complétion garantie) et préserve l'intégrité non fonctionnelle **NFR-1** (zéro régression) et **NFR-3** (propreté de terminaison des ressources).

---

## Définition de prêt

- [ ] Objectif compris : sécuriser l'inférence locale de `SentenceTransformerEmbedder` via un verrou de sérialisation thread-safe (`self._lock`) englobant l'appel à `_encode_sync(texts)`, et rendre le drain final de `ZepGraphMemoryUpdater.stop()` résilient en journalisant les erreurs de lots d'activités défaillants sans faire échouer brutalement la finalisation de la simulation ni la bloquer dans l'état `STOPPING`.
- [ ] Documents consultés :
  - [PRD Epic 010](prd.md) : §1 (crash PyTorch et thread-safety dans l'ingestion mémoire), §2 (objectifs de résilience), §3 (critère C4).
  - [Architecture Epic 010](architecture.md) : §1 (diagramme de séquence et flush final), §2.3 (sécurisation thread-safe de SentenceTransformers).
  - [Hub Epic 010](epic-010.md) : FR-4, C4, NFR-1.
  - `backend/app/utils/graphiti_embedder.py` : méthodes `_get_model()`, `_encode_sync()`, `create()` et `create_batch()` (l. 63-120, 179-201).
  - `backend/app/services/zep_graph_memory_updater.py` : méthode `stop()` (l. 295-327), gestion de `_failed_batches`, `_wait_for_pending_episodes()`.
  - `backend/app/services/simulation_runner.py` : gestion de la barrière mémoire dans `_monitor_simulation` (l. 907-928) et `stop_simulation` (l. 1171-1186).
  - `backend/tests/test_graphiti_embedder.py` : tests unitaires existants de l'embedder local.
  - `backend/tests/test_zep_graph_memory_updater.py` : tests existants sur le cycle de vie de l'updater mémoire.
  - `backend/tests/test_zep_simulation_barrier.py` : tests de la barrière de simulation.
  - [AGENTS.md](../../../AGENTS.md) : §2.1 (clean architecture, SOLID), §2.2 (qualité des tests), §2.8 (gestion des plans).
- [ ] Dépendances résolues :
  - Stories 010-1 (arrêt déterministe) et 010-2 (réconciliation d'état OS/cache et résilience IHM) closes (`done`).
  - Filet de tests au vert : **1568 tests passants sur l'hôte**.
- [ ] Décisions d'ingénierie arrêtées avant code :
  1. **Thread-safety stricte sur l'inférence PyTorch** : `SentenceTransformer.encode` partage des tenseurs internes et des buffers non réentrants sous certains contextes de concurrence multi-threads (`asyncio.to_thread`). Le verrou `self._lock` déjà présent dans `SentenceTransformerEmbedder` pour le chargement paresseux (`_get_model`) doit être également acquis lors de l'exécution de `_encode_sync(texts)` pour sérialiser les appels au modèle sous-jacent.
  2. **Drain mémoire résilient et non bloquant** : dans `ZepGraphMemoryUpdater.stop()`, si `self._failed_batches` contient des échecs d'ingestion d'activités simulées, l'updater doit consigner des alertes détaillées (`logger.warning`), mettre à disposition les diagnostics d'erreurs, mais offrir une option ou politique de tolérance permettant à `SimulationRunner` de ne pas avorter la complétion de la simulation lorsque l'essentiel des rounds est achevé.
  3. **Préservation du contrat de barrière pour les erreurs critiques** : distinguer les erreurs d'ingestion partielles (activités secondaires perdues sans corrompre le graphe) des timeouts bloquants de workers (`TimeoutError`), en veillant à ce que `_pending_episode_uuids` soit purgé proprement sans deadlock.
  4. **Isolation et non-régression** : aucune dépendance directe vers PyTorch ne doit être ajoutée ; la sérialisation s'appuie sur le `threading.Lock` standard de Python.
- [ ] Stratégie de tests identifiée :
  - Test de concurrence unitaire sur `SentenceTransformerEmbedder` simulant des requêtes parallèles d'encodage via plusieurs threads sans collision ni corruption.
  - Tests unitaires sur `ZepGraphMemoryUpdater.stop()` vérifiant le comportement en présence de lots défaillants avec et sans mode résilient.
  - Validation de non-régression sur l'ensemble de la suite existante (1568 tests).

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| **AC1** | **Sérialisation thread-safe de `_encode_sync`** : Dans `SentenceTransformerEmbedder`, l'appel à `model.encode(...)` au sein de `_encode_sync(texts)` s'exécute sous la protection d'un verrou thread-safe (`self._lock`), empêchant tout accès concurrent simultané aux structures internes du modèle PyTorch lors d'invocations parallèles de `create` et `create_batch`. | Test unitaire exécutant 20 encodages concurrents en parallèle via `ThreadPoolExecutor` et vérifiant l'absence d'exceptions de concurrence et l'exactitude des dimensions retournées. |
| **AC2** | **Drain mémoire tolérant aux pannes partielles dans `ZepGraphMemoryUpdater`** : Si des lots d'activités échouent lors de l'ingestion (`self._failed_batches` non vide), `ZepGraphMemoryUpdater.stop(strict=False)` ou la politique de tolérance configurée journalise un avertissement explicite avec le détail des lots sans lever de `RuntimeError` bloquant. | Test unitaire simulant un lot d'activités défaillant et vérifiant que `stop(strict=False)` se termine sans exception tout en comptabilisant `failed_count`. |
| **AC3** | **Complétion nominale de la simulation malgré des erreurs de lots secondaires** : Dans `SimulationRunner._monitor_simulation`, si `ZepGraphMemoryManager.stop_updater()` signale des erreurs partielles d'activités mais que l'attente des épisodes principaux s'est achevée, la simulation bascule en `RunnerStatus.COMPLETED` (avec mention d'avertissement) plutôt que de rester coincée en `STOPPING` ou d'échouer brutalement en `FAILED`. | Test unitaire simulant un arrêt de simulation avec échecs partiels d'updater et confirmant la transition vers `COMPLETED`. |
| **AC4** | **Préservation du mode strict sur demande explicite** : Si `stop(strict=True)` est appelé (ou pour les tests exigeant une exhaustivité stricte comme `test_failed_non_idempotent_write_is_reported_by_stop`), `RuntimeError` continue d'être levée pour garantir la rétrocompatibilité des tests et des contrats exigeants. | Exécution des tests existants de `test_zep_graph_memory_updater.py` confirmant la conservation du comportement strict quand requis. |
| **AC5** | **Nettoyage propre des ressources et des threads de travail** : À la fin de `stop()`, le thread de travail (`_worker_thread`) est systématiquement arrêté et joint, les files d'attente résiduelles sont drainées ou purgées, et aucune fuite de descripteur ou de thread n'est constatée. | Test unitaire vérifiant que `_worker_thread.is_alive()` est faux et que le gestionnaire `ZepGraphMemoryManager` désenregistre l'updater. |
| **AC6** | **Non-régression et maintien du filet de tests** : Les 1568 tests existants demeurent intégralement passants sur l'hôte, et les nouveaux tests hermétiques dédiés s'intègrent sans flakiness. | Exécution complète de `pytest` sans échec. |

---

## Définition de fini

- [ ] AC1 à AC6 satisfaits et vérifiés par des tests automatisés passants.
- [ ] `SentenceTransformerEmbedder` protège l'encodage par verrou thread-safe.
- [ ] `ZepGraphMemoryUpdater.stop` dispose d'un mécanisme de drain tolérant aux pannes partielles.
- [ ] `SimulationRunner._monitor_simulation` finalise proprement la simulation vers `COMPLETED` même en cas de défaillances mineures de flush.
- [ ] Suite de tests unitaires dédiée ajoutée et filet global maintenu au vert (≥ 1572 tests).
- [ ] Revue de code contradictoire BMAD à 4 couches réalisée et consignée dans `## Revue`.
- [ ] Synchronisation des documents de suivi : `epic-010.md`, `sprint-status.yaml`, `STATUS.md` et `AGENTS.md`.

---

## Tâches

- [ ] **T1 — Sécurisation thread-safe de `SentenceTransformerEmbedder`** :
  - Verrouiller l'accès à `model.encode(...)` dans `_encode_sync` avec `with self._lock:`.
  - Vérifier la robustesse sous forte charge asynchrone / multi-threads.
- [ ] **T2 — Résilience du drain dans `ZepGraphMemoryUpdater`** :
  - Ajouter un paramètre `strict: bool = True` (ou gestion par politique) dans `ZepGraphMemoryUpdater.stop()`.
  - Consigner les erreurs dans les logs sans lever de `RuntimeError` lorsque `strict=False`.
- [ ] **T3 — Intégration de la tolérance dans `SimulationRunner`** :
  - Adapter `SimulationRunner._monitor_simulation` et `stop_simulation` pour utiliser le mode résilient lors de la finalisation terminale.
  - Renseigner les avertissements éventuels dans `state.error` ou les métadonnées sans bloquer le statut `COMPLETED`.
- [ ] **T4 — Tests unitaires hermétiques et non-régression** :
  - Créer ou enrichir les tests dans `test_graphiti_embedder.py` et `test_zep_graph_memory_updater.py`.
  - Valider l'exécution concurrente et la tolérance aux pannes partielles.
- [ ] **T5 — Revue contradictoire BMAD & clôture de l'Epic 010** :
  - Exécuter la suite complète des tests du backend.
  - Conduire la revue contradictoire BMAD à 4 couches.
  - Clore la story 010-3 et prononcer le bilan de qualification de l'Epic 010.

---

## Notes de développement

### Sécurisation de l'encodage dans `SentenceTransformerEmbedder`

```python
def _encode_sync(self, texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    model = self._get_model()
    # Sérialisation thread-safe de l'inférence PyTorch
    with self._lock:
        embeddings = model.encode(
            texts,
            normalize_embeddings=self.config.normalize_embeddings,
            convert_to_numpy=True,
        )
    ...
```

### Tolérance aux pannes partielles dans `ZepGraphMemoryUpdater.stop`

```python
def stop(self, strict: bool = False):
    ...
    self._flush_remaining(deadline=deadline)

    if self._failed_batches:
        msg = f"{len(self._failed_batches)} graph activity batch(es) failed"
        if strict:
            raise RuntimeError(f"{msg}; simulation graph ingestion is incomplete")
        logger.warning(f"{msg}; poursuite de la finalisation en mode résilient.")
    ...
```

---

## Revue

À compléter lors de la revue contradictoire BMAD.

---

## Notes de complétion

À compléter lors de la complétion de la story.
