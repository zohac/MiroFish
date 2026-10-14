---
id: "007-5"
epic: "007"
titre: "Cohérence projet (E5) et composition avec ActorClassifierService"
statut: backlog
auteur: "Simon"
format: "2"
---

# Story 007-5 — Cohérence projet (E5) et composition avec ActorClassifierService

En tant qu'utilisateur de MiroFish, je veux que la configuration et l'exécution de
simulations sociales réutilisent de façon stable l'ontologie dynamique déjà validée
pour le projet (évitant des réévaluations superflues), et que le classifieur
d'éligibilité des acteurs (`ActorClassifierService`) tire parti des types d'entités
déjà typés par l'ontologie pour court-circuiter les appels LLM inutiles, afin de
garantir la cohérence inter-simulations, d'accélérer la sélection des personas et
de réduire le coût d'inférence.

**Lot C — P1.** Exigences : FR-5 ; NFR-1, NFR-4 ; critères de sortie C5, C6 et contribution à C8.
Dépendance : 007-4 terminée (`done`).
Cette story implémente la validation de cohérence ontologique du projet lors du
lancement de simulation (événement E5), la fixation de `applied_ontology_id` dans
la configuration de simulation, ainsi que la composition formelle entre le label
d'ontologie du nœud et la cascade de qualification d'acteurs de l'Epic 009.

## Définition de prêt

- [ ] PRD §3.1/§4/C5/C6, architecture §5/§6, epic-007 §1/§4 et constitution consultés.
- [ ] Story 007-4 terminée (`done`) : modèle `OntologyVersion`, `applied_ontology_id`, magasin et événements E1-E4 opérationnels.
- [ ] Code source existant analysé : `ActorClassifierService` (`app/services/actor_classifier.py`), `SimulationManager` (`app/services/simulation_manager.py`), `OASISProfileGenerator` (`app/services/oasis_profile_generator.py`).
- [ ] Table de correspondance type d'ontologie → `ActorRole` définie comme injective et finie (types personnes → `PERSON`, types organisations → `ORGANIZATION`, types passifs → rôles passifs/`INELIGIBLE`, autres → `REVIEW`).
- [ ] Scénarios de test C5 (partage de version d'ontologie entre simulations d'un même projet, séparation inter-projets) et C6 (court-circuit du LLM quand le label est présent, retombée sur cascade 009-1 quand absent) conçus avec mocks hermétiques.

### Critères d’acceptation

| Réf. | Contrat mesurable | Vérification |
|---|---|---|
| AC1 | **Cohérence projet (C5) et événement E5** : Deux simulations successives exécutées sur un même projet, sans événement modificateur intermédiaire (aucun ajout de document E1, aucune modification substantielle de brief E2, aucune demande explicite E3), partagent exactement la même ontologie (`applied_ontology_id` identique, même contenu). La configuration de simulation (`SimulationConfig` / métadonnées de simulation) référence explicitement `applied_ontology_id`. | Tests d'intégration exécutant deux préparations successives sur un projet figé et vérifiant l'égalité stricte des `applied_ontology_id` et l'absence de régénération. |
| AC2 | **Isolation stricte inter-projets (C5)** : Deux projets distincts (avec documents ou briefs distincts) possèdent des ontologies indépendantes avec des `applied_ontology_id` différents. Une modification ou régénération sur le projet A n'altère en rien l'ontologie appliquée au projet B. | Test d'intégration multi-projets créant deux projets distincts et vérifiant l'étanchéité des versions et des magasins. |
| AC3 | **Signal primaire d'ontologie dans `ActorClassifierService` (C6)** : `ActorClassifierService` consulte le label d'ontologie custom du nœud comme signal primaire d'éligibilité via une table de correspondance injective :<br/>• Types personnes (`PersonEntity`, `Citizen`, `Actor`, etc.) $\to$ `ActorRole.PERSON`, `EligibilityStatus.ELIGIBLE`.<br/>• Types organisations (`MediaOrganization`, `Organization`, `Company`, `Institution`, etc.) $\to$ `ActorRole.ORGANIZATION`, `EligibilityStatus.ELIGIBLE`.<br/>• Types passifs (`Product`, `Infrastructure`, `Event`, `Concept`, `Location`, etc.) $\to$ `ActorRole` passif associé, `EligibilityStatus.INELIGIBLE`.<br/>• Types non reconnus ou ambigus $\to$ `ActorRole.UNKNOWN`, `EligibilityStatus.REVIEW`. | Tests unitaires sur les différentes classes d'entités vérifiant les rôles et statuts d'éligibilité attribués de façon déterministe. |
| AC4 | **Court-circuit LLM prouvé (C6)** : Lorsqu'un nœud porte un label d'ontologie custom reconnu avec une correspondance univoque (ex. `PersonEntity` ou `MediaOrganization`), `ActorClassifierService` qualifie l'entité sans aucun appel au client LLM (`client.chat_json` n'est pas appelé). La justification (`rationale`) mentionne explicitement la déduction par le signal d'ontologie appliquée et `confidence=1.0`. | Test unitaire avec mock LLM espion vérifiant 0 appel LLM quand le label est suffisant. |
| AC5 | **Préservation de la cascade 009-1 en l'absence de label (C6)** : Si le nœud ne porte aucun label custom (ou seulement `:Entity` / `:Node`), `ActorClassifierService` retombe sur la cascade standard en deux passes (Passe 1 syntaxique déterministe, Passe 2 LLM structuré). Les résultats canoniques de l'Epic 009 (dont `space-bunny` avec 8/8 acteurs retenus et 0 faux acteur) sont rigoureusement préservés. | Exécution des tests de régression de `test_actor_classifier.py` et `test_actor_eligibility_pipeline.py`. |
| AC6 | **Transmission de l'ontologie à la génération de profils personas** : Lors de la préparation de simulation (`prepare_simulation`), `OASISProfileGenerator` intègre le type d'ontologie d'origine dans les métadonnées de rôle des personas générés pour assurer la traçabilité ascendante vers le graphe. | Tests de composant sur `prepare_simulation` validant la présence du type d'ontologie dans les personas créés. |
| AC7 | **Filet de tests hermétiques et non-régression (C8)** : Au moins **20 nouveaux tests hermétiques** ajoutés couvrant la cohérence C5, l'événement E5, le court-circuit C6 et la non-régression. Suite globale portée à $\ge 1505$ tests passants sur l'hôte, `ruff check .` propre, `validate_plans.py` conforme. | Exécution complète de pytest, ruff et validate_plans. |

## Définition de fini

- [ ] AC1 à AC7 satisfaits avec preuves de tests unitaires et d'intégration hermétiques associées.
- [ ] Événement E5 et persistance de `applied_ontology_id` dans la configuration de simulation implémentés et testés.
- [ ] Table de correspondance de typage injectée dans `ActorClassifierService`.
- [ ] Court-circuit de l'appel LLM validé par mock étanche quand le label d'ontologie est suffisant.
- [ ] Préservation stricte des 921+ tests de l'Epic 009 sans régression.
- [ ] Filet global $\ge 1505$ tests passants sur l'hôte, `ruff check .` propre, `validate_plans.py` conforme.
- [ ] Revue contradictoire BMAD 4 couches effectuée et patches traités.
- [ ] Notes de complétion rédigées, suivi `sprint-status.yaml`, `STATUS.md` et `epic-007.md` actualisés.

## Tâches

- [ ] T1 — Définition de la table de correspondance ontologique (`ONTOLOGY_ROLE_MAPPING`) dans `app/services/actor_classifier.py` (AC3).
- [ ] T2 — Implémentation du court-circuit de classification par signal d'ontologie dans `ActorClassifierService` (AC3, AC4).
- [ ] T3 — Validation de la retombée sur la cascade 009-1 et non-régression sur le banc d'éligibilité (AC5).
- [ ] T4 — Câblage de l'événement E5 et persistance de `applied_ontology_id` dans la préparation de simulation (`prepare_simulation` / `SimulationManager`) (AC1, AC2, AC6).
- [ ] T5 — Isolation inter-projets et vérification d'indépendance des versions d'ontologie (AC2).
- [ ] T6 — Rédaction des suites de tests unitaires et d'intégration (`tests/test_ontology_actor_composition.py`, `tests/test_ontology_project_consistency.py`) (AC7).
- [ ] T7 — Revue contradictoire BMAD 4 couches et validation outillée globale (AC7).

## Notes de développement

### Architecture et flux de données

```
                      +-----------------------------+
                      |           Project           |
                      |  (applied_ontology_id: ont) |
                      +--------------+--------------+
                                     |
                                     v
                       +---------------------------+
                       |    OntologyVersionStore   |
                       | (entity_types, edge_types)|
                       +-------------+-------------+
                                     |
           +-------------------------+-------------------------+
           |                                                   |
           v (Signal primaire)                                 v (Traçabilité E5)
+-----------------------+                            +--------------------+
| ActorClassifierService|                            | SimulationManager  |
| - Label check         |                            | - prepare_sim      |
| - ONTOLOGY_ROLE_MAP   |                            | - SimulationConfig |
| - Court-circuit LLM   |                            |   applied_onto_id  |
+-----------+-----------+                            +---------+----------+
            |                                                  |
            v                                                  v
+-----------------------+                            +--------------------+
| ActorClassification   |                            |  OASIS Personas    |
| (Eligible/Ineligible) |                            | (metadata rôle ont)|
+-----------------------+                            +--------------------+
```

1. **Table de correspondance ontologique** :
   La table fait correspondre les types d'entités d'ontologie inférés ou standard (`PersonEntity`, `MediaOrganization`, `Citizen`, `Company`, `Institution`, etc.) aux rôles `ActorRole` (`PERSON`, `ORGANIZATION`, `PRODUCT`, `EVENT`, etc.).
   Elle est injective et conservative : tout type non expressément identifié comme un acteur actif potentiel (`PERSON`, `ORGANIZATION`) tombe en `REVIEW` ou en rôle passif `INELIGIBLE`.

2. **Événement E5 (Cohérence simulation)** :
   Lorsqu'une simulation est lancée via `prepare_simulation` ou l'API de simulation, le service lit `project.applied_ontology_id`. Aucune réévaluation d'ontologie n'est opérée : l'ontologie appliquée fait foi pour toute la durée de la simulation.

## Revue

Revue contradictoire BMAD à 4 couches à réaliser lors de la phase de revue :
- **Couche 1 : blind-hunter** (sécurité des types, résilience aux labels inattendus, format de données).
- **Couche 2 : edge-case-hunter** (nœuds multi-labels, collisions de noms, entités sans labels d'ontologie).
- **Couche 3 : verification-gap** (preuve de court-circuit 0 appel LLM par mock, vérification du maintien de la cascade 009-1).
- **Couche 4 : acceptance-auditor** (validation de 100 % des critères AC1 à AC7).

## Notes de complétion

*À renseigner lors de la clôture du ticket (passage en `done`).*
