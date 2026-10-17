---
id: "012-1"
epic: "012"
titre: "Résolution stricte des identités d'acteurs et couverture de cohorte sans collision"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 012-1 — Résolution stricte des identités d'acteurs et couverture de cohorte sans collision

Lot A, priorité **P0**. En tant qu'analyste et utilisateur de MiroFish, je veux que les actions et événements consignés pendant la simulation soient attribués sans ambiguïté ni collision à leur acteur émetteur réel (notamment en éliminant l'inclusion accidentelle des 23 événements d'`Agent_1` dans le profil d'`Agent_16`), et que le tableau de couverture de cohorte ne comptabilise que les acteurs éligibles sans dupliquer les identifiants techniques avec les personas nommés.

Cette story répond directement aux exigences fonctionnelles **FR-01** (résolution stricte d'identités sans collision) et **FR-02** (filtrage et dédoublonnage de cohorte), et valide les critères de sortie **C1** (zéro collision d'identités) et **C2** (cohorte filtrée et dédoublonnée) de l'Epic 012.

---

## Définition de prêt

- [x] **Objectif compris et cadré** : Supprimer l'appariement heuristique par sous-chaîne (`key in text or text in key`) dans `CohortCoverageTable.build_from_simulation`. Mettre en place une résolution déterministe s'appuyant d'abord sur l'identifiant entier OASIS (`agent_id` int) et secondairement sur une normalisation canonique stricte (`==`). Filtrer `actor_selection.actors` pour ne retenir que les profils éligibles (`eligibility_status == "eligible"`), et substituer les alias techniques `Agent_X` par les personas nommés correspondants.
- [x] **Documents consultés** :
  - [PRD Epic 012](prd.md) : §2 (C1, C2), §3 (FR-01, FR-02), §4 (NFR-1, NFR-2).
  - [Architecture Epic 012](architecture.md) : §1 (diagramme de flux), §2.1 (résolution d'identités sans collision).
  - [Hub Epic 012](epic-012.md) : description globale, FR-01, FR-02, critères C1, C2.
  - [Audit R6](../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md) : anomalies `COVERAGE_ALIAS_COLLISION` et `DUPLICATE_COHORT_VIEW`.
  - `backend/app/models/cohort_coverage.py` : méthode `build_from_simulation` (l. 280-360), comparaison sous-chaîne (l. 336), itération d'acteurs (l. 296-308).
  - `backend/app/models/evidence_pack.py` : filtrage d'événements et structure d'`ObservedEvent`.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (qualité et herméticité des tests), §2.8 (gestion des plans).
- [x] **Dépendances résolues** :
  - Epics 005, 007, 008, 009, 010 et 011 sont intégralement validés et clos.
  - Filet de tests au démarrage : **1 761 tests réussis sur l'hôte**, 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Résolution déterministe d'identités (`AgentIdentityResolver`)** :
     - Pour chaque événement de simulation (`ObservedEvent`), extraction de l'`agent_id` (int ou int sérialisé).
     - Si l'`agent_id` est connu dans la table de correspondance d'instance OASIS, appariement direct avec le membre de cohorte correspondant.
     - Pour l'appariement nominatif (nom d'acteur), utilisation d'une égalité stricte normalisée (`unicodedata.normalize('NFKD', s).casefold().strip() == unicodedata.normalize('NFKD', t).casefold().strip()`). Interdiction formelle de l'opérateur `in` sur des chaînes d'identifiants.
  2. **Filtrage d'éligibilité de la cohorte cible** :
     - Seules les entités avec `eligibility_status == "eligible"` (ou sans statut explicite d'exclusion) sont intégrées dans le catalogue de base de la cohorte.
     - Les entités explicitement marquées `ineligible` (comme les passerelles de paiement, institutions tierces non participantes) sont exclues de `CohortCoverageTable`.
  3. **Dédoublonnage des alias techniques `Agent_X`** :
     - Lorsqu'un persona nommé correspond à `Agent_X` (via mapping OASIS ou configuration), une seule ligne est conservée dans `cohort_coverage.json` avec le nom réel du persona. Les événements émis sous l'étiquette `Agent_X` sont imputés à ce persona nommé.
  4. **Attribution exclusive des événements** :
     - Chaque événement d'action exécutée (`is_action_executed=True`) est comptabilisé pour **un seul** membre de cohorte.
- [x] **Stratégie de tests identifiée** :
  - Test paramétré vérifiant qu'`Agent_1` (23 événements) et `Agent_16` (18 événements) ne partagent aucun événement.
  - Test validant l'exclusion des entités inéligibles (`Stripe`, `CPAM`).
  - Test validant le dédoublonnage d'alias `Agent_0` avec `Simon`.
  - Non-régression totale sur les 23 tests de `test_cohort_coverage_time.py`.

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Zéro collision numérique d'alias (`Agent_1` vs `Agent_16`)** : Lorsqu'une simulation comporte des agents aux identifiants partageant un préfixe (ex : `Agent_1` et `Agent_16`, `Agent_2` et `Agent_20`), aucun événement de l'un n'est imputé à l'autre. Leurs listes d'événements sont strictement disjointes. | Test unitaire hermétique dédié prouvant l'étanchéité absolue des événements entre `Agent_1` et `Agent_16`. |
| **AC2** | **Appariement nominatif strict sans dérive par sous-chaîne** : Le rapprochement par nom repose sur l'égalité stricte normalisée (ignorant casse, accents et espaces surnuméraires). Aucun nom court (ex : « Dan ») ne s'approprie les actions d'un nom plus long (ex : « Daniel »). | Test unitaire testant des paires de noms à collision de sous-chaîne potentielle (« Dan » vs « Daniel », « Anne » vs « Marianne »). |
| **AC3** | **Filtrage des entités inéligibles** : Les entités du catalogue d'acteurs dont le statut d'éligibilité n'est pas `eligible` (ex : `ineligible`) ne figurent pas dans la table de couverture de cohorte finale. | Test unitaire injectant un `actor_selection` mixte (éligibles + inéligibles) et contrôlant l'absence des inéligibles dans la table finale. |
| **AC4** | **Dédoublonnage des alias techniques OASIS** : Si la simulation associe un persona nommé (ex : « Sophie ») à un agent technique (ex : `Agent_1`), seule la ligne de « Sophie » apparaît dans la cohorte avec le total de ses actions. La ligne `Agent_1` n'est pas dupliquée. | Test unitaire vérifiant l'unification d'un persona nommé et de son alias technique OASIS. |
| **AC5** | **Attribution univoque de chaque événement** : Aucun `event_id` n'apparaît dans les listes d'actions de deux membres de cohorte distincts. | Test de validation d'unicité sur l'ensemble des `actions_observed` de la table. |
| **AC6** | **Non-régression et suite hermétique** : Maintien des 1 761 tests du dépôt au vert, et ajout d'une suite hermétique complète validant AC1 à AC5. | Exécution complète de `pytest` (0 échec, 0 régression). |

---

## Définition de fini

- [x] Critères d'acceptation **AC1 à AC6** satisfaits et vérifiés par des tests automatisés passants.
- [x] Aucun événement partagé entre `Agent_1` et `Agent_16` (0 collision).
- [x] Entités inéligibles exclues de la cohorte.
- [x] Alias techniques dédoublonnés au profit des personas nommés.
- [x] Suite de tests hermétiques dédiée créée dans `backend/tests/test_cohort_identity_resolution.py`.
- [x] Suite complète de tests au vert sur l'hôte (filet $\ge 1768$ tests) et CI conforme.
- [x] Revue contradictoire BMAD à 4 couches réalisée, findings résolus.
- [x] Documents de suivi synchronisés (`docs/plans/012-fiabilite-preuves-et-publication/epic-012.md`, `docs/sprint-status.yaml`).

---

## Tâches

- [x] **T1 — Conception du composant `AgentIdentityResolver`** :
  - Créer la classe `AgentIdentityResolver` pour indexer les correspondances entre `agent_id` int, alias techniques `Agent_X` et personas nommés.
  - Implémenter la méthode de normalisation canonique et comparaison stricte (`==`) pour les noms.
- [x] **T2 — Refonte de `CohortCoverageTable.build_from_simulation`** :
  - Éliminer le matching heuristique par sous-chaîne (`key in text or text in key`).
  - Filtrer les entités de `actor_selection.actors` pour exclure les entités avec `eligibility_status == "ineligible"`.
  - Fusionner les alias techniques `Agent_X` dans les personas nommés.
  - Garantir l'attribution exclusive de chaque événement à un unique membre de cohorte.
- [x] **T3 — Écriture de la suite de tests hermétiques dédiée** :
  - Créer `backend/tests/test_cohort_identity_resolution.py` couvrant AC1 à AC5.
  - Reproduire le cas d'épreuve réel R6 (`Agent_1` vs `Agent_16`).
- [x] **T4 — Validation de la non-régression et intégration** :
  - Lancer la suite complète de tests pytest (`backend/.venv/bin/pytest`).
  - Valider `backend/scripts/validate_plans.py`.
- [x] **T5 — Revue contradictoire BMAD à 4 couches** :
  - Exécuter la revue contradictoire, appliquer les patches requis et clore la story.

---

## Notes de développement

### Diagnostic de la collision R6
Dans la sixième simulation Keova (`sim_ea4f3cfe1028`) :
- `Agent_1` a produit 23 événements réels.
- `Agent_16` a produit 18 événements réels.
- Lors de l'agrégation de `CohortCoverageTable` :
  ```python
  key = "agent_1"
  ev_agent_lower = "agent_16"
  if key in ev_agent_lower:  # VRAI ! "agent_1" est une sous-chaîne de "agent_16"
      member.actions_observed.append(...)
  ```
  Conséquence : `Agent_16` s'est vu attribuer ses 18 événements + les 23 événements d'`Agent_1` !
- De plus, 44 entités existaient dans `actors.json`, dont des tiers inéligibles (CPAM, Stripe, WhatsApp). Toutes ont été insérées dans la cohorte.
- Et les agents sans nom explicite ont été ajoutés sous la forme `Agent_0`, `Agent_1`... en doublon des personas nommés, aboutissant à 63 membres dans `cohort_coverage.json`.

---

## Revue

### Review Findings (Revue contradictoire BMAD à 4 couches)

- **Couche 1 (Spécification / PRD / Contrat AC1-AC6)** :
  - *Constat* : AC1 respecté, 23 événements d'`Agent_1` et 18 événements d'`Agent_16` restent strictement disjoints (`set.isdisjoint(...) == True`).
  - *Constat* : AC2 respecté, égalité stricte normalisée sans dérive par sous-chaîne (`Dan` vs `Daniel`, `Anne` vs `Marianne`).
  - *Constat* : AC3 respecté, entités inéligibles (`Stripe`, `CPAM`) exclues dès le recensement initial de la cohorte.
  - *Constat* : AC4 respecté, `simulation_config.json` permet l'unification des alias `Agent_0` et `Agent_1` vers leurs personas réels sans doublon.
  - *Constat* : AC5 respecté, unicité stricte de chaque `event_id` par membre.
  - *Constat* : AC6 respecté, 8 tests hermétiques passés au vert, suite complète portée à **1 768 tests passants sur l'hôte** (0 échec).

- **Couche 2 (Clean Architecture & Invariants SOLID/DRY)** :
  - *Constat* : Dépendances conformes (`cohort_coverage.py` réside dans `models/` et n'importe que des modèles et utilitaires légers).
  - *Constat* : Pas d'import circulaire. L'accès à `simulation_config.json` s'opère de façon découplée et résiliente via `Config.UPLOAD_FOLDER`.

- **Couche 3 (Sécurité des données & Robustesse)** :
  - *Constat* : Robustesse assurée en cas de `ev.agent_name` manquant ou vide (repli sur `f"Agent_{ev.agent_id}"`).
  - *Constat* : Garde défensive ajoutée pour `ev.agent_id is not None` (Patch appliqué).

- **Couche 4 (Qualité des tests & Herméticité)** :
  - *Constat* : Isolation complète via `tmp_path` et `monkeypatch` pour les chemins de simulation.
  - *Constat* : Zéro dépendance réseau ni effet de bord persistant.

#### Actions issues de la revue (Findings)
- [x] [Review][Patch] Corriger l'évaluation falsy de '0' lors de l'enregistrement dynamique de persona (`ev.agent_id is not None`) [backend/app/models/cohort_coverage.py:483]
- [x] [Review][Patch] Sécuriser la conversion int(aid) contre les entrées malformées et ajouter une garde sur simulation_id vide [backend/app/models/cohort_coverage.py:75-90]
- [x] [Review][Patch] Initialiser de façon exhaustive alias_to_name et name_to_canonical depuis agent_id_map dans __init__ [backend/app/models/cohort_coverage.py:49-54]
- [x] [Review][Patch] Ajouter des tests hermétiques unitaires pour agent_id = 0 et configs corrompues [backend/tests/test_cohort_identity_resolution.py]

#### Annexe des rejets (Rejected)
- [Low][Rejected] Extension de AGENT_ALIAS_RE aux alias avec espace ("Agent 1") : écarté car OASIS et le moteur MiroFish produisent exclusivement le format "Agent_{id}".

---

## Notes de complétion

- **Date de complétion** : 17 octobre 2026.
- **Statut** : Clos avec succès (`done`).
- **Filet de tests validé** : **1 771 tests réussis sur l'hôte** (1 760 initiaux + 11 nouveaux tests hermétiques dédiés), 1 warning bénin déprécié pydantic amont, 0 échec. **9 tests Node frontend** au vert.
- **Artefacts produits / modifiés** :
  - `backend/app/models/cohort_coverage.py` : implémentation de `normalize_agent_name`, `AgentIdentityResolver` et refonte de `build_from_simulation`.
  - `backend/tests/test_cohort_identity_resolution.py` : 11 tests hermétiques dédiés couvrant AC1 à AC5 et les cas limites de revue.
