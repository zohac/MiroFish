# Epic 002 — Interface GraphStore

- **Statut** : `in-progress` · **Dépend de** : 001 · **Bloque** : 003, 004
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> On abstrait avant de bifurquer. Le plan complet du projet est dans
> [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md) et la cible d'architecture dans
> [`docs/architecture/cible-graphstore.md`](../../architecture/cible-graphstore.md).

**Artefacts de ce dossier** — [`prd.md`](prd.md) (quoi, pourquoi, critères chiffrés) ·
[`architecture.md`](architecture.md) (comment, modèles et schémas) · ce fichier (le contrat
d'ingénierie) · `story-002-<n>.md` (une story démarrée = un fichier markdown).

---

## Le problème en une phrase

Les services métiers et routes HTTP de MiroFish appellent directement le SDK propriétaire Zep Cloud
à travers 10 fichiers, rendant impossible le remplacement par Graphiti sans réécriture invasive
ni prolifération de branchements conditionnels `if/else`.

## Objectif

Construire une couche d'abstraction unifiée `GraphStore`, encapsuler l'implémentation existante
dans `ZepGraphStore`, fournir une factory pilotée par `ZEP_BACKEND` (`cloud` par défaut) et refactorer
les consommateurs métier pour garantir une transition transparente, découplée et réversible
sans aucune régression sur le filet de tests existant (333 tests).

## Exigences fonctionnelles

| # | Exigence |
|---|---|
| FR-1 | Définir l'interface abstraite `GraphStore`, les modèles de données neutres (`GraphNode`, `GraphEdge`, `GraphSearchResult`, `EpisodeRecord`, `BatchSubmissionRecord`) et la hiérarchie d'exceptions (`GraphStoreError`, `GraphNotFoundError`, `GraphConnectionError`) |
| FR-2 | Implémenter `ZepGraphStore` encapsulant l'accès à Zep Cloud, la pagination par curseurs et les retries sans fuite de types propriétaires |
| FR-3 | Fournir la factory `get_graph_store()` instanciant le backend selon `ZEP_BACKEND` (`cloud` par défaut, réservation explicite de `graphiti`, injection de fake store pour les tests) |
| FR-4 | Refactorer les flux d'ingestion et d'écriture (`graph_builder.py`, `zep_graph_memory_updater.py`, `simulation_runner.py`) pour consommer l'interface `GraphStore` |
| FR-5 | Refactorer les flux de lecture et d'interrogation (`zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py`, `api/graph.py`) pour consommer l'interface `GraphStore` |
| FR-6 | Valider l'étanchéité architecturale par un test statique d'isolation d'imports et confirmer la non-régression absolue (≥ 333 tests verts) |

## Exigences non fonctionnelles

| # | Exigence | Pourquoi |
|---|---|---|
| NFR-1 | Zéro régression : les 333 tests existants restent verts | La migration ne doit pas dégrader le comportement existant du produit |
| NFR-2 | Dépendances vers l'intérieur : Clean Architecture stricte | `api` → `services` → `utils/graph_store`, aucun import inverse ni circulaire (AGENTS.md §2.1) |
| NFR-3 | Zéro `if zep else graphiti` dans le code applicatif ou les routes | L'aiguillage vit exclusivement dans la factory (ADR 0001, AGENTS.md §2.1) |
| NFR-4 | Réversibilité immédiate par configuration | `ZEP_BACKEND=cloud` conserve 100 % du comportement initial de l'application |
| NFR-5 | Tests hermétiques et sans réseau réel pour chaque composant nouveau | Les clients HTTP/SDK sont mockés, aucun appel sortant durant la suite pytest |

## UX requirements

L'epic 002 est un refactoring architectural backend pur sans impact d'interface utilisateur directe.
Les contrats JSON de l'API HTTP (`/api/graph/*`) restent strictement identiques pour le frontend Vue existant.

## Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 002-1 | Définition de l'interface `GraphStore`, des modèles de données neutres et des exceptions | `backlog` | — |
| 002-2 | Implémentation de `ZepGraphStore` et encapsulation du SDK Zep | `backlog` | — |
| 002-3 | Factory `get_graph_store()` et configuration `ZEP_BACKEND` | `backlog` | — |
| 002-4 | Refactoring de l'ingestion (`graph_builder.py`, `zep_graph_memory_updater.py`, `simulation_runner.py`) | `backlog` | — |
| 002-5 | Refactoring de la lecture (`zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py`, `api/graph.py`) | `backlog` | — |
| 002-6 | Validation de l'isolation, tests de non-régression et clôture de l'epic 002 | `backlog` | — |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 002-1 | Given les besoins du moteur, when on définit `backend/app/utils/graph_store/base.py` et `errors.py`, then l'interface `GraphStore` couvre cycle de vie, batch, ontologie, lecture, parcours, recherche et épisodes ; les modèles (`GraphNode`, `GraphEdge`, etc.) sont complètement typés et sérialisables ; aucune dépendance à `zep-cloud` n'existe dans ce module ; des tests unitaires valident le contrat |
| 002-2 | Given l'interface `GraphStore`, when on implémente `ZepGraphStore`, then toutes les méthodes délèguent au SDK Zep Cloud en intégrant pagination (`zep_paging.py`) et retries (`call_zep_read_with_retry`) ; les erreurs Zep (`NotFoundError`, `ApiError`, etc.) sont traduites en exceptions de la hiérarchie `GraphStoreError` ; la suite de tests unitaires mockés valide la conformité |
| 002-3 | Given la configuration `Config.ZEP_BACKEND`, when `get_graph_store()` est appelé, then il retourne `ZepGraphStore` si `ZEP_BACKEND=cloud` (défaut), lève `NotImplementedError` pour `graphiti` (réservé Epic 003), rejette toute valeur inconnue, et supporte l'injection d'un store substitut (`set_graph_store_override`) pour les tests unitaires |
| 002-4 | Given les flux d'écriture et d'ingestion, when `graph_builder.py`, `zep_graph_memory_updater.py` et `simulation_runner.py` sont refactorés, then ils n'importent plus directement `zep.py` ou le SDK Zep ; toutes les opérations passent par `GraphStore` ; les tests existants associés restent au vert |
| 002-5 | Given les flux de lecture et d'interrogation, when `zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py` et `api/graph.py` sont refactorés, then toute recherche et extraction de nœuds/arêtes s'effectue via l'interface `GraphStore` ; `api/graph.py` ne dépend plus de `zep_cloud.NotFoundError` ; les contrats de sortie vers le frontend et les agents restent 100 % identiques |
| 002-6 | Given l'ensemble du dépôt, when on exécute l'audit d'isolation statique (`test_graph_store_isolation.py`), then **0** import direct de `zep_cloud` et de `utils.zep.get_zep_client` ne subsiste dans `app/services/` et `app/api/` ; 100 % des tests (≥ 333 tests) sont verts ; les artefacts de documentation (`STATUS.md`, `sprint-status.yaml`, `AGENTS.md`) sont synchronisés |

## Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`prd.md`](prd.md) | Objectifs et critères chiffrés C1 à C6 |
| [`architecture.md`](architecture.md) | Contrat d'interface, factory, modèles neutres et exceptions |
| [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md) | Décision de l'interface à deux implémentations et de `ZEP_BACKEND` |
| [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md) | Ontologie dynamique différée en v2 |
| [`docs/LOCAL-FIRST.md` §3–§6](../../LOCAL-FIRST.md) | Rayon d'impact de Zep et points de couplage |
| [`docs/architecture/cible-graphstore.md`](../../architecture/cible-graphstore.md) | Schémas d'architecture cible |
| `backend/app/utils/zep.py` | Logique existante du client Zep et politique de retry |
| `backend/app/utils/zep_paging.py` | Gestion de pagination par curseurs opaques |
| `backend/tests/test_zep_*.py` | Filet de sécurité des 9 suites de tests de contrats Zep |

## Décisions liées

- **ADR 0001** — Remplacement de Zep par Graphiti + Neo4j derrière une interface
- **ADR 0003** — Ontologie dynamique différée en v2
- **ADR 0007** — Une story = un fichier markdown
- **ADR 0009** — Clarification de la forme des stories
- **ADR 0011** — Format 2 des stories et sections obligatoires en français

## L'epic est terminé quand

- [ ] L'interface `GraphStore`, ses modèles de données et ses exceptions sont posés et testés (Story 002-1)
- [ ] `ZepGraphStore` est pleinement implémenté, encapsule le SDK Zep et est testé (Story 002-2)
- [ ] `get_graph_store()` aiguille correctement selon `ZEP_BACKEND` et supporte les tests (Story 002-3)
- [ ] Les services d'ingestion et d'écriture consomment `GraphStore` (Story 002-4)
- [ ] Les services de lecture, outils et routes API consomment `GraphStore` (Story 002-5)
- [ ] Zéro import direct du SDK Zep dans `services/` et `api/` prouvé par test d'isolation (Story 002-6)
- [ ] Les 333 tests existants restent 100 % au vert et le filet global a grossi (Story 002-6)
