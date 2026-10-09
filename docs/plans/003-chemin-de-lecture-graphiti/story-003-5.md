---
id: "003-5"
epic: "003"
titre: "Tests d'intégration réels avec Neo4j local, validation des critères C1-C6 et clôture de l'Epic 003"
statut: in-progress
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

- [ ] Un protocole ou banc d'intégration autonome (`backend/scripts/verifier_integration_graphiti.py`) valide l'ensemble du cycle de vie contre le serveur Neo4j réel
- [ ] Critère C1 validé : 100 % des 14 méthodes de `GraphStore` s'exécutent avec succès sur l'instance réelle
- [ ] Critère C2 validé : 0 fuite de données inter-graphes démontrée lors d'un test multi-tenant (2 `graph_id` distincts dans la même base)
- [ ] Critère C3 validé : Métadonnées temporelles (`created_at`, `valid_at`, `invalid_at`, `expired_at`) persistées et relues fidèlement
- [ ] Critère C4 validé : `zep_entity_reader.filter_defined_entities()` extrait avec succès des entités typées et enrichies depuis la base réelle
- [ ] Critère C5 validé : `get_graph_store(backend="graphiti")` instancie et opère le store en mode nominal
- [ ] Critère C6 validé : Filet global de tests unitaires (≥ 555 tests) maintenu à 100 % vert
- [ ] Rapport de validation versionné consignant les résultats d'exécution réels
- [ ] Synchronisation documentaire et passage formel de l'Epic 003 à `done` (`epic-003.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`)
- [ ] Outils de qualité validés : `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Concevoir le script de validation d'intégration `backend/scripts/verifier_integration_graphiti.py`
- [ ] Vérifier la connectivité Bolt et l'initialisation des index/contraintes Neo4j
- [ ] Tester l'ingestion d'épisodes et la persistance des nœuds et arêtes
- [ ] Valider le partitionnement strict `group_id` (test multi-tenant avec isolation étanche)
- [ ] Valider la lecture Cypher (`get_all_nodes`, `get_all_edges`, `get_graph_data`, `get_graph_info`)
- [ ] Valider la recherche hybride `search` (scopes `edges`, `nodes`, `hybrid`)
- [ ] Valider la chaîne de lecture `zep_entity_reader` sur le graphe réel
- [ ] Tester le cycle de vie (`delete_graph`) et vérifier l'absence d'effets de bord sur les autres graphes
- [ ] Valider formellement les critères C1 à C6 du PRD
- [ ] Exécuter la revue contradictoire BMad sur la story 003-5
- [ ] Clôturer l'Epic 003 et synchroniser l'ensemble des référentiels

## Notes de développement

- **Environnement Neo4j réel** :
  L'intégration s'appuie sur `docker-compose.neo4j.yml` lancé via `docker compose -f docker-compose.neo4j.yml up -d --wait`.
  Les paramètres de connexion proviennent de `.env` (`NEO4J_URI=bolt://localhost:7687`, `NEO4J_USER=neo4j`, `NEO4J_PASSWORD`).
- **Hermétisme de la CI** :
  Conformément à AGENTS.md §2.2, les tests lancés par `pytest tests/` par défaut restent unitaires et hermétiques (aucun prérequis de service tiers actif).
  Le script `verifier_integration_graphiti.py` constitue un banc de vérification comportementale exécutable localement dès que le conteneur Neo4j est démarré.

## Revue

- **Revue contradictoire BMad (prévue lors du passage en `review`)** :
  - *Critère C1 à C6 du PRD* : Validation chiffrée de chacun des 6 critères d'acceptation du PRD.
  - *Conformité architecturale (NFR-1 à NFR-5)* : Vérification de l'absence de fuite de dépendances propriétaires et du respect de la clean architecture.
  - *Robustesse et nettoyage* : Vérification que les opérations d'intégration nettoient proprement leurs données de test sans corrompre l'état de la base.

## Notes de complétion

- Story en cours de cadrage et de démarrage (statut `in-progress`).
- Les notes de complétion définitives seront rédigées à l'issue de l'exécution du banc d'intégration, de la validation des critères C1-C6 et de la revue contradictoire BMad.
