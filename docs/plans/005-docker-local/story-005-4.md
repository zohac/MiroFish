---
id: "005-4"
epic: "005"
titre: "Persistance des données Neo4j et cycle de vie des volumes"
statut: backlog
auteur: agent
format: "2"
---

# Story 005-4 — Persistance des données Neo4j et cycle de vie des volumes

## Définition de prêt

- [ ] Objectif compris : valider et prouver que les données du graphe de connaissances stockées dans Neo4j sous Docker survivent intégralement aux cycles d'arrêt et de redémarrage des conteneurs via Docker Compose (`docker compose down` puis `docker compose up -d`), grâce au volume nommé `neo4j_data`, et qu'une purge volontaire (`docker compose down -v`) réinitialise proprement la base sans laisser de résidus orphelins.
- [ ] Documents consultés : [PRD](prd.md) (notamment critère C3, exigence NFR-3), [Architecture](architecture.md) (§4), [Epic 005](epic-005.md), [`docker-compose.yml`](../../docker-compose.yml), [AGENTS.md](../../AGENTS.md) (§2.9, §3).
- [ ] Prérequis vérifiés : `docker-compose.yml` unifié configuré avec les volumes nommés `neo4j_data` et `neo4j_logs`, service `neo4j` opérationnel avec healthcheck Bolt (`cypher-shell`), service `backend` opérationnel et validé sous Docker (Stories 005-1, 005-2, 005-3).
- [ ] Stratégie de test identifiée : conception d'une sonde de vérification automatisée (`backend/scripts/verifier_persistance_neo4j_docker.py`) exécutant un cycle réel (insertion de nœuds/relations témoins, arrêt `down`, redémarrage `up -d --wait`, validation de l'intégrité à 100 %, puis validation de la purge sur `down -v`), et suite de tests unitaires hermétiques validant la déclaration et le cycle de vie des volumes (`backend/tests/test_docker_volume_persistence.py`).

## Définition de fini

- [ ] Sonde de vérification automatisée de persistance opérationnelle (`backend/scripts/verifier_persistance_neo4j_docker.py`) démontrant la conformité au critère C3 du PRD.
- [ ] Preuve formelle que 100 % des nœuds et arêtes créés dans Neo4j sont préservés après un cycle `docker compose down && docker compose up -d` (sans option `-v`).
- [ ] Preuve formelle qu'un cycle `docker compose down -v` purge explicitement le volume `neo4j_data` et réinitialise l'instance à un état vierge.
- [ ] Vérification du comportement des montages bind backend (`backend/uploads`, `backend/simulations`) garantissant la non-régression sur les fichiers téléversés et rapports générés.
- [ ] Suite de tests unitaires hermétiques (`backend/tests/test_docker_volume_persistence.py`) validant la configuration et le comportement attendu.
- [ ] Filet global de tests (671 tests + nouveaux tests) et outillage (`ruff check .`, `validate_plans.py`) 100 % passants au vert.

## Tâches

- [ ] Développer la sonde de vérification autonome de persistance (`backend/scripts/verifier_persistance_neo4j_docker.py`).
- [ ] Exécuter le cycle de vérification de persistance (écriture de graphe témoin -> arrêt conteneur -> redémarrage -> validation 100 % intègre).
- [ ] Vérifier le comportement de réinitialisation contrôlée lors de l'exécution de `docker compose down -v`.
- [ ] Contrôler la préservation des données applicatives dans les volumes bind `./backend/uploads` et `./backend/simulations`.
- [ ] Écrire la suite de tests unitaires hermétiques (`backend/tests/test_docker_volume_persistence.py`).
- [ ] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [ ] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

## Notes de développement

La constitution ([`AGENTS.md`](../../AGENTS.md) §2.9) et l'Architecture ([`architecture.md`](architecture.md) §4) posent un principe strict pour la gestion des données persistantes :
- Les données Neo4j résident dans le volume nommé `neo4j_data` monté sur `/data`.
- Les logs Neo4j résident dans le volume nommé `neo4j_logs` monté sur `/logs`.
- La commande standard `docker compose down` détruit les conteneurs éphémères mais préserve les volumes nommés et bind.
- Seule l'instruction explicite `docker compose down -v` détruit le volume `neo4j_data` et le graphe sous-jacent.

La Story 005-4 met en place l'outillage de validation et les tests automatisés apportant la preuve empirique et reproductible de cette invariant d'infrastructure (critère de sortie C3 du PRD).

## Revue

- **Couche Contrat & Architecture** : À compléter lors de la revue BMad.
- **Couche Hermétisme & Sécurité** : À compléter lors de la revue BMad.
- **Couche Tests & Qualité** : À compléter lors de la revue BMad.
- **Couche Robustesse & CI** : À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
