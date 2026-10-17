---
id: "012-2"
epic: "012"
titre: "Rôles de scénario et statuts de décision d'adoption déterministes"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 012-2 — Rôles de scénario et statuts de décision d'adoption déterministes

Lot A, priorité **P0**. En tant qu'analyste et utilisateur de MiroFish, je veux que les rôles attribués aux membres de la cohorte reflètent fidèlement leur nature (notamment en évitant d'étiqueter automatiquement un fondateur, un membre d'équipe ou une institution comme « PROSPECT »), et que les statuts de décision d'adoption soient déterministes et étayés par des faits observables (en éliminant catégoriquement l'attribution d'`ADOPTED` par simple absence d'objections ou sur un post social anodin), avec une catégorie `NOT_APPLICABLE` pour les acteurs non clients afin de ne pas fausser les taux d'adoption.

Cette story répond directement à l'exigence fonctionnelle **FR-03** (qualification honnête des décisions et des rôles de scénario) et valide le critère de sortie **C3** (rôles et adoptions étayés, 0 faux statut `ADOPTED` déduit de la seule absence d'objection) de l'Epic 012.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  - Supprimer le mapping aveugle `ActorRole.PERSON -> ScenarioRole.PROSPECT` dans `CohortCoverageTable.build_from_simulation`.
  - Enrichir `ScenarioRole` avec `FOUNDER`, `TEAM_MEMBER`, `EXISTING_USER`, `PROSPECT`, `PARTNER`, `INSTITUTION`, `UNKNOWN`.
  - Enrichir `DecisionStatus` avec `NOT_APPLICABLE`, `NO_DECISION`, `INTERESTED`, `DEMO_REQUESTED`, `REJECTED_EXPRESSED`, `ADOPTED_VERIFIED`.
  - Assigner `NOT_APPLICABLE` aux fondateurs, collaborateurs internes et institutions non clientes.
  - Interdire l'inférence d'`ADOPTED` par la seule absence d'objections : exiger une preuve probante d'acte d'adoption.
- [x] **Documents consultés** :
  - [PRD Epic 012](prd.md) : §2 (Critère C3), §3 (FR-03), §4 (NFR-1, NFR-2, NFR-3).
  - [Architecture Epic 012](architecture.md) : §2.2 (Rôles de scénario & statuts de décision déterministes).
  - [Hub Epic 012](epic-012.md) : FR-03, critère C3.
  - [Audit R6](../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md) : anomalies de sur-optimisme décisionnel et confusion de rôles.
  - `backend/app/models/cohort_coverage.py` : `ScenarioRole` (l. 164), `DecisionStatus` (l. 213), `build_from_simulation` (l. 410-580).
  - `backend/app/models/simulation_brief.py` : structuration des audiences, fondateurs et objectifs.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (herméticité des tests), §2.8 (gestion des plans).
- [x] **Dépendances résolues** :
  - Story 012-1 validée et close (résolution univoque des identités, filtrage d'éligibilité).
  - Filet de tests au démarrage : **1 771 tests réussis sur l'hôte**, 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Hiérarchie de résolution des rôles de scénario** :
     - Étape 1 : Rôle défini explicitement dans le `simulation_brief` (fondateur nommé, audiences cibles, partenaires).
     - Étape 2 : Rôle issu de la qualification d'acteurs `actor_selection` ou de la configuration d'agents.
     - Étape 3 : Repli par défaut sur `ScenarioRole.UNKNOWN` (interdiction d'inférer un rôle commercial par défaut).
  2. **Statut d'adoption anti-affabulation** :
     - Pour un acteur éligible ayant agi (`action_count > 0`) sans objection bloquante : le statut par défaut est `NO_DECISION` ou `INTERESTED` (si marque d'intérêt lexicale), jamais `ADOPTED`.
     - Le statut `ADOPTED_VERIFIED` nécessite la confirmation d'une conversion avérée (verbatim ou argument d'action attestant de la souscription, achat ou adoption formelle).
  3. **Isolation des non-prospects (`NOT_APPLICABLE`)** :
     - Tout acteur de type `FOUNDER`, `TEAM_MEMBER` ou `INSTITUTION` reçoit le statut `DecisionStatus.NOT_APPLICABLE`.
     - La méthode `adoption_rate` de `CohortCoverageTable` calcule le ratio uniquement sur les prospects réels (`scenario_role == ScenarioRole.PROSPECT` ou audiences cibles), en ignorant strictement les membres `NOT_APPLICABLE`.
  4. **Rétrocompatibilité ascendante** :
     - Désérialisation transparente des anciens exports comportant `ADOPTED`, `REJECTED`, `UNDECIDED`.
- [x] **Stratégie de tests identifiée** :
  - Test vérifiant qu'un fondateur (ex: Simon) est qualifié `FOUNDER` avec décision `NOT_APPLICABLE`.
  - Test vérifiant qu'un prospect actif sans objection est qualifié `NO_DECISION` ou `INTERESTED`, et JAMAIS `ADOPTED`.
  - Test validant l'attribution d'`ADOPTED_VERIFIED` uniquement en présence de marqueurs d'adoption probants.
  - Test validant le calcul du taux d'adoption sans pollution par les acteurs non clients.
  - Test de désérialisation rétrocompatible d'un fichier `cohort_coverage.json` hérité.

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Typologie de rôles sans inférence commerciale aveugle** : Les rôles de scénario incluent `FOUNDER`, `TEAM_MEMBER`, `EXISTING_USER`, `PROSPECT`, `PARTNER`, `INSTITUTION`, `UNKNOWN`. Aucun acteur n'est forcé en `PROSPECT` par simple statut `PERSON`. Si aucun rôle précis n'est déductible, le rôle attribué est `UNKNOWN`. | Test unitaire injectant divers profils et vérifiant l'attribution fidèle des rôles sans biais systématique en `PROSPECT`. |
| **AC2** | **Statut `NOT_APPLICABLE` pour les fondateurs et acteurs internes** : Tout persona identifié comme fondateur (`FOUNDER`), membre de l'équipe (`TEAM_MEMBER`) ou tiers institutionnel (`INSTITUTION`) se voit assigner le statut `DecisionStatus.NOT_APPLICABLE`. | Test unitaire contrôlant que le fondateur (Simon) et les organisations institutionnelles reçoivent `NOT_APPLICABLE`. |
| **AC3** | **Zéro faux statut `ADOPTED` par absence d'objection (Anti-Affabulation)** : Un membre de la cohorte ayant produit des messages sans formuler d'objection est classé `NO_DECISION` ou `INTERESTED`, mais en aucun cas `ADOPTED`. L'attribution d'`ADOPTED_VERIFIED` exige la présence de preuves d'action probantes. | Test unitaire avec un persona émettant des commentaires sociaux sans objection : statut attendu $\ne$ `ADOPTED`. |
| **AC4** | **Nuance des statuts décisionnels d'adoption** : `DecisionStatus` gère distinctement `NOT_APPLICABLE`, `PRESENT_NO_ACTION`, `REJECTED_EXPRESSED`, `HESITANT`, `INTERESTED`, `DEMO_REQUESTED`, `ADOPTED_VERIFIED`, `NO_DECISION`. | Test unitaire testant chaque transition décisionnelle sur corpus de verbatims et d'arguments d'actions. |
| **AC5** | **Calcul assaini du taux d'adoption de la cohorte** : Le calcul du ratio d'adoption et des statistiques de cohorte exclut strictement les membres `NOT_APPLICABLE` du dénominateur d'adoption. | Test vérifiant que la présence de fondateurs ou d'institutions ne dilue ni ne gonfle artificiellement le pourcentage d'adoption des prospects. |
| **AC6** | **Rétrocompatibilité et non-régression** : Les anciens fichiers de simulation portant les valeurs historiques (`ADOPTED`, `REJECTED`) sont relus sans erreur via `CohortCoverageTable.from_dict()`. Filet complet $\ge 1 771$ tests au vert sur l'hôte. | Test de désérialisation avec fixtures historiques et exécution complète de pytest (0 régression). |

---

## Définition de fini

- [x] Critères d'acceptation **AC1 à AC6** satisfaits et vérifiés par des tests automatisés passants.
- [x] Suppression définitive du forçage aveugle `ActorRole.PERSON -> ScenarioRole.PROSPECT`.
- [x] Statut `DecisionStatus.NOT_APPLICABLE` attribué et ignoré dans les ratios de prospects.
- [x] Statut `ADOPTED` / `ADOPTED_VERIFIED` conditionné à une action probante démontrée.
- [x] Suite de tests hermétiques dédiée créée dans `backend/tests/test_cohort_roles_and_decisions.py`.
- [x] Non-régression totale sur les suites `test_cohort_coverage_time.py` et `test_cohort_identity_resolution.py`.
- [x] Suite complète de tests au vert sur l'hôte (filet $\ge 1 780$ tests) et CI conforme.
- [x] Revue contradictoire BMAD à 4 couches réalisée, findings résolus.
- [x] Documents de suivi synchronisés (`epic-012.md`, `sprint-status.yaml`, `AGENTS.md`).

---

## Tâches

- [x] **T1 — Extension des enums `ScenarioRole` et `DecisionStatus`** :
  - Ajouter `FOUNDER`, `TEAM_MEMBER`, `EXISTING_USER`, `PARTNER`, `INSTITUTION`, `UNKNOWN` dans `ScenarioRole`.
  - Ajouter `NOT_APPLICABLE`, `NO_DECISION`, `INTERESTED`, `DEMO_REQUESTED`, `REJECTED_EXPRESSED`, `ADOPTED_VERIFIED` dans `DecisionStatus`.
  - Sécuriser `from_str()` pour la tolérance et la rétrocompatibilité des anciens termes.
- [x] **T2 — Algorithme d'attribution des rôles de scénario** :
  - Découpler l'attribution de rôle de `ActorRole.PERSON`.
  - Analyser les indices du brief (`simulation_brief.py`), des personas et des attributs de configuration pour qualifier fondateurs, équipes et prospects.
  - Repli par défaut vers `ScenarioRole.UNKNOWN`.
- [x] **T3 — Qualification probante des décisions et statuts d'adoption** :
  - Assigner `NOT_APPLICABLE` aux rôles non prospects.
  - Détecter les demandes de démo (`DEMO_REQUESTED`) et les marques d'intérêt (`INTERESTED`).
  - Détecter les objections motivées (`REJECTED_EXPRESSED`, `HESITANT`).
  - N'attribuer `ADOPTED_VERIFIED` qu'en présence d'actes d'engagement avérés.
  - Assigner `NO_DECISION` en cas d'activité sans preuve d'adoption.
- [x] **T4 — Refonte du calcul des métriques de cohorte** :
  - Mettre à jour `status_summary`, `adoption_rate` et les rendus Markdown dans `CohortCoverageTable` pour isoler les membres `NOT_APPLICABLE`.
  - Mettre à jour les labels FR/EN associés.
- [x] **T5 — Suite de tests hermétiques dédiée et non-régression** :
  - Créer `backend/tests/test_cohort_roles_and_decisions.py` validant AC1 à AC6.
  - Vérifier la non-régression de l'ensemble des 1 771 tests existants.
- [x] **T6 — Revue contradictoire BMAD à 4 couches et clôture** :
  - Mener la revue contradictoire, appliquer les patches requis et synchroniser le statut.

---

## Notes de développement

### Anomalie constatée lors de l'audit R6
Dans la simulation Keova R6 (`sim_ea4f3cfe1028`) :
- Simon (le fondateur du projet) et Sophie (cofondatrice) ont été classés comme `PROSPECT` car ils étaient des personnes physiques (`ActorRole.PERSON`).
- Le calcul de décision dans `CohortCoverageTable.build_from_simulation` indiquait :
  ```python
  if action_count == 0:
      decision = DecisionStatus.PRESENT_NO_ACTION
  elif entry["objections"]:
      decision = DecisionStatus.HESITANT  # ou REJECTED
  else:
      decision = DecisionStatus.ADOPTED
  ```
- Conséquence : Simon et Sophie ont été comptabilisés comme des « prospects ayant adopté » leur propre solution !
- De plus, 12 personas ayant émis de simples salutations ou questions générales sans objections ont été automatiquement convertis en « clients adoptés », gonflant artificiellement le taux de conversion à plus de 80 %.
- La story 012-2 corrige structurellement ce biais en introduisant le principe de preuve probante pour l'adoption et l'exclusion des non-clients via `NOT_APPLICABLE`.

---

## Revue

### Review Findings (Revue contradictoire BMAD à 4 couches)

- **Couche 1 (Spécification / PRD / Contrat AC1-AC6)** :
  - *Constat AC1* : Conforme. `ScenarioRole` intègre `FOUNDER`, `TEAM_MEMBER`, `EXISTING_USER`, `PROSPECT`, `PARTNER`, `INSTITUTION`, `UNKNOWN`. Aucun forçage systématique n'est appliqué depuis `ActorRole.PERSON` (repli propre sur `ScenarioRole.UNKNOWN`).
  - *Constat AC2* : Conforme. Fondateurs, collaborateurs et institutions reçoivent `DecisionStatus.NOT_APPLICABLE` dès la détection de rôle.
  - *Constat AC3* : Conforme. Règle anti-affabulation C3 validée : les interactions sociales sans objection sont qualifiées `NO_DECISION` ou `INTERESTED`, jamais `ADOPTED`.
  - *Constat AC4* : Conforme. Détection probante distincte de `ADOPTED_VERIFIED`, `DEMO_REQUESTED`, `INTERESTED`, `HESITANT`, `REJECTED_EXPRESSED`, `NO_DECISION`.
  - *Constat AC5* : Conforme. Propriété `adoption_rate` assainie excluant strictement les acteurs `NOT_APPLICABLE` et fondateurs du dénominateur.
  - *Constat AC6* : Conforme. Rétrocompatibilité transparente avec les valeurs héritées `ADOPTED`, `REJECTED`, `UNDECIDED`. 9 tests hermétiques dédiés passants dans `test_cohort_roles_and_decisions.py`.

- **Couche 2 (Clean Architecture & Invariants SOLID/DRY)** :
  - *Constat* : Intégrité architecturale préservée. Découplage complet de la résolution des rôles via `AgentIdentityResolver` et `SimulationBrief`.
  - *Constat* : Aucun hardcoding propre à Keova : motifs d'extraction et lexiques universels FR/EN (NFR-1).

- **Couche 3 (Sécurité des données & Robustesse)** :
  - *Constat* : Normalisation Unicode NFKD étendue aux parsing de chaînes `ScenarioRole.from_str()` et `DecisionStatus.from_str()` (gère les accents comme « employé », « régulateur », « intéressé » sans repli silencieux erroné).
  - *Constat* : Extraction des fondateurs durcie par regex avec délimiteurs de ponctuation et conjonctions, évitant les absorptions de phrases complètes.
  - *Constat* : Prise en charge des objections explicites transmises dans `ev.action_args["objection"]` ou `ev.action_args["objections"]`.

- **Couche 4 (Qualité des tests & Herméticité)** :
  - *Constat* : Suite complète exécutée avec succès sur l'hôte : **1 785 tests unitaires et d'intégration réussis** (0 échec), 1 warning pydantic amont inoffensif.
  - *Constat* : Tests frontend Node validés (9/9 passés).

#### Actions issues de la revue (Findings)
- [x] [Review][Patch] Éliminer la troncature prématurée à 160 caractères des citations pour la détection probante des décisions en analysant le texte complet des actions [backend/app/models/cohort_coverage.py:431-432, 479]
- [x] [Review][Patch] Assouplir le lookahead de la regex d'extraction des fondateurs depuis le brief pour supporter les phrasés naturels [backend/app/models/cohort_coverage.py:324-338]
- [x] [Review][Patch] Enrichir les motifs lexicaux d'adoption au présent, de demande de démo et d'intérêt exploratoire [backend/app/models/cohort_coverage.py:442-455]
- [x] [Review][Patch] Résoudre directement les membres et alias via cls.__members__ dans ScenarioRole.from_str() et DecisionStatus.from_str() [backend/app/models/cohort_coverage.py:106-108, 186-188]
- [x] [Review][Patch] Gérer l'insensibilité à la casse des chaînes de rôles d'acteurs dans ScenarioRole.from_actor_role() [backend/app/models/cohort_coverage.py:135-152]
- [x] [Review][Defer] Arbitrage de préséance entre ADOPTED_VERIFIED et objections antérieures en cas de conversion tardive [backend/app/models/cohort_coverage.py:471-477] — deferred: préservation du principe anti-affabulation conservateur d'Epic 012

#### Annexe des rejets (Rejected)
- [Low][Rejected] Ajout d'un statut `ABSTAINED` distinct de `NO_DECISION` : rejeté pour préserver la simplicité de l'énumération et la conformité avec le PRD Epic 012.

---

## Notes de complétion

- **Date de complétion** : 17 octobre 2026.
- **Statut** : Clos avec succès (`done`).
- **Filet de tests validé** : **1 785 tests réussis sur l'hôte** (1 771 initiaux + 14 tests hermétiques dédiés dans `test_cohort_roles_and_decisions.py` dont 5 validant les patches de la revue BMAD), 1 warning bénin déprécié pydantic amont, 0 échec. **9 tests Node frontend** au vert.
- **Artefacts produits / modifiés** :
  - `backend/app/models/cohort_coverage.py` : extensions de `ScenarioRole`, `DecisionStatus`, hiérarchie de résolution des rôles, inférence anti-affabulation, calcul assaini de `adoption_rate` et rétrocompatibilité des alias.
  - `backend/tests/test_cohort_roles_and_decisions.py` : 14 tests hermétiques dédiés (9 initiaux couvrant AC1 à AC6 + 5 tests issus des findings BMAD).
  - `backend/tests/test_cohort_coverage_time.py` : adaptation de l'assertion sur `status_summary` multi-clés.

