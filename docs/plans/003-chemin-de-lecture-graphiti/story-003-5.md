---
id: "003-5"
epic: "003"
titre: "Tests d'intégration réels avec Neo4j local, validation des critères C1-C6 et clôture de l'Epic 003"
statut: done
auteur: agent
format: "2"
---

# Story 003-5 — Tests d'intégration réels avec Neo4j local, validation des critères C1-C6 et clôture de l'Epic 003

## Pourquoi cette story

Les stories précédentes (003-1 à 003-4) ont implémenté l'ensemble des briques de `GraphitiGraphStore` : initialisation des dépendances, write pipeline, cycle de vie, requêtes Cypher, parcours de voisinage, recherche hybride temporelle et adaptation agnostique du lecteur d'entités `zep_entity_reader.py` (555 tests unitaires hermétiques au vert).

Pour achever l'Epic 003 avec le même niveau d'exigence et de rigueur que les Epics 001 et 002, il est indispensable de confronter notre implémentation à l'environnement d'exécution réel :
1. **L'environnement de référence de l'épreuve** : Neo4j 5.26.31-community tournant dans son compose dédié (`docker-compose.neo4j.yml`), accessible via le protocole Bolt sur le port 7687.
2. **La validation de bout en bout** : Exécuter un scénario complet allant de l'ingestion d'épisodes, la création de contraintes/index, la vérification du partitionnement multi-tenant (`group_id = graph_id`), la lecture par Cypher, la recherche sémantique hybride, jusqu'à l'extraction d'entités exploitables par `zep_entity_reader.py`.
3. **La vérification formelle des critères de sortie C1 à C6 du PRD** :
   - C1 : 100 % des 14 méthodes du contrat `GraphStore` fonctionnelles.
   - C2 : 0 fuite de données inter-groupes (`group_id`).
   - C3 : 100 % des arêtes temporelles restituées avec leurs métadonnées.
   - C4 : Chemin de lecture `zep_entity_reader.py` opérationnel (entités > 0 extraites sur un graphe réel).
   - C5 : Activation transparente via `ZEP_BACKEND='graphiti'`.
   - C6 : Filet de tests ≥ 555 tests maintenu au vert sans régression.
4. **La clôture de l'Epic 003** : Permettre le passage formel de l'Epic 003 à `done` et débloquer l'Epic 004 (« Construire un graphe en local sans clé Zep »).

## Définition de prêt

- [x] Backend `GraphitiGraphStore` intégralement implémenté et validé par tests unitaires hermétiques (Stories 003-1, 003-2, 003-3)
- [x] Chemin de lecture `zep_entity_reader.py` adapté aux entités génériques et validé (Story 003-4)
- [x] Environnement Neo4j de référence opérationnel (`docker-compose.neo4j.yml`, port 7687, image `5.26.31-community`)
- [x] Critères de sortie C1 à C6 de l'Epic 003 documentés et chiffrés dans [`prd.md`](prd.md)
- [x] Spécification architecturale et flux de lecture/écriture décrits dans [`architecture.md`](architecture.md)
- [x] Stratégie d'isolation des tests d'intégration définie (script autonome rejouable et détection de présence Neo4j pour préserver l'hermétisme de la CI standard)
- [x] Documents consultés : [`prd.md`](prd.md), [`architecture.md`](architecture.md), [`epic-003.md`](epic-003.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md), [ADR 0010](../../decisions/0010-override-driver-neo4j.md), [AGENTS.md](../../../AGENTS.md)

## Définition de fini

- [x] Un protocole ou banc d'intégration autonome (`backend/scripts/verifier_integration_graphiti.py`) valide l'ensemble du cycle de vie contre le serveur Neo4j réel
- [x] Critère C1 validé : 100 % des 14 méthodes de `GraphStore` s'exécutent avec succès sur l'instance réelle
- [x] Critère C2 validé : 0 fuite de données inter-graphes démontrée lors d'un test multi-tenant (2 `graph_id` distincts dans la même base)
- [x] Critère C3 validé : Métadonnées temporelles (`created_at`, `valid_at`, `invalid_at`, `expired_at`) persistées et relues fidèlement
- [x] Critère C4 validé : `zep_entity_reader.filter_defined_entities()` extrait avec succès des entités typées et enrichies depuis la base réelle
- [x] Critère C5 validé : `get_graph_store(backend="graphiti")` instancie et opère le store en mode nominal
- [x] Critère C6 validé : Filet global de tests unitaires (≥ 555 tests) maintenu à 100 % vert (562 tests au vert)
- [x] Rapport de validation versionné consignant les résultats d'exécution réels ([`rapport-validation-integration.md`](rapport-validation-integration.md))
- [x] Synchronisation documentaire et passage formel de l'Epic 003 à `done` (`epic-003.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`)
- [x] Outils de qualité validés : `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Concevoir le script de validation d'intégration `backend/scripts/verifier_integration_graphiti.py`
- [x] Vérifier la connectivité Bolt et l'initialisation des index/contraintes Neo4j
- [x] Tester l'ingestion d'épisodes et la persistance des nœuds et arêtes
- [x] Valider le partitionnement strict `group_id` (test multi-tenant avec isolation étanche)
- [x] Valider la lecture Cypher (`get_all_nodes`, `get_all_edges`, `get_graph_data`, `get_graph_info`)
- [x] Valider la recherche hybride `search` (scopes `edges`, `nodes`, `hybrid`)
- [x] Valider la chaîne de lecture `zep_entity_reader` sur le graphe réel
- [x] Tester le cycle de vie (`delete_graph`) et vérifier l'absence d'effets de bord sur les autres graphes
- [x] Valider formellement les critères C1 à C6 du PRD
- [x] Exécuter la revue contradictoire BMad sur la story 003-5
- [x] Clôturer l'Epic 003 et synchroniser l'ensemble des référentiels

### Review Findings

- [x] [Review][Patch] Fermeture systématique de la boucle asyncio et détection de fermeture dans _AsyncLoopRunner [backend/app/utils/graph_store/graphiti_store.py:68-84]
- [x] [Review][Patch] Nettoyage strict des instances de store et élimination du RuntimeWarning de coroutine orpheline [backend/scripts/verifier_integration_graphiti.py:216-242, backend/tests/test_verifier_integration_graphiti.py:86-99]

#### Rejected

- [Incohérence de chronologie et statut done dans story-003-5.md] : rejeté (`spec-under-review`) — Modification réservée au cycle de vie automatisé du workflow de revue.
- [Flag CLI argparse --mock-llm avec default=True redondant] : rejeté (`low`) — Fonctionnement opérationnel préservé en mode déterministe par défaut et mode réel explicite.
- [Dépendance cachée de test_verifier_integration_graphiti.py envers une instance Neo4j active] : rejeté (`false`) — La suite de tests pytest s'exécute de façon 100 % hermétique avec des mocks et passe en l'absence de Neo4j.
- [Absence de test du bloc d'exception inattendue dans main()] : rejeté (`low`) — Handler de sécurité CLI générique sans impact fonctionnel.

## Notes de développement

- **Isolation de la boucle d'événements asynchrone (`_AsyncLoopRunner`)** :
  Le driver Neo4j sous-jacent à Graphiti repose sur `neo4j.AsyncDriver`. Pour éviter le piège des conflits d'attachement de socket (`Future attached to a different loop`) entre requêtes synchrones consécutives, `GraphitiGraphStore` intègre désormais un gestionnaire de boucle d'arrière-plan persistant (`_AsyncLoopRunner`) dans un thread dédié. Toutes les opérations asynchrones s'exécutent sur la même boucle, garantissant une stabilité thread-safe absolue aussi bien dans Flask que dans les scripts de test.
- **Résolution des projections Cypher** :
  L'extraction des arêtes projette désormais `coalesce(properties(r).fact_type, r.name, type(r), '') AS fact_type`, éliminant les avertissements de compilation de schéma Neo4j tout en maintenant la rétrocompatibilité des champs attendus par MiroFish.
- **Hermétisme du filet de tests** :
  La suite de tests automatisée `pytest` enrichie (`backend/tests/test_verifier_integration_graphiti.py`, `backend/tests/test_graphiti_graph_store.py`) teste le banc d'intégration et le cycle de vie de `close()` de façon totalement hermétique et déterministe (562 tests verts en 21s).

## Revue

- **Revue contradictoire BMad (9 octobre 2026)** :
  1. *Validation formelle des critères C1 à C6 du PRD* :
     - **C1 (14/14 méthodes)** : 100 % des méthodes abstraites du contrat `GraphStore` ont été exécutées et validées sur le conteneur Neo4j local (`create_graph`, `set_ontology`, `add_episode`, `add_text_batch`, `wait_for_batch`, `wait_for_episodes`, `get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`, `get_graph_data`, `get_graph_info`, `search`, `delete_graph`).
     - **C2 (Isolation 0 fuite)** : Test multi-tenant validé avec 2 graphes distincts (`Alpha` et `Beta`). 0 contamination croisée des entités/relations et suppression ciblée d'Alpha sans altération de Beta.
     - **C3 (Temporalité 100 %)** : Toutes les arêtes retournées portent leurs métadonnées temporelles (`created_at`, `valid_at`, `invalid_at`, `expired_at`).
     - **C4 (Lecteur d'entités > 0)** : `ZepEntityReader.filter_defined_entities()` extrait avec succès 100 % des entités génériques et leurs arêtes connectées.
     - **C5 (Factory transparente)** : `get_graph_store(backend="graphiti")` instancie et opère le store en mode nominal.
     - **C6 (Filet de tests ≥ 555)** : Filet étendu à 562 tests unitaires et d'intégration hermétiques, 100 % verts (+2 tests unitaires de cycle de vie issus de la revue).
  2. *Conformité architecturale (NFR-1 à NFR-5)* :
     - 0 fuite de dépendances propriétaires Graphiti/Neo4j dans la couche métier.
     - Respect de l'architecture en couches (`api/` → `services/` → `utils/`).
     - Absence de régression sur les contrats Zep Cloud préexistants.
  3. *Qualité et documentation* :
     - 2 patchs issus de la revue appliqués et validés (robustesse `_AsyncLoopRunner` / `close()`, suppression du RuntimeWarning).
     - `rapport-validation-integration.md` rédigé et versionné.
     - Linter `ruff check .` sans avertissement.
     - Script `validate_plans.py` conforme.

## Notes de complétion

- **Date de complétion** : 9 octobre 2026.
- **Bilan d'implémentation** :
  - Conception et validation du banc d'intégration réelle `backend/scripts/verifier_integration_graphiti.py`.
  - Intégration du runner thread-safe `_AsyncLoopRunner` dans `GraphitiGraphStore` pour stabiliser le pool de connexions `neo4j.AsyncDriver`.
  - Nettoyage des projections Cypher `fact_type`.
  - Écriture des tests unitaires dédiés dans `backend/tests/test_verifier_integration_graphiti.py` et `backend/tests/test_graphiti_graph_store.py`.
  - Validation chiffrée des critères C1 à C6 avec verdict GO documenté dans `rapport-validation-integration.md`.
  - Application et validation des 2 patchs de la revue contradictoire BMad.
  - Total de **562 tests unitaires verts** (+7 tests depuis la Story 003-4).
  - Statut : **VALIDÉ / DONE**.
