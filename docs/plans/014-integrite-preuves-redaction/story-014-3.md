---
id: "014-3"
epic: "014"
titre: "La règle de silence monte jusqu'à la prose et jusqu'à la barrière"
statut: review
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 014-3 — La règle de silence monte jusqu'à la prose et jusqu'à la barrière

**Lot C (règle de silence), priorité P0.** En tant que relecteur d'un rapport produit
par MiroFish — analyste, commanditaire ou tiers recevant l'archive d'audit —, je veux
que la règle de silence (un persona sans action ne peut se voir attribuer d'action)
agisse dans la prose du rapport et à la barrière de publication, et pas seulement dans
le registre d'affirmations, afin qu'un rapport ne puisse plus attribuer une parole, une
décision ou une section à un persona qui n'a jamais agi.

Cette story répond aux exigences **FR-05** (un persona silencieux ou non admis ne peut
recevoir ni parole, ni décision, ni section, dans la prose comme dans le registre),
**FR-06** (la contradiction « persona silence ↔ action affirmée » est critique pour la
barrière de publication) et **FR-09** (un tiers peut établir l'origine de chaque passage)
du [PRD de l'epic](prd.md), et sert les critères de sortie **C3** (aucun persona
silencieux ne reçoit parole, décision ou section), **C4** (la contradiction déclenche un
échec de la barrière) et **C7** (établissement de l'origine) de l'[epic](epic-014.md).
Elle dépend des stories 014-1 (régime de provenance des entretiens) et 014-2 (section
« Sources & Provenance » honnête), dont elle consomme le registre et la table de
couverture de cohorte, et alimente la story 014-4 qui pourra s'appuyer sur une règle de
silence effective pour durcir la construction des briefs.

**Frontière, en une phrase.** Cette story **fait remonter** la règle de silence jusqu'à
la prose et jusqu'à la barrière ; elle ne corrige ni le régime des entretiens (014-1),
ni la section Sources & Provenance (014-2), ni la construction des briefs et des fiches
persona (014-4).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :

  **Le problème, mesuré.** La règle de silence n'existe qu'en un seul endroit :
  `SimulationActionVerifier.verify_report_claim` (`simulation_action_verifier.py:939-961`)
  rétrograde en `ClaimKind.SPECULATIVE_PROJECTION` toute affirmation d'action imputée à
  un persona dont `CohortMemberStatus.is_silent` est vrai, mais **ne réécrit que le
  `ReportClaim`** — le markdown du rapport reste inchangé. Sur la campagne de l'Epic 013,
  la variante B affiche 7 affirmations `CONTRADICTED` sur le même persona silencieux avec
  `failed_checks: 0`, et la barrière de publication ne les compte pas comme critiques :
  `report_quality_gate.py:470` ne retient que les `CONTRADICTED` de kind
  `OBSERVED_SOCIAL_ACTION`, et `SPECULATIVE_PROJECTION` n'en fait pas partie. De plus, les
  fiches persona et le brief entrent dans le prompt de rédaction sans filtrage
  (`report_agent.py:688`, `:1886`) ; un acteur au statut `review` n'est jamais filtré
  (`cohort_coverage.py:83-86`, `:622-625` — seuls les `ineligible` le sont). Le persona
  « Émilie » (non admis, 0 action, `present_no_action`) se voit pourtant attribuer un
  arc, des citations et une section dans les deux variantes.

  **Ce que la story garantit, par sous-ensemble.**

  - **Contexte de rédaction.** Les fiches persona des acteurs non admis (`review`,
    `ineligible`) ne sont plus injectées dans le contexte de rédaction comme des
    personas actifs, ou le sont balisées comme non admises. La table de cohorte déjà
    construite avant la rédaction (`report_agent.py:1976-1983`) est transmise à la
    rédaction, pas recalculée.
  - **Prose.** Un passage attribuant une parole, une décision ou une section à un
    persona silencieux (`is_silent == True`) est retiré ou inhibé de la prose publiée,
    et non seulement du registre.
  - **Barrière.** La contradiction « persona silencieux ↔ action affirmée » est
    **critique** pour la barrière de publication : elle déclenche `FAILED_VALIDATION`
    et `is_publishable = False`, et non un avertissement.
  - **Traçabilité.** Chaque inhibition ou retrait est justifié dans `limitations` du
    claim concerné, et visible dans l'archive d'audit.

  **Les invariants — ce que l'implémentation ne peut pas faire.**

  - **Jamais de parole à un silencieux.** Un persona avec `is_silent == True` ne peut
    se voir attribuer ni parole, ni décision, ni section, dans la prose comme dans le
    registre.
  - **Jamais d'avertissement pour une contradiction de silence.** La contradiction
    « persona silencieux ↔ action affirmée » déclenche un **échec**, pas un
    avertissement.
  - **Jamais de recalcul de la cohorte.** La table de cohorte est construite une fois,
    avant la rédaction, et transmise.
  - **Jamais de nouvelle valeur dans `InformationOrigin` ni dans `ClaimKind`.** La règle
    lit des données existantes ; elle n'étend aucun contrat.
  - **Jamais de dépendance ajoutée.** `json`, déjà utilisé, suffit.
  - **Jamais de régression du Fail-Closed.** Le statut `FAILED_VALIDATION` et
    `is_publishable = False` restent la conséquence d'une contradiction de silence.

- [x] **Documents consultés** :

  - [PRD de l'epic](prd.md) : §2.3 (la règle de silence n'agit que sur le registre, jamais
    sur la prose, et sa contradiction n'est pas critique pour la barrière), §4 (FR-05,
    FR-06, FR-09), §5 (NFR-1, NFR-2, NFR-5), §6 (C3, C4, C7).
  - [Architecture de l'epic](architecture.md) : §3 (le modèle de preuve), §4 (contraintes
    de non-régression, point d'application économique de la table de cohorte).
  - [Hub de l'epic](epic-014.md) : §2 (FR-05, FR-06), §4 (story 014-3), §5 (C3, C4, C7),
    §6 (preuve de l'état de départ : 7 `CONTRADICTED` sur le même persona silencieux).
  - `AGENTS.md` : §2.1 (les dépendances pointent vers l'intérieur), §2.2 (tout code
    produit est testé ; hermétique), §10 (la fiction de scénario d'un persona non admis
    fuit dans la prose).
  - `backend/app/services/simulation_action_verifier.py` : `verify_report_claim` (`:909`),
    règle des personas silencieux C7 (`:939-961`), `check_executive_summary_bias` (`:1343`),
    `analyze_intentions` (`:820`).
  - `backend/app/models/cohort_coverage.py` : `CohortMemberStatus` (`:333`), invariant de
    silence C7 (`:349-362`), `CohortCoverageTable` (`:391`), `build_from_simulation`
    (`:574`), `get_member` (`:471`), filtre des acteurs non admis (`:83-86`, `:622-625`),
    `ScenarioRole` (`:210`), `DecisionStatus` (`:278`).
  - `backend/app/services/report_agent.py` : contexte de rédaction (`:688`, `:1886`),
    construction de la table de cohorte temporaire (`:1976-1983`), `extract_claims_from_content`
    (`:3278`), barrière de publication (`:2727`), `generate_and_save_cohort_coverage`
    (`:2635`).
  - `backend/app/models/report_quality.py` : `PublicationStatus` (`:23`), `QualityGateResult`
    (`:89`), `_recompute_status` (`:121`), `is_publishable`.
  - `backend/app/services/report_quality_gate.py` : contrôles préalables (`:464-493`),
    `critical_contradictions` (`:470-474`), QA-08 (`:553-569`), QA-09 (`:587-604`).
  - `backend/tests/test_cohort_coverage_time.py` : tests de la couverture de cohorte.
  - `backend/tests/test_report_quality_gate_audit.py` : tests de la barrière de publication.
  - `backend/tests/test_report_claims_reconciliation.py` : tests de réconciliation.
  - `docs/deferred-work.md` : § « La fiction de scénario d'un persona non admis fuit dans
    les affirmations "observées" » (`:536-544`).

- [x] **Dépendances résolues** :

  - **Stories amont** : 014-1 est `done` (régime de provenance des entretiens, champ
    `provenance_regime` dans `ReportClaim`, artefact `report_interviews.json`) ; 014-2 est
    `done` (section « Sources & Provenance » honnête, `ProjectManager` résilient, index
    d'attribution). Les Epics 011 et 012 sont clos et fournissent `ReportClaim`,
    `ReportClaimRegistry`, `SimulationActionVerifier`, `CohortCoverageTable`,
    `QualityGateResult`, la barrière Fail-Closed et la prévalence épistémique. Aucun
    contrat de ces epics n'est rouvert.
  - **Stories avalentes** : 014-4 pourra s'appuyer sur une règle de silence effective pour
    durcir la construction des briefs.
  - **Filet de tests mesuré à la rédaction** : **2 077 tests backend** au vert sur l'hôte
    et **43 tests Node** frontend, mesuré le 22 octobre 2026 (`uv run pytest tests/ -q`,
    `pnpm --dir frontend test`).
  - **Dépendances techniques** : aucune nouvelle dépendance. `json`, déjà utilisé, suffit.

- [x] **Décisions d'ingénierie arrêtées avant code** :

  1. **La règle de silence agit à trois endroits.** Contexte de rédaction (filtrage ou
     balisage des personas `review`/`ineligible`), prose (inhibition des passages
     attribués à un persona silencieux), barrière (contradiction de silence = critique).
     *Raison* : la règle n'agit aujourd'hui que sur le registre ; la prose et la barrière
     doivent la respecter pour que le rapport ne se contredise pas.
  2. **La table de cohorte est transmise, pas recalculée.** La table déjà construite
     avant la rédaction (`report_agent.py:1976-1983`) est passée à la rédaction. *Raison* :
     point d'application économique, évite un recalcul et garantit la cohérence.
  3. **Les acteurs `review` sont filtrés du contexte de rédaction.** Extension du filtre
     actuellement limité aux `ineligible` (`cohort_coverage.py:83-86`, `:622-625`) pour
     exclure aussi les acteurs au statut `review`. *Raison* : un acteur non admis ne doit
     pas figurer comme persona actif dans le prompt.
  4. **La barrière compte les contradictions de silence comme critiques.** Ajout d'un
     contrôle dédié dans `QualityGate` qui compte les claims `CONTRADICTED` dont l'agent
     est silencieux (via la table de cohorte), sans modifier le `ClaimKind` existant ni
     le reclassement en `SPECULATIVE_PROJECTION`. *Raison* : ne pas rouvrir le contrat
     gelé (`ClaimKind`), tout en rendant la contradiction critique.
  5. **La prose inhibe les passages attribués à un silencieux.** Dans
     `extract_claims_from_content`, un claim dont l'agent résolu est silencieux est
     déclassé en `REPORTED_INTENTION` / `UNSUPPORTED` et son texte est retiré de la prose
     publiée, ou annoté comme non fondé. *Raison* : la règle agit sur la prose, pas
     seulement sur le registre.
  6. **Aucune nouvelle valeur dans `InformationOrigin` ni dans `ClaimKind`.** La règle
     lit des données existantes. *Raison* : ne pas rouvrir un contrat gelé.
  7. **Aucune nouvelle dépendance.** `json`, déjà utilisé, suffit. *Raison* : NFR-1.

- [x] **Stratégie de tests identifiée** :

  - **Hermétique d'abord.** Tous les tests nouveaux sont hermétiques : aucun appel
    réseau, aucun modèle, aucun `.env`. Les cohortes et registres sont des objets en
    mémoire ou des dossiers temporaires (`tmp_path`).
  - **Nouveau fichier** : `backend/tests/test_silence_rule_reaches_prose.py`, avec les
    cas nommés pour chaque AC.
  - **Ce qui est vérifié à l'œil** sur la pile Docker de référence : un rapport régénéré
    sur R7 dont aucun persona silencieux ne reçoit de parole, de décision ou de section.
  - **Tests existants à ne pas casser** : `test_report_quality_gate_audit.py`,
    `test_report_claims_reconciliation.py`, `test_cohort_coverage_time.py`,
    `test_epistemic_sources_and_brief.py`.

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Un persona silencieux ne reçoit ni parole, ni décision, ni section** : dans la prose d'un rapport généré avec un persona silencieux (`is_silent == True`), son nom n'apparaît dans aucune affirmation d'action observée, et aucune section ne lui est attribuée. | `tests/test_silence_rule_reaches_prose.py::test_silent_persona_gets_no_speech_or_section` |
| **AC2** | **Un persona non admis est filtré du contexte de rédaction** : les fiches persona des acteurs au statut `review` ou `ineligible` ne sont pas injectées dans le prompt de rédaction comme des personas actifs (ou le sont balisées comme non admises). | `::test_non_admitted_persona_filtered_from_context` |
| **AC3** | **La contradiction de silence déclenche un échec de la barrière** : un rapport dont un claim `CONTRADICTED` est imputé à un persona silencieux produit `QualityGateResult.final_status = FAILED` et `is_publishable = False`, et non `NEEDS_REVIEW`. | `::test_silence_contradiction_fails_barrier` |
| **AC4** | **La prose inhibe les passages attribués à un silencieux** : un passage attribuant une action à un persona silencieux est retiré ou inhibé de la prose publiée, avec justification dans `limitations`. | `::test_silence_rule_inhibits_prose_passage` |
| **AC5** | **La table de cohorte est transmise, pas recalculée** : la rédaction reçoit la table de cohorte déjà construite, et ne la recalcule pas. | `::test_cohort_table_passed_to_report` |
| **AC6** | **Non-régression** : le filet ne rétrécit pas — **2 077 tests backend** et **43 tests Node** au vert, mesurés le 22 octobre 2026 —, `ruff check` ne signale rien, `validate_plans.py` valide la structure. | `uv run pytest tests/ -q` (total ≥ 2 077), `pnpm --dir frontend test` (43), `uv run ruff check .`, `uv run python scripts/validate_plans.py` |

**Traçabilité exigence → AC → tâche.**

| Exigence de l'epic | AC | Tâches |
|---|---|---|
| FR-05 — pas de parole/décision/section à un silencieux | AC1, AC2, AC4 | T1, T2, T3 |
| FR-06 — contradiction de silence critique pour la barrière | AC3 | T4 |
| FR-09 — établissement de l'origine par un tiers | AC1, AC4 | T3, T5 |
| NFR-1 — zéro régression | AC6 | T8 |
| NFR-5 — honnêteté | AC1, AC3, AC4 | T1, T3, T4 |
| C3 — aucun persona silencieux ne reçoit parole/décision/section | AC1, AC2, AC4 | T1, T2, T3 |
| C4 — la contradiction déclenche un échec de la barrière | AC3 | T4 |
| C7 — établissement de l'origine | AC1, AC4 | T3, T5 |

---

## Définition de fini

- [x] `backend/app/services/simulation_action_verifier.py` : la règle de silence agit sur la prose (inhibition des passages attribués à un silencieux), pas seulement sur le registre.
- [x] `backend/app/models/cohort_coverage.py` : les acteurs `review` et `ineligible` sont filtrés du contexte de rédaction (ou balisés comme non admis).
- [x] `backend/app/services/report_agent.py` : la table de cohorte déjà construite est transmise à la rédaction.
- [x] `backend/app/services/report_quality_gate.py` : la contradiction « persona silencieux ↔ action affirmée » est critique pour la barrière (`FAILED_VALIDATION`, `is_publishable = False`).
- [x] `backend/tests/test_silence_rule_reaches_prose.py` : tous les cas nommés dans les AC, verts.
- [x] Non-régression : `uv run pytest tests/ -q`, `pnpm --dir frontend test`, `uv run ruff check .`, `uv run python scripts/validate_plans.py`.
- [x] Vérification visuelle sur la pile Docker de référence : un rapport régénéré sur R7 dont aucun persona silencieux ne reçoit de parole, de décision ou de section.

---

## Tâches

- [x] 1. **Filtrer les acteurs non admis du contexte de rédaction** : étendre le filtre actuellement limité aux `ineligible` pour exclure (ou baliser) les acteurs au statut `review`. *(AC2)*
- [x] 2. **Transmettre la table de cohorte à la rédaction** : passer la table déjà construite (`report_agent.py:1976-1983`) à la rédaction, sans recalcul. *(AC5)*
- [x] 3. **Inhiber les passages attribués à un silencieux dans la prose** : dans `extract_claims_from_content`, déclasser et retirer (ou annoter) les claims dont l'agent résolu est silencieux. *(AC1, AC4)*
- [x] 4. **Rendre la contradiction de silence critique pour la barrière** : ajouter un contrôle dédié dans `QualityGate` qui compte les claims `CONTRADICTED` imputés à un persona silencieux, déclenchant `FAILED_VALIDATION` et `is_publishable = False`. *(AC3)*
- [x] 5. **Justifier chaque inhibition** : ajouter la justification dans `limitations` du claim concerné, visible dans l'archive d'audit. *(AC1, AC4)*
- [x] 6. **Les tests** : `backend/tests/test_silence_rule_reaches_prose.py`. *(AC1 à AC5)*
- [x] 7. **La clôture technique** : non-régression, lint, validation de plan, vérification visuelle sur la pile Docker de référence. *(AC6)*

## Notes de développement

*(à remplir pendant l'implémentation : ce qui a été décidé en codant, et pourquoi ; les
points non résolus)*

---

## Revue

*(à remplir par la revue contradictoire : findings retenus, gravité, correctif appliqué,
points différés, rejets motivés)*

---

## Notes de complétion

*(à remplir à la clôture : statut final, tests exécutés, lint, validation de plan, écarts
avec le plan et pourquoi, ce que la story ne fait pas, effets de bord observés)*