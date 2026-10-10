---
id: "006-3"
epic: "006"
titre: "Validation de relecture GraphStore, personas OASIS et outil de purge Zep Cloud (purger_graphes_zep.py)"
statut: in-progress
auteur: agent
format: "2"
---

# Story 006-3 — Validation de relecture GraphStore, personas OASIS et outil de purge Zep Cloud (purger_graphes_zep.py)

## Définition de prêt

- [x] Objectif compris : valider de bout en bout l'exploitabilité applicative des graphes migrés dans Neo4j local (`GraphitiGraphStore`, `ZepEntityReader`, génération de personas OASIS sans Zep) afin de satisfaire le critère C4 du PRD, et concevoir un outil autonome de purge distante sécurisée (`backend/scripts/purger_graphes_zep.py`) permettant de supprimer de manière contrôlée et confirmée les graphes obsolètes ou migrés sur Zep Cloud (FR-5, FR-6, NFR-1, NFR-2, NFR-4).
- [x] Documents consultés : [PRD Epic 006](prd.md) (§1, §2, §4, §5 C4, C5, FR-5, FR-6, NFR-1, NFR-2, NFR-4), [Architecture Epic 006](architecture.md) (§1, §2, §4, §5, §6), [Epic 006 Hub](epic-006.md), [`backend/scripts/migrer_zep_vers_graphiti.py`](../../backend/scripts/migrer_zep_vers_graphiti.py), [`backend/app/utils/graph_store/graphiti_store.py`](../../backend/app/utils/graph_store/graphiti_store.py), [`backend/app/services/zep_entity_reader.py`](../../backend/app/services/zep_entity_reader.py), [`backend/app/services/oasis_profile_generator.py`](../../backend/app/services/oasis_profile_generator.py), [`backend/app/utils/zep.py`](../../backend/app/utils/zep.py), [ADR 0001](../../decisions/0001-interface-graph-store.md), [ADR 0006](../../decisions/0006-docker-first.md), [AGENTS.md](../../AGENTS.md) (§2.1, §2.2, §2.4, §2.8, §2.9).
- [x] Prérequis techniques vérifiés : script ETL `migrer_zep_vers_graphiti.py` opérationnel et validé (Story 006-2), services `GraphitiGraphStore` et `ZepEntityReader` validés (Epics 003 et 004), client Zep Cloud et méthode de suppression `client.graph.delete(graph_id)` identifiés dans le SDK `zep_cloud`, instance Neo4j locale de référence disponible sous Docker (`bolt://localhost:7687` ou `bolt://neo4j:7687`).
- [x] Stratégie de test identifiée : suite de tests unitaires hermétiques (`backend/tests/test_purger_graphes_zep.py`) avec mocks du client Zep Cloud (`unittest.mock`), tests de vérification de relecture applicative (`GraphitiGraphStore`, `ZepEntityReader`, `OasisProfileGenerator`), tests du mode `--dry-run`, du mode `--mock`, de la double confirmation interactive / flag `--yes`, de l'absence de fuite de secrets et du maintien strict du filet global ($\ge 771$ tests verts).

## Définition de fini

- [ ] Sonde / procédure de validation de relecture applicative démontrant que les données migrées par `migrer_zep_vers_graphiti.py` sont immédiatement exploitables par `GraphitiGraphStore` (`get_all_nodes`, `get_all_edges`, `get_graph_data`), `ZepEntityReader` et `OasisProfileGenerator` (Critère C4 du PRD).
- [ ] Script autonome `backend/scripts/purger_graphes_zep.py` implémenté avec CLI complète (`--graph-id`, `--all`, `--api-key`, `--yes`, `--dry-run`, `--mock`, `--output-report`, `--quiet`).
- [ ] Mécanisme de sécurité renforcé contre les suppressions accidentelles : double confirmation interactive (saisie explicite du nom du graphe) ou passage obligatoire du flag `--yes` en mode non-interactif.
- [ ] Mode `--dry-run` simulant l'inventaire des graphes à supprimer sans exécuter d'appel de suppression sur Zep Cloud.
- [ ] Mode `--mock` hors-ligne déterministe simulant le flux de purge pour la CI sans compte Zep réel ni réseau.
- [ ] Masquage strict des secrets (`masquer_secret`) et zéro fuite de `ZEP_API_KEY` dans les logs, traces d'erreurs ou sorties écran.
- [ ] Suite de tests unitaires hermétiques (`backend/tests/test_purger_graphes_zep.py`) couvrant 100 % des branches (confirmation interactive, flag `--yes`, mode dry-run, mode mock, erreurs réseau, masquage de secret, relecture).
- [ ] Conformité outillage (`ruff check .`, `validate_plans.py`) et préservation du filet de tests ($\ge 771$ tests verts).
- [ ] Revue contradictoire BMad (4 couches) réalisée et consignée.

## Tâches

- [ ] Concevoir l'architecture modulaire du script `backend/scripts/purger_graphes_zep.py` avec dataclasses typées (`PurgeTarget`, `PurgeResult`, `PurgeReport`).
- [ ] Implémenter la logique de purge sécurisée avec double confirmation interactive et flag `--yes`.
- [ ] Implémenter les modes `--dry-run` et `--mock` hors-ligne.
- [ ] Implémenter la CLI complète et la gestion sécurisée des secrets (`ZEP_API_KEY`).
- [ ] Implémenter la validation de relecture applicative post-migration (`GraphitiGraphStore`, `ZepEntityReader`, personas OASIS).
- [ ] Écrire la suite de tests unitaires hermétiques `backend/tests/test_purger_graphes_zep.py`.
- [ ] Exécuter la suite de tests et vérifier la propreté du code via `ruff check .`.
- [ ] Réaliser la revue contradictoire BMad (4 couches) et appliquer les correctifs.
- [ ] Clore la story, synchroniser les référentiels et finaliser l'Epic 006.

## Notes de développement

La Story 006-3 clôture l'Epic 006 en bouclant les deux extrémités du cycle de migration :
1. **Validation de relecture sans Zep (Critère C4)** : S'assurer qu'un graphe migré depuis Zep Cloud vers Neo4j via l'ETL de la Story 006-2 est immédiatement lisible par l'ensemble de la chaîne applicative locale-first :
   - `GraphitiGraphStore.get_all_nodes()` et `get_all_edges()` restituent fidèlement les données ;
   - `ZepEntityReader.filter_defined_entities()` extrait correctement les nœuds typés grâce à l'attribut `entity_type` préservé ;
   - `OasisProfileGenerator` et `SimulationConfigGenerator` peuvent générer des personas et configurations de simulation valides sans jamais appeler Zep Cloud.
2. **Purge distante sécurisée (FR-6)** : Fournir aux utilisateurs le script `backend/scripts/purger_graphes_zep.py` pour nettoyer leur compte Zep Cloud une fois la migration validée. La suppression sur Zep Cloud étant irréversible, le script implémente une sécurité à double détente :
   - Mode interactif : saisie obligatoire et exacte de l'identifiant du graphe pour confirmer la suppression ;
   - Mode script / automatisé : exigence explicite du flag `--yes` pour lever le blocage ;
   - Mode `--dry-run` : affichage des graphes ciblés sans exécution de la requête `delete` ;
   - Mode `--mock` : exécution simulée déterministe pour la validation CI sans clé API.
3. **Zéro secret** : Tous les affichages console et rapports masquent `ZEP_API_KEY` via `masquer_secret`.

## Revue

*(Section à renseigner lors de la revue contradictoire BMad 4 couches)*

## Notes de complétion

*(Section à renseigner lors de la clôture de la story)*
