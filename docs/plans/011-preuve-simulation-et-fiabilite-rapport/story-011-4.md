---
id: "011-4"
epic: "011"
titre: "Tableau de couverture de cohorte, anti-biais de confirmation (section limites) et respect du temps simulé"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 011-4 — Tableau de couverture de cohorte, anti-biais de confirmation (section limites) et respect du temps simulé

Lot B, priorité **P0**. En tant qu'analyste et décideur s'appuyant sur les synthèses de MiroFish, je veux qu'un tableau de couverture de cohorte récapitule systématiquement l'engagement de chaque persona exigé dans le scénario (rôle attribué, actions réellement observées avec identifiants `event_id`, objections exprimées, décision finale), qu'un persona silencieux soit explicitement consigné comme `present_no_action` sans aucune fabrication artificielle d'événements, qu'une rubrique dédiée aux objections non levées, contradictions et limites soit obligatoirement présente dans le rapport, que la synthèse exécutive ne puisse pas affirmer un consensus unanime ou une conversion totale en présence de refus dans la cohorte, que l'horizon temporel déclaré dans le brief (`time_horizon`) soit strictement respecté en interdisant toute extrapolation hors horizon présentée comme observation empirique, et qu'aucune métrique quantitative fantôme ne puisse être formulée sans formule ni données calculables issues du run.

Cette story répond directement aux exigences fonctionnelles **FR-07** (tableau de couverture de la cohorte & anti-biais) et **FR-08** (respect du temps simulé & anti-métriques inventées) de l'Epic 011. Elle concourt aux critères de sortie chiffrés **C7** (100 % des personas demandés figurent au tableau de couverture, personas silencieux notés `present_no_action`, rubrique d'objections non levées obligatoire) et **C8** (0 événement situé au-delà de l'horizon du run, 0 métrique quantitative non calculable), tout en garantissant la neutralité locale (**NFR-01**), la non-régression absolue (**NFR-02**), la résilience ReACT (**NFR-04**) et l'étanchéité passive des prompts (**NFR-05**).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  1. Définir le modèle de données structuré `CohortMemberStatus` et le conteneur `CohortCoverageTable` dans `backend/app/models/cohort_coverage.py` avec sérialisation JSON et rendu en tableau Markdown.
  2. Spécifier les énumérations `ScenarioRole` (`PROSPECT`, `EXISTING_USER`, `FOUNDER`, `PRESCRIBER`, `OBSERVER`, `STAKEHOLDER`, `UNKNOWN`) et `DecisionStatus` (`ADOPTED`, `REJECTED`, `HESITANT`, `UNDECIDED`, `PRESENT_NO_ACTION`, `ABSENT_FROM_SIMULATION`).
  3. Mettre en œuvre le mécanisme d'agrégation déterministe rapprochant la liste des acteurs sélectionnés (`actors.json` / `ActorSelection`) des traces d'actions effectives (`EvidencePack` / `ObservedEvent`).
  4. Poser la règle d'intégrité stricte des personas silencieux (Critère C7) : si un persona n'a produit aucune action dans le run (`action_count == 0`), son statut est obligatoirement `PRESENT_NO_ACTION` (`is_silent = True`) ; interdiction formelle de fabriquer des faits ou de valider des assertions événementielles lui étant attribuées.
  5. Imposer la présence obligatoire de la section « Objections non levées, contradictions et limites » dans le rapport dès lors que des réticences, objections ou statuts `REJECTED`/`HESITANT` sont constatés dans la cohorte.
  6. Implémenter le contrôleur anti-biais de confirmation sur la synthèse exécutive (`summary`) interdisant les affirmations de triomphe unanime (ex: « toute la cohorte a adopté l'offre ») lorsque des membres de la cohorte ont refusé ou contesté l'offre.
  7. Établir le calcul déterministe du ratio temporel round $\leftrightarrow$ temps simulé à partir de `SimulationBrief.time_horizon` (ex: 40 rounds pour 72 heures = 1,8 heure par tour) et rétrograder toute affirmation située hors horizon en `SPECULATIVE_PROJECTION` (`UNSUPPORTED`) (Critère C8).
  8. Détecter et neutraliser les métriques quantitatives fantômes formulées sans base calculable ni dénominateur (ex: « churn à 90 jours » sur run de 72h, « coût mathématiquement insoutenable » sans calcul de coût unitaire).
- [x] **Documents consultés** :
  - [PRD Epic 011](prd.md) : §1.B (défaillances analytiques), §3 (FR-07, FR-08), §4 (NFR-01, NFR-02, NFR-04, NFR-05), §5 (C7, C8).
  - [Architecture Epic 011](architecture.md) : §2.7 (tableau de couverture de cohorte & anti-biais), §2.8 (respect du temps simulé & anti-métriques fantômes).
  - [Hub Epic 011](epic-011.md) : exigences fonctionnelles, critères C7/C8.
  - [Proposition amont Keova](rapport-chatgpt.md) : retours des 5 runs, profils silencieux (Simon), objections de Florence ignorées en synthèse, calendrier saturé à 48h sans métrique de réservation, churn à 90 jours sur run de 72h.
  - `backend/app/models/simulation_brief.py` : `time_horizon`, `hypotheses`, `target_audiences`, `rules`.
  - `backend/app/models/actor_selection.py` : `ActorItem`, `ActorSelection`, `ActorRole`.
  - `backend/app/models/evidence_pack.py` : `ObservedEvent`, `EvidencePack`.
  - `backend/app/models/report_claim.py` : `ReportClaim`, `ClaimKind`, `VerificationStatus`.
  - `backend/app/services/simulation_action_verifier.py` : `SimulationActionVerifier`.
  - `backend/app/services/report_agent.py` : `ReportAgent`, `_plan_outline`, `_generate_section_react`, `_generate_report_internal`.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (tests hermétiques et filet global), §2.8 (gouvernance des plans).
- [x] **Dépendances résolues** :
  - Story 011-1 close (`done`) : maintien en vie interactif OASIS et clôture différée.
  - Story 011-2 close (`done`) : registre d'événements observés (`OasisLogReaderService`, `EvidencePack`), `ToolShield` et Round 0 déterministe.
  - Story 011-3 close (`done`) : contrat structuré `ReportClaim`, typage épistémique et contrôle anti-affabulation.
  - Filet global : **1 696 tests collectés et réussis sur l'hôte** (+ 9 tests frontend Node), 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `CohortCoverageTable`** : Créer `backend/app/models/cohort_coverage.py` contenant `CohortMemberStatus` (dataclass immuable avec `persona_name`, `scenario_role`, `action_count`, `observed_event_ids`, `objections`, `decision_status`, `is_silent`, `verbatim_citations`) et `CohortCoverageTable` (agrégateur gérant la validation, les statistiques d'adoption et le rendu Markdown).
  2. **Typage des rôles de scénario (`ScenarioRole`)** : Définir une énumération agnostique et non couplée à Keova (`PROSPECT`, `EXISTING_USER`, `FOUNDER`, `PRESCRIBER`, `OBSERVER`, `STAKEHOLDER`, `UNKNOWN`) permettant de qualifier la fonction de l'acteur dans l'expérimentation.
  3. **Règle absolue des personas silencieux (Critère C7)** : Si un persona issu de `actors.json` ne possède aucun événement dans l'`EvidencePack`, son statut est automatiquement verrouillé à `DecisionStatus.PRESENT_NO_ACTION` (`is_silent = True`). Le vérificateur serveur `SimulationActionVerifier` rejette ou déclasse toute claim affirmant une action sociale observée de cet agent.
  4. **Section obligatoire d'objections et limites (Critère C7)** : Le `ReportAgent` vérifie lors de la planification d'outline ou de l'assemblage que si la cohorte comprend au moins une objection ou un membre `REJECTED`/`HESITANT`, une section « Objections non levées, contradictions et limites » est formellement insérée et complétée.
  5. **Garde-fou anti-biais sur la synthèse** : Analyse textuelle et logique de la synthèse (`summary`) par rapport aux statuts de la cohorte. Si `REJECTED > 0` et que le texte affirme « unanimité », « tous les agents ont adopté », « conversion totale » ou formulation équivalente, le système émet un avertissement d'incohérence et rétrograde l'affirmation en `CONTRADICTED`.
  6. **Gestionnaire de temps simulé (`TimeHorizonGuard`)** :
     - Parseur de l'horizon temporel (`time_horizon` : "72h", "72 hours", "3 days", "3 jours", "48h") vers un nombre d'heures réelles `horizon_hours: float`.
     - Calcul du pas horaire : `step_hours = horizon_hours / total_rounds`.
     - Contrôle des mentions temporelles dans les claims et sections : interdiction de situer un événement au-delà de `horizon_hours`.
     - Déclassement de toute extrapolation post-horizon en `ClaimKind.SPECULATIVE_PROJECTION` avec statut `UNSUPPORTED`.
  7. **Règle anti-métriques fantômes (Critère C8)** :
     - Détection par motifs regex et analyse lexicale des affirmations chiffrées péremptoires (pourcentages d'adoption globaux, durées d'attrition/churn, saturation calendaire, coûts d'onboarding) non adossées à un calcul documenté dans les traces.
     - Étiquetage obligatoire en `ClaimKind.ANALYST_INFERENCE` ou `SPECULATIVE_PROJECTION` avec limitation explicite.
  8. **Persistance d'audit** : Sauvegarde déterministe de `simulations/<sim_id>/cohort_coverage.json` intégré dans le cycle du `ReportAgent`.
- [x] **Stratégie de tests identifiée** :
  - Suite de tests hermétiques dédiée : `backend/tests/test_cohort_coverage_time.py`.
  - Tests unitaires des modèles `CohortMemberStatus`, `CohortCoverageTable`, `ScenarioRole`, `DecisionStatus`.
  - Tests d'agrégation cohorte depuis `actors.json` et `EvidencePack` avec détection exacte des silencieux.
  - Tests du rejet d'actions inventées pour personas silencieux (Critère C7).
  - Tests de détection et insertion obligatoire de la section d'objections et limites.
  - Tests du garde-fou anti-biais de confirmation sur la synthèse exécutive.
  - Tests du parseur d'horizon temporel et de rejet des événements hors horizon (Critère C8).
  - Tests de neutralisation des métriques fantômes (Critère C8).
  - Maintien du filet global à $\ge 1 696$ tests passants sur l'hôte.

---

## Définition de fini

- [ ] Critères d'acceptation **AC1 à AC8** satisfaits et vérifiés par des tests automatisés passants.
- [ ] Modèle `backend/app/models/cohort_coverage.py` créé avec `CohortMemberStatus`, `CohortCoverageTable`, `ScenarioRole` et `DecisionStatus`.
- [ ] Moteur d'agrégation de cohorte intégrant `actors.json` et `EvidencePack` sans omission ni doublon.
- [ ] Règle d'intégrité des personas silencieux C7 implémentée et vérifiée (marquage `present_no_action`, 0 fausse action).
- [ ] Insertion et complétion obligatoires de la section « Objections non levées, contradictions et limites » validées.
- [ ] Détection et blocage du biais de confirmation dans la synthèse exécutive opérationnels.
- [ ] Parseur et validateur d'horizon temporel C8 intégrés dans la chaîne de vérification (0 extrapolation présentée comme observation).
- [ ] Détecteur de métriques quantitatives fantômes C8 actif, requalifiant systématiquement les chiffres non calculables.
- [ ] Persistance atomique de `simulations/<sim_id>/cohort_coverage.json` et rendu Markdown intégrés dans `ReportAgent`.
- [ ] Suite de tests hermétiques dédiée créée dans `backend/tests/test_cohort_coverage_time.py` ($\ge 15$ tests au vert).
- [ ] Filet global de tests maintenu ($\ge 1 696$ tests réussis sur l'hôte) et parité Docker vérifiée.
- [ ] `uv run python backend/scripts/validate_plans.py` et `uv run ruff check backend/` validés sans anomalie.
- [ ] Revue contradictoire BMAD à 4 couches réalisée avec findings consignés et résolus.
- [ ] Synchronisation des documents de suivi (`epic-011.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`).

---

## Tâches

- [ ] **T1 — Modèle structuré `CohortCoverageTable`, `CohortMemberStatus` et énumérations** :
  - Créer `backend/app/models/cohort_coverage.py`.
  - Définir `ScenarioRole` (`PROSPECT`, `EXISTING_USER`, `FOUNDER`, `PRESCRIBER`, `OBSERVER`, `STAKEHOLDER`, `UNKNOWN`).
  - Définir `DecisionStatus` (`ADOPTED`, `REJECTED`, `HESITANT`, `UNDECIDED`, `PRESENT_NO_ACTION`, `ABSENT_FROM_SIMULATION`).
  - Définir la dataclass `CohortMemberStatus` avec validation de cohérence interne (`is_silent` vs `action_count`).
  - Définir `CohortCoverageTable` avec calcul des statistiques globales (taux d'engagement, répartition des statuts) et méthodes `to_dict`, `from_dict`, `to_markdown_table`.
- [ ] **T2 — Agrégation déterministe de cohorte depuis `actors.json` et `EvidencePack`** :
  - Implémenter la méthode d'agrégation `CohortCoverageTable.build_from_simulation(actor_selection, evidence_pack, brief)`.
  - Mapper chaque `ActorItem` vers un `CohortMemberStatus` avec son `scenario_role`.
  - Associer les événements d'action réels (`ObservedEvent`) à chaque persona par correspondance nominative insensible à la casse.
  - Détecter les objections exprimées dans les arguments de message ou les résultats.
  - Assigner `DecisionStatus.PRESENT_NO_ACTION` (`is_silent = True`) si `action_count == 0`.
- [ ] **T3 — Règle anti-affabulation sur personas silencieux (Critère C7)** :
  - Intégrer dans `SimulationActionVerifier.verify_report_claim` un contrôle strict sur `cohort_table` : si `claim.persona_name` correspond à un membre `is_silent`, toute affirmation `OBSERVED_SOCIAL_ACTION` est automatiquement rétrogradée en `VerificationStatus.CONTRADICTED` ou `UNSUPPORTED`.
  - Ajouter un message d'avertissement explicite : « Le persona X est silencieux (present_no_action) dans ce run. Aucune action ne peut lui être imputée. »
- [ ] **T4 — Rubrique obligatoire d'objections non levées, contradictions et limites** :
  - Dans `ReportAgent`, inspecter `cohort_table` avant ou pendant la planification d'outline.
  - Si des objections ou statuts `REJECTED` / `HESITANT` existent dans la cohorte, forcer la présence de la section « Objections non levées, contradictions et limites » (ou équivalent localisé) dans `outline.sections`.
  - Si omise par le LLM, injecter automatiquement la section avec le récapitulatif des objections réelles extraites de `cohort_table`.
- [ ] **T5 — Contrôle anti-biais de confirmation de la synthèse exécutive** :
  - Implémenter dans `SimulationActionVerifier` la méthode `check_executive_summary_bias(summary_text, cohort_table)`.
  - Détecter les marqueurs textuels de consensus unanime (« tous les clients », « conversion totale », « unanimité », « aucun refus ») en présence de `REJECTED > 0` ou d'objections majeures non résolues.
  - Émettre un signalement d'incohérence et exiger un correctif ou annoter la synthèse d'une réserve de neutralité.
- [ ] **T6 — Respect strict du temps simulé et ratio rounds/heures (Critère C8)** :
  - Créer l'utilitaire `TimeHorizonGuard` pour parser `SimulationBrief.time_horizon` (ex: "72h" $\rightarrow$ 72.0h, "3 jours" $\rightarrow$ 72.0h).
  - Établir la conversion `round_to_simulated_hour(round_num, total_rounds, horizon_hours)`.
  - Vérifier dans `SimulationActionVerifier` que toute assertion événementielle mentionnant une heure ou un jour reste $\le horizon_hours$.
  - Déclasser toute assertion située au-delà de l'horizon en `ClaimKind.SPECULATIVE_PROJECTION` avec statut `UNSUPPORTED`.
- [ ] **T7 — Neutralisation des métriques quantitatives fantômes (Critère C8)** :
  - Implémenter le filtre `detect_unsupported_quantitative_metrics(claim_text, evidence_pack)` repérant les métriques péremptoires non calculables (pourcentages de conversion sans base d'effectif, ratios financiers sans formule, durées d'attrition hors horizon).
  - Rétrograder ces affirmations vers `ClaimKind.ANALYST_INFERENCE` ou `SPECULATIVE_PROJECTION` avec étiquette de limitation explicite.
- [ ] **T8 — Intégration globale, persistance `cohort_coverage.json` et suite hermétique** :
  - Intégrer la génération et la persistance de `simulations/<sim_id>/cohort_coverage.json` dans `ReportAgent._generate_report_internal`.
  - Insérer le tableau Markdown formaté dans le corps du rapport.
  - Créer la suite de tests hermétiques `backend/tests/test_cohort_coverage_time.py` ($\ge 15$ tests au vert).
  - Valider l'intégralité du filet de tests ($\ge 1 696$ tests) et la parité Docker.

---

## Notes de développement

### 1. Analyse des défaillances observées sur les simulations Keova (Runs R1 à R5)

L'audit des 5 rapports successifs Keova a mis en lumière des biais récurrents :
1. **L'illusion d'unanimité (Biais de confirmation)** :
   - Dans le run R5, Florence exprime un refus catégorique face à l'absence de flexibilité tarifaire, et Émilie reporte sa décision en attendant des garanties sur l'onboarding.
   - Pourtant, la synthèse exécutive affirmait : « L'offre Keova Essentiel emporte une adhésion massive et convertit l'ensemble des cibles grâce à l'accompagnement humain ».
   - **Correction Story 011-4 :** La synthèse ne peut plus masquer les refus consignés dans le tableau de cohorte. La présence d'au moins un statut `REJECTED` déclenche le verrouillage anti-biais.
2. **Le persona fantôme actif (Affabulation sur silencieux)** :
   - Simon (agent prescripteur / expert technique) n'a publié aucun message pendant les 40 rounds du run (`action_count = 0`).
   - Le rapporteur LLM a néanmoins inventé : « Simon a exprimé des réserves sur la scalabilité technique au Round 14 ».
   - **Correction Story 011-4 :** Tout agent avec 0 action réelle est consigné comme `present_no_action`. Toute claim lui attribuant un propos ou une action est automatiquement invalidée (`CONTRADICTED` ou `UNSUPPORTED`).
3. **L'extrapolation temporelle débridée (Viol de l'horizon temporel)** :
   - Le run Keova était configuré pour un horizon strict de **72 heures** (40 rounds).
   - Le rapport extrapolait : « Churn massif observé à 90 jours en raison de la complexité des tableaux de bord ».
   - **Correction Story 011-4 :** Un run de 72h ne peut en aucun cas rapporter un churn à 90 jours comme fait observé. L'assertion est déclassée en projection spéculative.
4. **Les métriques financières péremptoires (Métriques fantômes)** :
   - Le rapport qualifiait le coût d'acquisition de « mathématiquement insoutenable » et citait « un taux de saturation de 83 % de l'agenda de Simon à la 48ᵉ heure ».
   - Or, aucune trace de réservation ou de capacité d'agenda n'existait dans les traces du run.
   - **Correction Story 011-4 :** Rejet des affirmations quantitatives sans base de calcul issue du run.

### 2. Schéma de données de `cohort_coverage.json`

```json
{
  "simulation_id": "sim_20261016_keova",
  "horizon_hours": 72.0,
  "total_rounds": 40,
  "total_members": 6,
  "active_members": 5,
  "silent_members": 1,
  "status_summary": {
    "adopted": 2,
    "rejected": 1,
    "hesitant": 2,
    "present_no_action": 1
  },
  "members": [
    {
      "persona_name": "Florence",
      "scenario_role": "prospect",
      "action_count": 4,
      "observed_event_ids": ["evt_twitter_1_1", "evt_twitter_3_2"],
      "objections": ["Tarif fixe annuel trop engageant sans option mensuelle"],
      "decision_status": "rejected",
      "is_silent": false,
      "verbatim_citations": ["Je ne peux pas m'engager sur un an d'un coup"]
    },
    {
      "persona_name": "Simon",
      "scenario_role": "prescriber",
      "action_count": 0,
      "observed_event_ids": [],
      "objections": [],
      "decision_status": "present_no_action",
      "is_silent": true,
      "verbatim_citations": []
    }
  ]
}
```

### 3. Matrice de rendu Markdown du tableau de cohorte

Le tableau généré automatiquement et injecté dans le rapport se présente sous la forme canonique suivante :

| Persona | Rôle Scénario | Actions Observées | Objections Majeures | Décision Simulée | Statut Couverture |
|---|---|---|---|---|---|
| Florence | Prospect | 4 actions (2 tweets, 2 replies) | Absence d'abonnement mensuel | Rejet de l'offre | `observed_active` |
| Émilie | Prospect | 6 actions (3 tweets, 3 replies) | Clarté de la tarification litiges | Hésitation / Report | `observed_active` |
| Simon | Prescripteur | 0 action | Aucune | Aucune observation | `present_no_action` |

---

## Revue

### Review Findings (Revue contradictoire BMAD à 4 couches)

*(À consigner lors de la revue BMAD de la story)*

#### Rejected findings
*(À consigner lors de la revue BMAD de la story)*

---

## Notes de complétion

*(À consigner lors de la clôture de la story)*
