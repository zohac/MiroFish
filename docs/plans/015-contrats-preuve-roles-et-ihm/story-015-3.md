---
id: "015-3"
epic: "015"
titre: "Barrière ReportQualityGate sans angle mort conceptuel, section limitations contractuelle et provenance 100 % calculée"
statut: done
created: 2026-10-29
updated: 2026-10-29
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 015-3 — Barrière `ReportQualityGate` sans angle mort « conceptuel », section `limitations` contractuelle et provenance 100 % calculée

**Epic parent** : [Epic 015 — Contrats de preuve, gouvernance des rôles et ergonomie IHM Step 3/4](epic-015.md) · **Lot A — Coutures des contrats de preuve et barrière de publication (P0)**
**Priorité** : P0 (Bloquant — élimine l'angle mort « rapport conceptuel » quand 100 % des actions affirmées sont déclassées, remplace le contrôle littéral rigide de la section d'objections par un rôle structurel `section_role="limitations"` et supprime toute phrase de garantie statique non calculée dans `## Sources & Provenance`)
**En tant qu'** auditeur ou utilisateur générant ou rejouant un rapport de simulation MiroFish,
**je veux** que la barrière `ReportQualityGate` calcule le taux de vérification des actions sur **toutes** les affirmations initialement émises comme actions sociales (`asserted_as_action=True` ou `OBSERVED_SOCIAL_ACTION`), valide la section d'objections/limites via un rôle structurel contractuel `section_role="limitations"` dans `ReportOutline` / `ReportSection` plutôt que sur 4 titres littéraux figés, et génère une section `## Sources & Provenance` dont chaque assertion de conformité (notamment la « Règle anti-affabulation ») est 100 % calculée depuis `ReportClaimRegistry`,
**afin qu'** aucun rapport dont les actions affirmées ont été intégralement déclassées faute de preuve ne puisse esquiver l'échec QA-08 sous l'étiquette complaisante « rapport conceptuel », qu'une section substantielle consacrée aux verrous, refus et réserves ne soit plus rejetée à cause de son intitulé éditorial, et que la section `## Sources & Provenance` ne puisse jamais se contredire entre ses sous-sections 3 et 7.

**Exigences couvertes** :
- **Fonctionnelles** : `FR-04` (Barrière `ReportQualityGate` sans angle mort « conceptuel », validation structurelle `section_role="limitations"` et section « Sources & Provenance » 100 % calculée — P0).
- **Non fonctionnelles** : `NFR-1` (Zéro régression et compatibilité ascendante des artefacts `v1` : un `outline.json` ou `meta.json` historique sans clé `section_role` reste relu sans erreur et validé par heuristique structurelle de repli), `NFR-2` (Généricité absolue : aucun nom de persona, d'offre ou de domaine spécifique à R8/Keova dans le code applicatif ni dans les prompts globaux), `NFR-3` (Simplicité KISS & DRY : réutilisation directe de `ReportClaim.asserted_as_action` et `ReportClaimRegistry.asserted_action_claims` introduits en `015-1`, sans couche redondante), `NFR-5` (Honnêteté épistémique : zéro phrase de certification pré-rédigée contredisant les compteurs réels du registre).
- **Critères de sortie de l'Epic servis** : **C3** (Absence d'angle mort « conceptuel » sur `ReportQualityGate`, validation par `section_role="limitations"` et section « Sources & Provenance » 100 % calculée), ainsi que la contribution directe aux critères **C7** (Qualification sur les artefacts R8 `sim_7a1b02b8c092` / `report_934d3254004b`) et **C8** (Filet de non-régression global).

**Dépendances** :
- **Stories amont requises (au sein de l'Epic 015)** :
  - `015-1` (`done`, obligatoire) : fournit le booléen persistant `ReportClaim.asserted_as_action` (`backend/app/models/report_claim.py:131, 189-203`) et les compteurs `ReportClaimRegistry.asserted_action_claims` / `verified_action_claims` (`backend/app/models/report_claim.py:249-260, 278-279`) qui tracent toute affirmation initialement émise comme `OBSERVED_SOCIAL_ACTION` avant son éventuel déclassement par `SimulationActionVerifier.verify_report_claim`.
  - `015-2` (`done`, obligatoire) : fournit le schéma `report_interviews.json` v2 et l'authentification des citations d'entretien par répondant.
- **Épics amont requis (clos)** :
  - Epic 011 (`done` — `ReportClaim`, `ReportClaimRegistry`, `SimulationActionVerifier.verify_report_claim`).
  - Epic 012 (`done` — `ReportQualityGate`, `QualityCheckItem`, `QualityGateResult`, `PublicationStatus`).
  - Epic 014 (`done` — `ProvenanceRegime`, sous-section 7 de `build_sources_provenance_section`, `test_sources_provenance_honesty.py`).
- **Stories aval débloquées** :
  - `015-6` (Contrôle biographique aval de la prose, `GIT_COMMIT` Docker et banc de qualification R8 `verifier_qualification_epic_015.py`).

**Frontière de la story (Non-scope strict)** :
- **Inclus** :
  1. Fermeture de l'angle mort « rapport conceptuel » et redéfinition du dénominateur de `action_ratio` dans `ReportQualityGate.evaluate_report` (`backend/app/services/report_quality_gate.py:494-698`) en s'appuyant sur `asserted_actions = [c for c in claims_registry.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION or getattr(c, "asserted_as_action", False)]`, complétée par un filet d'inspection Markdown (`_markdown_alleges_simulated_actions`) empêchant tout rapport narratif d'actions d'être qualifié de « conceptuel » si `len(asserted_actions) == 0`.
  2. Durcissement par expressions régulières à frontières de mots (`\b`) de la détection d'adoption (`_ADOPTION_ACTION_RE`) et de la branche sans registre dans `ReportQualityGate.evaluate_report` (`backend/app/services/report_quality_gate.py:513-554, 699-730`), éliminant les faux positifs par sous-chaîne brute (`"sign"` dans *signal* / *souligne*).
  3. Ajout du champ contractuel `section_role: Optional[str] = None` sur `ReportSection` (`backend/app/services/report_agent.py:497-516`), sérialisation/désérialisation rétrocompatible dans `ReportOutline` et `ReportManager.get_report` (`backend/app/services/report_agent.py:518-538, 5048-5078`), propagation dans `PLAN_SYSTEM_PROMPT`, `_get_default_outline` et `plan_outline` (`backend/app/services/report_agent.py:675-713, 1098-1130, 2115-2172`), et validation par rôle structurel (`section_role == "limitations"`) avec repli rétrocompatible `v1` dans `ReportQualityGate.evaluate_report` (`backend/app/services/report_quality_gate.py:413-458`).
  4. Suppression définitive de la phrase statique inconditionnelle `- **Règle anti-affabulation :** Toute affirmation qualifiée d'action observée est reliée à un événement horodaté du run...` dans la sous-section 3 de `ReportAgent.build_sources_provenance_section` (`backend/app/services/report_agent.py:3295-3335`), remplacement par un libellé 100 % calculé depuis l'instance `ReportClaimRegistry` partagée avec la sous-section 7 (`backend/app/services/report_agent.py:3399-3457`), et exposition explicite des compteurs `asserted_action_claims` / `verified_action_claims`.
  5. Alignement des compteurs d'actions vérifiées dans `report_history.json` (`ReportAgent.generate_report` `:3009-3015`) pour ne comptabiliser en `verified_action_claims_count` que les actions sociales observées effectivement vérifiées.
  6. Suite de tests unitaires et d'intégration hermétiques dédiée dans `backend/tests/test_story_015_3_quality_gate_and_provenance.py`, incluant un test de non-régression sur la structure exacte de l'anomalie R8 (`report_934d3254004b`).
- **Exclus** :
  - Toute modification de la politique de participation par rôle (`prospect`, `competitor`, `observer`, `facilitator`, `catalyst`), du dénominateur d'adoption `prospect_members` ou du filtre `[persona non admis]` dans `brief_consistency.py` (réservés à la **Story `015-4`**).
  - Toute modification des composants Vue 3 (`Step3Simulation.vue`, `Step4Report.vue`) ou de la persistance incrémentale de `usage.json` (réservés à la **Story `015-5`**).
  - Le contrôle biographique aval de la prose finale, l'injection `GIT_COMMIT` Docker et le script `verifier_qualification_epic_015.py` (réservés à la **Story `015-6`**).
  - Toute modification du moteur de benchmark `backend/app/utils/report_benchmark_score.py` (grille `v1.1.0` figée par l'Epic 013).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  - **Faits mesurés sur le run R8 (`sim_7a1b02b8c092` / `report_934d3254004b`) et causes racines dans le code au `HEAD` (`dbb39b7`)** :
    | Symptôme observé sur R8 (`report_934d3254004b`) | Cause racine exacte vérifiée dans le code (`HEAD` `dbb39b7`) | Correction structurelle de la Story `015-3` |
    |---|---|---|
    | **D03 — Angle mort « rapport conceptuel » sur `ReportQualityGate`** : dans `quality_checks.json` (`:62-75`), `claim_verification` est noté `warning` avec le message `"Rapport conceptuel sans allégation d'actions observées : 165 assertion(s) analysée(s), 0 action simulée"` (`action_claims: 0`, `verified_action_claims: 0`), alors que le rapport affirme de nombreuses actions sociales non prouvées. | Dans `SimulationActionVerifier.verify_report_claim` (`backend/app/services/simulation_action_verifier.py:1357, 1423, 1444, 1523, 1716`), toute affirmation d'action (`OBSERVED_SOCIAL_ACTION` ou `asserted_as_action=True`) qui échoue à la preuve voit son `claim_kind` déclassé en `REPORTED_INTENTION` ou `SPECULATIVE_PROJECTION`. Or `ReportQualityGate.evaluate_report` (`backend/app/services/report_quality_gate.py:495-498`) calcule `action_claims = [c for c in claims_registry.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION]`. Quand 100 % des actions affirmées sont déclassées, `len(action_claims) == 0` : la barrière saute `elif action_claims and len(verified_action_claims) == 0:` (`:605`) et tombe dans `elif not action_claims:` (`:639`), émettant un simple `WARNING` au lieu de `FAILED`. De plus, si 1 action sur 10 est vérifiée et 9 sont déclassées, l'ancien `action_ratio` vaut `1/1 = 100 %` (`PASSED`) au lieu de `1/10 = 10 %` (`FAILED`). | Calculer `asserted_actions = [c for c in claims_registry.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION or getattr(c, "asserted_as_action", False)]` et `verified_action_claims = [c for c in asserted_actions if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION and c.verification_status == VerificationStatus.VERIFIED]`. Le ratio `action_ratio` a pour dénominateur `len(asserted_actions)`. Si `len(asserted_actions) > 0` et `len(verified_action_claims) == 0` → `QualityStatus.FAILED` (`r6_anomaly_detected=True`). Si `len(asserted_actions) == 0` mais que `report_markdown` allègue des actions simulées (`_markdown_alleges_simulated_actions`) → `QualityStatus.FAILED` (`unparseable_action_claims=True`). |
    | **D03 — Rejet de la section d'objections malgré `9 027` octets dédiés aux verrous** : dans `quality_checks.json` (`:52-60`) et `outline.json` (`:13-16`), `limitations_section` est en `FAILED` alors que la section 3 (`## Les verrous réels et les leviers qui fonctionnent (ou pas)`) analyse en détail les 3 verrous de la cohorte, le refus de Florence et les ajournements. | Dans `plan_outline` (`backend/app/services/report_agent.py:2155-2164`), la présence du mot `"risques"` dans la section 5 (`"Signaux faibles et risques à surveiller dans les 72 heures"`) a satisfait `has_objection_section` et empêché l'injection du titre canonique. Puis `ReportQualityGate.evaluate_report` (`backend/app/services/report_quality_gate.py:425-430`) n'a accepté que **4 chaînes littérales exactes** (`"objections non levées, contradictions et limites"`, `"objections et limites"`, `"unresolved objections, contradictions, and limitations"`, `"limitations and objections"`), rejetant à la fois la section 3 (« verrous ») et la section 5 (« risques »). | Introduire `section_role: Optional[str] = None` sur `ReportSection`. `plan_outline` et `_get_default_outline` marquent explicitement la section d'objections/verrous/limites avec `section_role="limitations"`. `ReportQualityGate` valide prioritairement toute section de `outline` portant `section_role == "limitations"` dont le titre `## <title>` figure dans `report_markdown` avec un corps substantiel (`>= 50` car.) traitant effectivement des freins/objections/limites, et conserve un repli heuristique élargi pour les rapports `v1` sans `section_role`. |
    | **D07 — Auto-contradiction frontale dans `## Sources & Provenance`** : dans `full_report.md` (`:350` vs `:391-397`), la sous-section 3 affirme : *« Toute affirmation qualifiée d'action observée est reliée à un événement horodaté du run »*, tandis que la sous-section 7 affiche `Affirmations portant un evidence_refs non vide : 0` et `Taux de vérification : 0.0 %`. | Dans `ReportAgent.build_sources_provenance_section` (`backend/app/services/report_agent.py:3321`), la puce `- **Règle anti-affabulation :**` est une chaîne constante codée en dur, émise avant même que `registry` ne soit chargé à la sous-section 7 (`:3401`). | Charger/résoudre `registry` une seule fois en amont de la sous-section 3 et calculer dynamiquement le libellé de `- **Règle anti-affabulation :**` à partir de `asserted_action_claims` et `verified_action_claims`, sans jamais certifier une conformité non prouvée. |
  - **Ce qui est garanti par sous-ensemble** :
    - **Contrôle 5 (`CLAIM_VERIFICATION`) de `ReportQualityGate`** :
      - Si `len(asserted_actions) > 0` et `len(verified_action_claims) == 0` : verdict **toujours `QualityStatus.FAILED`** (`PublicationStatus.FAILED_VALIDATION`, `is_publishable=False`, `r6_anomaly_detected=True`), que les actions affirmées soient restées `OBSERVED_SOCIAL_ACTION` (`UNSUPPORTED` / `CONTRADICTED`) ou qu'elles aient toutes été déclassées en `REPORTED_INTENTION` / `SPECULATIVE_PROJECTION` avec `asserted_as_action=True`.
      - Si `len(asserted_actions) > 0` et `0 < len(verified_action_claims) / len(asserted_actions) < 0.50` : verdict **toujours `QualityStatus.FAILED`** (`PublicationStatus.FAILED_VALIDATION`, `is_publishable=False`).
      - Si `len(asserted_actions) == 0` et que `report_markdown` contient néanmoins des allégations narratives d'actions simulées ou de rounds (`_markdown_alleges_simulated_actions(report_markdown) is True`) : verdict **toujours `QualityStatus.FAILED`** (`unparseable_action_claims=True`).
      - Le statut `QualityStatus.WARNING` (« Rapport conceptuel sans allégation d'actions observées ») est **strictement réservé** au cas où `len(asserted_actions) == 0` dans le registre **et** aucune action simulée n'est alléguée dans le corps Markdown hors `## Sources & Provenance`.
    - **Contrôle 4 (`LIMITATIONS_SECTION`) de `ReportQualityGate` et contrat `ReportOutline`** :
      - `ReportSection` porte `section_role: Optional[str] = None`.
      - Lorsque la cohorte présente au moins un refus, une réserve ou une non-adoption (`has_rejections`), `ReportQualityGate` accepte la section dès lors que :
        1. soit une section de `outline.sections` porte `section_role == "limitations"`, son titre `## <title>` est présent dans `report_markdown`, son corps fait au moins `50` caractères hors espaces et contient au moins un marqueur lexical de limites/objections/verrous/refus/réserves ;
        2. soit (repli rétrocompatible `v1` si `outline` est absent ou dépourvu de `section_role == "limitations"`) une section `## ...` du Markdown porte un intitulé de limites/objections/verrous/freins/risques/réserves et un corps substantiel (`>= 50` caractères) traitant des objections/limites.
    - **Section `## Sources & Provenance` (`build_sources_provenance_section`)** :
      - Aucune phrase de la sous-section 3 ne certifie que les actions observées sont reliées à un événement horodaté si le registre est absent, si `asserted_action_claims == 0`, ou si `verified_action_claims < asserted_action_claims`.
      - Les sous-sections 3 et 7 lisent la même instance `ReportClaimRegistry` et affichent des compteurs strictement identiques.
  - **Invariants « jamais / toujours »** :
    - **Jamais** un rapport ayant `asserted_action_claims > 0` et `verified_action_claims == 0` ne doit obtenir `QualityStatus.WARNING` ou `QualityStatus.PASSED` sur `CLAIM_VERIFICATION`.
    - **Jamais** une sous-chaîne accidentelle comme `"sign"` dans *signal*, *signifie* ou *souligne* ne doit déclencher une fausse détection d'affirmation d'adoption dans `ReportQualityGate`.
    - **Jamais** une section taguée `section_role="limitations"` mais vide (`< 50` caractères) ou dépourvue de tout lexique d'objections/limites/refus/verrous ne doit valider `LIMITATIONS_SECTION` lorsque `has_rejections` est vrai.
    - **Toujours** conserver l'amorce `- **Règle anti-affabulation` dans la sous-section 3 de `## Sources & Provenance` pour préserver le contrat structurel existant, tout en rendant son contenu 100 % calculé depuis le registre.

- [x] **Documents consultés** :
  - [`AGENTS.md`](../../../AGENTS.md) — Constitution du dépôt, règles d'ingénierie (KISS, DRY, SOLID, généricité), protocole de développement et de revue, convention de langue française.
  - [`docs/STATUS.md`](../../STATUS.md) et [`docs/sprint-status.yaml`](../../sprint-status.yaml) — État courant de l'Epic 015 (`015-1` et `015-2` `done`, `2 121` tests backend + `43` tests frontend verts).
  - [`docs/plans/015-contrats-preuve-roles-et-ihm/epic-015.md`](epic-015.md) — Hub de l'Epic 015, périmètre de la Story `015-3`, critère de sortie **C3**.
  - [`docs/plans/015-contrats-preuve-roles-et-ihm/prd.md`](prd.md) — Exigences `FR-04`, `NFR-1`, `NFR-2`, `NFR-3`, `NFR-5` et critères d'acceptation de la Story `015-3`.
  - [`docs/plans/015-contrats-preuve-roles-et-ihm/architecture.md`](architecture.md) — §3.1 (Flux A de bout en bout), §3.2 (chantiers `report_quality_gate.py` et `report_agent.py`), §4.1 (Contrat 1 `asserted_as_action` / `asserted_action_claims`) et §4.3 (Contrat 3 `ReportSection.section_role`).
  - [`docs/plans/015-contrats-preuve-roles-et-ihm/story-015-1.md`](story-015-1.md) et [`story-015-2.md`](story-015-2.md) — Contrats livrés en amont (`asserted_as_action`, `asserted_action_claims`, `verified_action_claims`, `_ACTION_VERB_FR_RE`, `_ACTION_VERB_EN_RE`, `_PURE_NEGATION_ACTION_RE`).
  - [`docs/PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md`](../../PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md) — Diagnostics sources D03, D07, spécification P0-3 et tests d'acceptation AT-12, AT-13, AT-14.
  - Code source et tests existants inspectés :
    - [`backend/app/services/report_quality_gate.py`](../../../backend/app/services/report_quality_gate.py) (lignes `1-750`, en particulier `evaluate_report` `:251-749`, Contrôle 4 `:413-458` et Contrôle 5 `:460-730`).
    - [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) (`ReportSection` `:497-516`, `ReportOutline` `:518-538`, `PLAN_SYSTEM_PROMPT` `:675-713`, `_get_default_outline` `:1098-1130`, `plan_outline` `:2049-2183`, `generate_report` `:2650-3030`, `build_sources_provenance_section` `:3218-3458`, `ReportManager.get_report` `:5048-5078`).
    - [`backend/app/models/report_claim.py`](../../../backend/app/models/report_claim.py) (`ReportClaim.asserted_as_action` `:131`, `ReportClaimRegistry.asserted_action_claims` `:249-253`, `verified_action_claims` `:255-260`).
    - [`backend/app/models/report_quality.py`](../../../backend/app/models/report_quality.py) (`QualityCategory`, `QualityStatus`, `PublicationStatus`, `QualityCheckItem`, `QualityGateResult`).
    - [`backend/tests/test_report_quality_gate_audit.py`](../../../backend/tests/test_report_quality_gate_audit.py), [`backend/tests/test_sources_provenance_honesty.py`](../../../backend/tests/test_sources_provenance_honesty.py), [`backend/tests/test_report_agent_provenance.py`](../../../backend/tests/test_report_agent_provenance.py), [`backend/tests/test_silence_rule_reaches_prose.py`](../../../backend/tests/test_silence_rule_reaches_prose.py).
    - Artefacts R8 de référence dans `backend/uploads/reports/report_934d3254004b/` (`quality_checks.json`, `outline.json`, `full_report.md`).

- [x] **Dépendances résolues** :
  - Les stories `015-1` et `015-2` sont à l'état `done`.
  - Le filet de tests existant a été exécuté et mesuré au `HEAD` (`dbb39b7`) ce 29 octobre 2026 : **`2 121` tests backend passants** (`0` échec) et **`43` tests frontend Node passants** (`0` échec).

- [x] **Décisions d'ingénierie arrêtées avant code** :
  - **D1 — Contrat structurel `section_role: Optional[str] = None` sur `ReportSection` et `ReportOutline` (`backend/app/services/report_agent.py:497-538, 5048-5078`)** :
    - Ajouter l'attribut optionnel `section_role: Optional[str] = None` sur `ReportSection` (`:498-504`). Les valeurs normalisées attendues sont `"overview"`, `"analysis"`, `"limitations"`, `"recommendations"` ou `None` (toute chaîne non vide est normalisée en `str.strip().lower()`, ou `None` si vide).
    - Dans `ReportSection.to_dict()` (`:506-511`), sérialiser `"section_role": self.section_role` (aux côtés de `"title"` et `"content"`).
    - Ajouter une méthode de classe `ReportSection.from_dict(cls, data: Dict[str, Any]) -> "ReportSection"` qui accepte un dictionnaire `v1` (sans `section_role`) ou `v2` (avec `section_role`) et retourne `cls(title=str(data.get("title", "")), content=str(data.get("content", "")), section_role=...)`.
    - Utiliser `ReportSection.from_dict(s)` dans `ReportManager.get_report` (`backend/app/services/report_agent.py:5051-5055`) afin que les rapports relus depuis `outline.json` / `meta.json` restaurent fidèlement `section_role`.
  - **D2 — Attribution et garantie de `section_role="limitations"` dans `plan_outline` et `_get_default_outline` (`backend/app/services/report_agent.py:675-713, 1098-1130, 2115-2172`)** :
    - Dans `PLAN_SYSTEM_PROMPT` (`:700-712`) et le prompt utilisateur de `plan_outline` (`:2080-2090`) : documenter le champ optionnel `"section_role"` dans le schéma JSON de chaque section (`"overview" | "analysis" | "limitations" | "recommendations"`), en exigeant qu'exactement une section porte `"section_role": "limitations"` dès que la simulation comporte des refus, objections, verrous, réserves ou limites méthodologiques.
    - Dans `_get_default_outline` (`:1098-1130`) : attribuer `section_role="overview"` à la section 1, `section_role="analysis"` à la section 2 et `section_role="limitations"` à la section 3 (qui couvre les verrous/risques/perspectives dans les 3 locales `zh`, `fr`, `en`).
    - Dans `plan_outline` (`:2115-2172`) :
      1. Lors de la construction de `sections` depuis la réponse JSON du LLM (`:2115-2122`), lire `raw_role = s.get("section_role")` normalisé.
      2. Si aucune section générée ne porte encore `section_role == "limitations"`, inspecter les titres générés avec un ensemble de marqueurs structurels FR/EN élargi (`_LIMITATIONS_TITLE_MARKERS = ("objection", "limite", "contradiction", "reserve", "réserve", "verrou", "blocage", "frein", "réticence", "reticence", "refus", "obstacle", "risque", "limit", "risk", "caveat", "drawback", "concern", "barrier", "blocker", "friction")`) en privilégiant en premier les titres contenant un marqueur de verrou/objection/limite/frein/refus/contradiction avant le mot générique `"risque"`, et affecter `section_role = "limitations"` à la section correspondante.
      3. Si `has_objections` est vrai (`:2151`) et qu'aucune section ne porte toujours `section_role == "limitations"`, injecter la section canonique dédiée avec `section_role="limitations"` (`:2166-2167`).
  - **D3 — Validation hybride (`section_role="limitations"` + repli `v1`) et garde de pertinence du contenu dans `ReportQualityGate` (`backend/app/services/report_quality_gate.py:413-458`)** :
    - Lorsque `has_rejections` est vrai :
      1. **Voie primaire (contrat `section_role="limitations"`)** : extraire de `outline` (qu'il s'agisse d'une instance `ReportOutline` ou d'un `dict` issu d'`outline.json`) les sections dont `section_role == "limitations"`. Pour chaque section candidate, rechercher dans `report_markdown` l'en-tête `## <title>` correspondant (correspondance exacte normalisée ou inclusion insensible à la casse), extraire son corps jusqu'au prochain titre `## `, et vérifier deux conditions :
         - `len(section_body.strip()) >= 50` ;
         - le titre ou le corps contient au moins un marqueur lexical substantiel de limites/objections/refus/réserves (`_LIMITATIONS_CONTENT_RE` : `objection|limite|contradiction|r[ée]serve|refus|rejet|verrou|blocage|frein|r[ée]ticence|non[- ]adoption|abstention|ajournement|obstacle|risque|limit|objection|contradiction|caveat|drawback|concern|rejection|refusal|barrier|blocker|hesitation`). Cette seconde condition empêche qu'une section hors-sujet artificiellement étiquetée `section_role="limitations"` ne valide la barrière.
      2. **Voie de repli rétrocompatible (`v1` / rapports sans `section_role`)** : si `outline` est absent ou ne contient aucune section `section_role == "limitations"`, scanner toutes les sections `## <heading>` de `report_markdown` (hors `## Sources & Provenance`). Une section valide le contrôle si son en-tête contient l'un des intitulés historiques FR/EN ou un marqueur de `_LIMITATIONS_HEADING_RE` (`objection`, `limite`, `contradiction`, `réserve`, `verrou`, `blocage`, `frein`, `refus`, `risque`, `limit`, `caveat`, `drawback`, `concern`, `barrier`, `blocker`, `risk`) **et** que son corps fait `>= 50` caractères tout en satisfaisant `_LIMITATIONS_CONTENT_RE`.
    - Conserver dans `details` les clés `"has_rejections_or_objections"` et `"limitations_heading_present"` (attendues par les tests existants) et y ajouter `"limitations_role_matched": bool` et `"matched_section_title": Optional[str]`.
  - **D4 — Fermeture de l'angle mort « rapport conceptuel » et redéfinition de `action_ratio` dans `ReportQualityGate` (`backend/app/services/report_quality_gate.py:494-698`)** :
    - Remplacer la sélection `action_claims = [c for c in claims_registry.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION]` par :
      - `asserted_actions = [c for c in claims_registry.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION or getattr(c, "asserted_as_action", False)]`
      - `strict_action_claims = [c for c in claims_registry.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION]`
      - `downgraded_action_claims = [c for c in asserted_actions if c.claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION]`
      - `verified_action_claims = [c for c in asserted_actions if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION and c.verification_status == VerificationStatus.VERIFIED]`
    - Calculer `action_ratio = (len(verified_action_claims) / len(asserted_actions)) if asserted_actions else 1.0`.
    - Dans l'arbre de décision du Contrôle 5 (`:556-685`) :
      - **Cas 1 (`asserted_actions` non vide et `len(verified_action_claims) == 0`)** : émettre **systématiquement `QualityStatus.FAILED`** (`"Absence totale de preuves authentiques sur les actions affirmées : ..."`), avec `r6_anomaly_detected=True`, `"action_claims": len(asserted_actions)`, `"asserted_action_claims": len(asserted_actions)`, `"strict_action_claims": len(strict_action_claims)`, `"downgraded_action_claims": len(downgraded_action_claims)`, `"verified_action_claims": 0` dans `details`. Le libellé conserve la sous-chaîne `"Absence totale de preuves authentiques"` vérifiée par `backend/tests/test_report_quality_gate_audit.py:736`.
      - **Cas 2 (`asserted_actions` non vide et `action_ratio < 0.50`)** : émettre **`QualityStatus.FAILED`** (`"Couverture de preuves insuffisante..."`), y compris lorsque la baisse du ratio provient d'actions déclassées (`downgraded_action_claims`).
      - **Cas 3 (`len(asserted_actions) == 0`)** : appeler un helper `_markdown_alleges_simulated_actions(report_markdown: str) -> bool` qui inspecte le Markdown hors `## Sources & Provenance` et hors citations d'entretiens (`> « ... »`), en ignorant les phrases de négation explicite (`"sans actions simulées"`, `"aucune action"`, `_PURE_NEGATION_ACTION_RE`). Si le Markdown narre néanmoins des actions sociales exécutées (`_ACTION_VERB_FR_RE` / `_ACTION_VERB_EN_RE` couplés à un marqueur d'exécution en simulation : `round \d+`, `durant la simulation`, `sur reddit`, `sur twitter`, `a publié`, `a posté`, `a souscrit`, `a adopté`, `evt_`), émettre **`QualityStatus.FAILED`** (`"unparseable_action_claims": True`, `"r6_anomaly_detected": True`). Sinon seulement, émettre `QualityStatus.WARNING` (« Rapport conceptuel sans allégation d'actions observées »).
  - **D5 — Durcissement par `\b` de la détection d'adoption (`ADOPTED_VERIFIED`) et de la branche sans registre dans `ReportQualityGate` (`backend/app/services/report_quality_gate.py:513-554, 699-730`)** :
    - Dans le contrôle d'affabulation d'adoption (`:513-554`), remplacer la recherche par sous-chaîne `any(k in c_text_lower for k in (..., "sign", ...))` (qui matchait *signal*, *signifie*, *souligne*) par une expression régulière à frontières de mots `_ADOPTION_CLAIM_RE` (`\b(?:a\s+adopt[ée]|adopt[ée]s?|adopte|a\s+souscrit|souscrit|s['’]est\s+abonn[ée]e?s?|a\s+achet[ée]|achet[ée]s?|ach[èe]te|a\s+pay[ée]|pay[ée]s?|a\s+command[ée]|command[ée]s?|a\s+sign[ée]\s+(?:le\s+contrat|l['’]abonnement|l['’]offre|un\s+contrat)|adopted|subscribed|subscribes|purchased|bought|paid|ordered)\b`) en excluant toute négation (`_PURE_NEGATION_ACTION_RE` ou `\b(?:sans|aucun[e]?|pas|jamais|ni|refus[ée]?|rejet[ée]?|not|never|no|without)\b`).
    - Pour qu'un claim satisfasse `has_verified_adoption_claim` lorsque `adopted_count > 0`, exiger que :
      1. `c.verification_status == VerificationStatus.VERIFIED` ;
      2. `c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION` ;
      3. `any(str(ref).startswith("evt_") for ref in (c.evidence_refs or []))` ;
      4. si `c.agent_name` est renseigné et que la liste `adopted_members` de `consensus_summary` est non vide, `c.agent_name` correspond à l'un des membres de `adopted_members`.
    - Dans la branche de secours sans `claims_registry` (`:699-730`), réutiliser les expressions régulières `_ACTION_VERB_FR_RE` et `_ACTION_VERB_EN_RE` de `SimulationActionVerifier` (en excluant `_PURE_NEGATION_ACTION_RE`) pour détecter aussi bien le présent de narration que le passé composé.
  - **D6 — Calcul 100 % dynamique de la sous-section 3 et harmonisation avec la sous-section 7 dans `build_sources_provenance_section` (`backend/app/services/report_agent.py:3295-3335, 3399-3457`)** :
    - Extraire la résolution de `registry` (paramètre `claims_registry` ou relecture disque `reports/<report_id>/report_claims.json` puis `simulations/<sim_id>/report_claims.json`) dans un bloc unique situé **avant** la sous-section 3 (`### 3. Actions simulées (OASIS)`), afin que les sous-sections 3 et 7 travaillent sur la même instance `registry`.
    - Remplacer la ligne statique `:3321` (`"- **Règle anti-affabulation :** Toute affirmation qualifiée d'action observée est reliée à un événement horodaté du run..."`) par une fonction pure `_format_anti_affabulation_status(registry: Optional[ReportClaimRegistry]) -> str` qui produit :
      - Si `registry is None` :
        `"- **Règle anti-affabulation :** Traçabilité non établie (registre d'affirmations absent ou illisible — aucune affirmation d'action observée n'est certifiée)."`
      - Si `asserted_actions_count == 0` :
        `"- **Règle anti-affabulation :** Aucune affirmation d'action sociale exécutée n'est revendiquée au registre (0 action affirmée, 0 action vérifiée). Les simples déclarations d'intention ou d'entretien restent classées hors actions observées."`
      - Si `asserted_actions_count > 0` et `verified_actions_count == asserted_actions_count` :
        `f"- **Règle anti-affabulation :** Les {verified_actions_count}/{asserted_actions_count} affirmation(s) d'action observée du registre sont reliées à un événement horodaté du run (100.0 % vérifiées). Les simples déclarations d'intention simulées n'ont pas été promues en actions observées."`
      - Si `asserted_actions_count > 0` et `0 < verified_actions_count < asserted_actions_count` :
        `f"- **Règle anti-affabulation :** Couverture partielle des preuves d'action — {verified_actions_count}/{asserted_actions_count} affirmation(s) d'action affirmée sont reliées à un événement horodaté du run ({action_verification_rate:.1f} %) ; {unverified_actions_count} affirmation(s) non prouvée(s) ont été déclassées ou écartées."`
      - Si `asserted_actions_count > 0` et `verified_actions_count == 0` (cas R8) :
        `f"- **Règle anti-affabulation :** Aucune affirmation d'action sociale n'a pu être certifiée (0/{asserted_actions_count} vérifiée(s) par un événement horodaté du run) ; les {asserted_actions_count} allégation(s) d'action non prouvées ont été déclassées ou marquées en échec de vérification."`
    - Dans la sous-section 7 (`### 7. Vérification des affirmations du rapport`, `:3441-3453`), conserver intégralement les puces existantes (pour la compatibilité avec `test_sources_provenance_honesty.py`) et ajouter deux puces explicites :
      - `f"- **Actions sociales affirmées (\`asserted_as_action\`) :** {asserted_actions_count}."`
      - `f"- **Actions sociales vérifiées (\`OBSERVED_SOCIAL_ACTION\` + \`VERIFIED\`) :** {verified_actions_count}."`
  - **D7 — Alignement de `verified_action_claims_count` dans `report_history.json` (`backend/app/services/report_agent.py:3009-3015`)** :
    - Dans `ReportAgent.generate_report` (`:3009-3015`), remplacer le filtre `c.verification_status.value == "verified"` (qui comptait tout claim `VERIFIED` quelle que soit sa nature, y compris une hypothèse ou une intention) par `claims_registry.verified_action_claims` (qui compte exclusivement les `OBSERVED_SOCIAL_ACTION` à l'état `VERIFIED`), et exposer également `"asserted_action_claims_count": claims_registry.asserted_action_claims` dans l'entrée d'historique.

- [x] **Stratégie de tests identifiée** :
  - Nouveau fichier de tests hermétiques dédié : `backend/tests/test_story_015_3_quality_gate_and_provenance.py` couvrant chaque critère `AC1` à `AC10`.
  - Exécution conjointe des suites de non-régression liées :
    - `backend/tests/test_report_quality_gate_audit.py`
    - `backend/tests/test_sources_provenance_honesty.py`
    - `backend/tests/test_report_agent_provenance.py`
    - `backend/tests/test_silence_rule_reaches_prose.py`
    - `backend/tests/test_story_015_1_action_Verification_contracts.py`
    - `backend/tests/test_story_015_2_interview_registry_v2.py`

---

## Critères d'acceptation

- **AC1 — Fermeture de l'angle mort « rapport conceptuel » quand 100 % des actions affirmées sont déclassées (FR-04, C3, AT-12)** :
  - **Étant donné** un `ReportClaimRegistry` contenant `N >= 1` affirmations initialement émises comme actions sociales (`asserted_as_action=True`) mais toutes déclassées par `SimulationActionVerifier` en `REPORTED_INTENTION` ou `SPECULATIVE_PROJECTION` avec `verification_status != VerificationStatus.VERIFIED` (de sorte que `len([c for c in claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION]) == 0` mais `claims_registry.asserted_action_claims == N` et `claims_registry.verified_action_claims == 0`),
  - **Quand** `ReportQualityGate.evaluate_report(...)` évalue ce rapport,
  - **Alors** le contrôle `QualityCategory.CLAIM_VERIFICATION` retourne `status == QualityStatus.FAILED` (et **jamais** `QualityStatus.WARNING` « Rapport conceptuel »), `result.publication_status == PublicationStatus.FAILED_VALIDATION`, `result.is_publishable is False`, et `claim_check.details` expose `"action_claims": N`, `"asserted_action_claims": N`, `"downgraded_action_claims": N`, `"verified_action_claims": 0` et `"r6_anomaly_detected": True`.
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac1_all_downgraded_actions_fail_quality_gate_not_conceptual_warning`.

- **AC2 — Calcul de `action_ratio` sur le dénominateur complet des actions affirmées (`asserted_actions`) (FR-04, C3)** :
  - **Étant donné** un `ReportClaimRegistry` contenant `10` affirmations avec `asserted_as_action=True`, dont `1` seule est restée `OBSERVED_SOCIAL_ACTION` à l'état `VERIFIED` et `9` ont été déclassées en `REPORTED_INTENTION` (`UNSUPPORTED`) faute d'événement `evt_*`,
  - **Quand** `ReportQualityGate.evaluate_report(...)` calcule le taux de vérification des actions,
  - **Alors** `action_ratio` vaut `1 / 10 = 0.10` (`10 % < 50 %`) — et non `1 / 1 = 1.0` — et le contrôle `QualityCategory.CLAIM_VERIFICATION` échoue avec `status == QualityStatus.FAILED` (`PublicationStatus.FAILED_VALIDATION`).
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac2_action_ratio_uses_all_asserted_actions_as_denominator`.

- **AC3 — Filet Markdown anti-contournement quand `asserted_actions == 0` mais que la prose narre des actions simulées (FR-04, C3)** :
  - **Étant donné** un `ReportClaimRegistry` ne contenant aucune affirmation marquée `OBSERVED_SOCIAL_ACTION` ni `asserted_as_action=True` (par exemple uniquement des `SCENARIO_HYPOTHESIS`),
  - **Quand** `ReportQualityGate.evaluate_report(...)` est appelé sur un `report_markdown` dont le corps (hors `## Sources & Provenance` et hors citations d'entretien) narre explicitement des actions sociales exécutées durant les rounds de simulation (ex. *« Durant le round 2, @ Claire_Dumont a publié un post sur Reddit et a souscrit à l'offre »*),
  - **Alors** `QualityCategory.CLAIM_VERIFICATION` échoue en `QualityStatus.FAILED` avec `details["unparseable_action_claims"] is True` ; inversement, sur un rapport véritablement théorique sans action simulée (y compris mentionnant la négation *« modèle sans actions simulées »*), le contrôle conserve le statut `QualityStatus.WARNING` (`PublicationStatus.NEEDS_REVIEW`).
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac3_zero_asserted_actions_with_narrative_action_prose_fails_gate`.

- **AC4 — Contrat structurel `ReportSection.section_role` et propagation dans `ReportOutline` / `plan_outline` (FR-04, NFR-1, C3)** :
  - **Étant donné** le modèle `ReportSection` et `ReportOutline` dans `backend/app/services/report_agent.py`,
  - **Quand** un plan est construit via `_get_default_outline`, `plan_outline` ou désérialisé via `ReportSection.from_dict` / `ReportManager.get_report`,
  - **Alors** :
    1. `ReportSection.to_dict()` inclut `"section_role"` et `ReportSection.from_dict()` relit aussi bien un dictionnaire `v2` (avec `section_role`) qu'un dictionnaire `v1` historique (sans `section_role`, valué à `None`) ;
    2. dans `plan_outline`, si la cohorte comporte des objections/refus (`has_objections=True`) et que le LLM génère une section intitulée par exemple `"Les verrous réels et les leviers qui fonctionnent (ou pas)"` (sans mot-clé `"objection"` mais avec `"verrous"`), `plan_outline` lui attribue `section_role == "limitations"` sans injecter de section doublon ;
    3. si aucune section générée par le LLM ne traite des verrous/objections/limites alors que `has_objections=True`, `plan_outline` injecte la section dédiée avec `section_role == "limitations"`.
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac4_report_section_role_serialization_and_plan_outline_assignment`.

- **AC5 — Validation de `QualityCategory.LIMITATIONS_SECTION` par `section_role="limitations"` et repli rétrocompatible `v1` (FR-04, NFR-1, C3, AT-13)** :
  - **Étant donné** une simulation présentant au moins un refus ou une réserve (`has_rejections=True`) et un rapport dont la section consacrée aux freins s'intitule `## Les verrous réels et les leviers qui fonctionnent (ou pas)` avec un corps substantiel (`>= 50` caractères) analysant les verrous, refus et réserves,
  - **Quand** `ReportQualityGate.evaluate_report(...)` évalue ce rapport :
    1. avec un `outline` où cette section porte `section_role="limitations"` → `LIMITATIONS_SECTION` passe à `QualityStatus.PASSED` avec `details["limitations_role_matched"] is True` et `details["matched_section_title"] == "Les verrous réels et les leviers qui fonctionnent (ou pas)"` ;
    2. avec un `outline` historique `v1` dépourvu de `section_role` → le repli structurel reconnait le titre `## Les verrous réels...` et le contenu d'objections/refus et passe à `QualityStatus.PASSED` ;
    3. avec une section frauduleusement taguée `section_role="limitations"` mais dont le corps est trop court (`< 50` caractères) ou ne contient aucun lexique d'objections/limites/verrous/refus → `LIMITATIONS_SECTION` échoue en `QualityStatus.FAILED`.
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac5_limitations_section_validated_by_role_and_v1_fallback`.

- **AC6 — Détection d'adoption (`ADOPTED_VERIFIED`) par frontières de mots `\b` sans faux positifs par sous-chaîne (FR-04, NFR-2)** :
  - **Étant donné** une simulation où `adopted_count == 0` et un rapport contenant des affirmations avec les mots *« signal faible »*, *« souligne une réserve »*, *« signifie un rejet »* ou *« n'a pas adopté »*,
  - **Quand** `ReportQualityGate.evaluate_report(...)` exécute le contrôle d'affabulation d'adoption,
  - **Alors** aucune de ces affirmations n'est prise à tort pour une allégation d'adoption (`adoption_affabulation` reste `False`) ; en revanche, une affirmation positive *« Chloé a souscrit à l'abonnement »* alors que `adopted_count == 0` déclenche bien `QualityStatus.FAILED` (`adoption_affabulation=True`).
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac6_adoption_detection_word_boundaries_and_negation_guard`.

- **AC7 — Suppression du littéral statique et calcul 100 % honnête de la sous-section 3 dans `build_sources_provenance_section` (FR-04, NFR-5, C3, AT-14)** :
  - **Étant donné** `ReportAgent.build_sources_provenance_section(...)` appelé selon les 4 configurations suivantes du `ReportClaimRegistry` :
    1. `claims_registry=None` (et aucun fichier `report_claims.json` sur disque) ;
    2. registre avec `asserted_action_claims == 12` et `verified_action_claims == 0` (cas R8 où toutes les actions affirmées sont non prouvées / déclassées) ;
    3. registre avec `asserted_action_claims == 4` et `verified_action_claims == 2` (couverture partielle `50.0 %`) ;
    4. registre avec `asserted_action_claims == 5` et `verified_action_claims == 5` (`100.0 %` prouvées par `evt_*`),
  - **Quand** la section `## Sources & Provenance` est générée,
  - **Alors** :
    - dans les cas 1, 2 et 3, la chaîne trompeuse *"Toute affirmation qualifiée d'action observée est reliée à un événement horodaté du run"* est **strictement absente** de toute la section ;
    - dans le cas 1, la puce `- **Règle anti-affabulation :**` mentionne explicitement `"Traçabilité non établie"` ;
    - dans le cas 2, la puce `- **Règle anti-affabulation :**` mentionne explicitement `"0/12"` et l'absence de certification, en parfaite cohérence avec la sous-section 7 qui affiche `Actions sociales affirmées (\`asserted_as_action\`) : 12` et `Actions sociales vérifiées (\`OBSERVED_SOCIAL_ACTION\` + \`VERIFIED\`) : 0` ;
    - dans le cas 3, la puce mentionne `"2/4"` (`50.0 %`) ;
    - dans le cas 4 uniquement, la puce certifie que les `"5/5"` affirmations d'action observée sont reliées à un événement horodaté du run (`100.0 %`).
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac7_sources_provenance_subsection3_is_fully_computed_and_matches_subsection7`.

- **AC8 — Qualification directe sur la structure exacte du cas R8 (`report_934d3254004b` / `sim_7a1b02b8c092`) (FR-04, C3, C7)** :
  - **Étant donné** une fixture reproduisant fidèlement les données de `report_934d3254004b` (`outline.json` avec la section 3 `"Les verrous réels et les leviers qui fonctionnent (ou pas)"` et la section 5 `"Signaux faibles et risques à surveiller dans les 72 heures"`, `165` claims dont des actions affirmées toutes déclassées en `REPORTED_INTENTION` avec `asserted_as_action=True` et `0` `evidence_refs`, et `has_rejections=True`),
  - **Quand** on exécute `ReportQualityGate.evaluate_report(...)` et `ReportAgent.build_sources_provenance_section(...)`,
  - **Alors** :
    1. `LIMITATIONS_SECTION` passe de `FAILED` à `PASSED` ;
    2. `CLAIM_VERIFICATION` passe de `WARNING` (« Rapport conceptuel ») à `FAILED` (`r6_anomaly_detected=True`, `is_publishable=False`, `publication_status == PublicationStatus.FAILED_VALIDATION`) ;
    3. `## Sources & Provenance` ne contient plus la contradiction entre la sous-section 3 et la sous-section 7.
  - **Preuve** : test d'intégration `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac8_r8_report_934d3254004b_exact_regression_verification`.

- **AC9 — Alignement des compteurs d'actions dans `report_history.json` (FR-04, NFR-3)** :
  - **Étant donné** un `ReportClaimRegistry` comprenant `3` claims `SCENARIO_HYPOTHESIS` à l'état `VERIFIED` et `2` claims `asserted_as_action=True` déclassés à l'état `UNSUPPORTED` (`verified_action_claims == 0`),
  - **Quand** l'entrée de `report_history.json` est construite à l'issue de la génération,
  - **Alors** `verified_action_claims_count` vaut `0` (et non `3`) et `asserted_action_claims_count` vaut `2`.
  - **Preuve** : test unitaire `backend/tests/test_story_015_3_quality_gate_and_provenance.py::test_ac9_report_history_counts_only_verified_social_actions`.

- **AC10 — Zéro régression sur le filet de tests existant et conformité linter (NFR-1, C8)** :
  - **Étant donné** l'ensemble de la suite de tests backend et frontend du dépôt,
  - **Quand** on exécute `pytest`, `ruff check`, `pnpm --dir frontend test` et `validate_plans.py`,
  - **Alors** `100 %` des tests existants (`2 121` tests backend + `43` tests frontend) ainsi que les nouveaux tests de `test_story_015_3_quality_gate_and_provenance.py` passent au vert avec `0` erreur Ruff et `0` erreur de validation de plan.
  - **Preuve** : exécution complète de la suite de tests consignée dans les Notes de développement.

---

## Définition de fini

- [x] Rôle structurel `section_role: Optional[str] = None` implémenté sur [`ReportSection`](../../../backend/app/services/report_agent.py) (`to_dict`, `from_dict`), restauré dans [`ReportManager.get_report`](../../../backend/app/services/report_agent.py) et propagé dans `PLAN_SYSTEM_PROMPT`, `_get_default_outline` et `plan_outline`.
- [x] Contrôle `QualityCategory.LIMITATIONS_SECTION` de [`ReportQualityGate.evaluate_report`](../../../backend/app/services/report_quality_gate.py) mis à jour pour valider prioritairement `section_role == "limitations"` (avec vérification de longueur `>= 50` caractères et de pertinence lexicale) tout en assurant le repli rétrocompatible `v1`.
- [x] Contrôle `QualityCategory.CLAIM_VERIFICATION` de [`ReportQualityGate.evaluate_report`](../../../backend/app/services/report_quality_gate.py) mis à jour : calcul de `asserted_actions` via `c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION or getattr(c, "asserted_as_action", False)`, élimination de l'angle mort « rapport conceptuel » quand `asserted_actions` est non vide et déclassé, filet `_markdown_alleges_simulated_actions` quand `len(asserted_actions) == 0`, et durcissement `\b` de `_ADOPTION_CLAIM_RE`.
- [x] Sous-section 3 et sous-section 7 de [`ReportAgent.build_sources_provenance_section`](../../../backend/app/services/report_agent.py) unifiées sur la même instance `ReportClaimRegistry`, suppression de la phrase statique inconditionnelle sur la règle anti-affabulation et remplacement par `_format_anti_affabulation_status(registry)` 100 % calculé.
- [x] Compteurs `verified_action_claims_count` et `asserted_action_claims_count` alignés sur `claims_registry.verified_action_claims` / `asserted_action_claims` dans [`ReportAgent.generate_report`](../../../backend/app/services/report_agent.py).
- [x] Fichier de tests dédié [`backend/tests/test_story_015_3_quality_gate_and_provenance.py`](../../../backend/tests/test_story_015_3_quality_gate_and_provenance.py) créé et couvrant `AC1` à `AC9` (dont le test de régression R8 `report_934d3254004b`).
- [x] Suite complète de tests backend + frontend verte, `ruff check` propre et `validate_plans.py` au vert.
- [x] Story passée à l'état `review` et agrégats de suivi (`epic-015.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`) synchronisés.

---

## Tâches

- [x] **Tâche 1 — Implémenter le contrat `ReportSection.section_role` et son attribution dans `ReportAgent` (`AC4`)** :
  - Dans [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) :
    - Étendre `ReportSection` (`:498-515`) avec `section_role: Optional[str] = None`, normaliser la valeur (`overview`, `analysis`, `limitations`, `recommendations` ou `None`), mettre à jour `to_dict()` et ajouter `from_dict(cls, data: Dict[str, Any]) -> "ReportSection"`.
    - Mettre à jour `ReportManager.get_report` (`:5051-5055`) pour instancier chaque section via `ReportSection.from_dict(s)`.
    - Mettre à jour `PLAN_SYSTEM_PROMPT` (`:700-712`), `_get_default_outline` (`:1098-1130`) et `plan_outline` (`:2080-2172`) pour demander, inférer par marqueurs structurels élargis (`verrou`, `blocage`, `frein`, `objection`, `limite`, `contradiction`, `réserve`, `refus`, `risque`, etc.) ou injecter `section_role="limitations"` lorsque `has_objections` est vrai.

- [x] **Tâche 2 — Mettre à jour le Contrôle 4 (`LIMITATIONS_SECTION`) dans `ReportQualityGate` (`AC5`, `AC8`)** :
  - Dans [`backend/app/services/report_quality_gate.py`](../../../backend/app/services/report_quality_gate.py) (`:413-458`) :
    - Structurer la logique dans `evaluate_report` qui :
      1. inspecte d'abord les sections de `outline` ayant `section_role == "limitations"`, retrouve leur bloc `## <title>` dans `report_markdown` et vérifie `len(body.strip()) >= 50` ainsi que la présence d'un marqueur lexical de `_LIMITATIONS_CONTENT_RE` ;
      2. en repli rétrocompatible (`v1` sans `section_role`), inspecte toutes les sections `## ...` du Markdown (hors `## Sources & Provenance`) via `_LIMITATIONS_HEADING_RE` + `len(body.strip()) >= 50` + `_LIMITATIONS_CONTENT_RE` ;
      3. renseigne `"has_rejections_or_objections"`, `"limitations_heading_present"`, `"limitations_role_matched"` et `"matched_section_title"` dans `details`.

- [x] **Tâche 3 — Fermer l'angle mort « rapport conceptuel » et durcir le Contrôle 5 (`CLAIM_VERIFICATION`) dans `ReportQualityGate` (`AC1`, `AC2`, `AC3`, `AC6`, `AC8`)** :
  - Dans [`backend/app/services/report_quality_gate.py`](../../../backend/app/services/report_quality_gate.py) (`:494-730`) :
    - Calculer `asserted_actions`, `strict_action_claims`, `downgraded_action_claims` et `verified_action_claims` en s'appuyant sur `c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION or getattr(c, "asserted_as_action", False)`.
    - Calculer `action_ratio = len(verified_action_claims) / len(asserted_actions)` lorsque `asserted_actions` est non vide.
    - Faire échouer en `QualityStatus.FAILED` (`r6_anomaly_detected=True`) tout rapport ayant `len(asserted_actions) > 0` et `len(verified_action_claims) == 0`, ou `action_ratio < 0.50`.
    - Implémenter `_markdown_alleges_simulated_actions(report_markdown: str) -> bool` et faire échouer en `QualityStatus.FAILED` (`unparseable_action_claims=True`) tout rapport où `len(asserted_actions) == 0` mais dont le Markdown narre des actions simulées hors négations pures.
    - Remplacer la détection d'adoption par sous-chaîne (`:528-534`) par `_ADOPTION_CLAIM_RE` à frontières de mots `\b` avec garde de négation et vérification de `adopted_members`.

- [x] **Tâche 4 — Rendre la sous-section 3 de `## Sources & Provenance` 100 % calculée et aligner `report_history.json` (`AC7`, `AC8`, `AC9`)** :
  - Dans [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) :
    - Dans `build_sources_provenance_section` (`:3295-3457`), charger `registry` une seule fois en amont de la sous-section 3.
    - Remplacer le littéral statique de `:3321` par un libellé 100 % calculé depuis `registry` (`asserted_action_claims`, `verified_action_claims`).
    - Ajouter dans la sous-section 7 (`:3441-3453`) les compteurs explicites `Actions sociales affirmées (\`asserted_as_action\`)` et `Actions sociales vérifiées (\`OBSERVED_SOCIAL_ACTION\` + \`VERIFIED\`)`.
    - Dans `generate_report` (`:3009-3015`), utiliser `claims_registry.verified_action_claims` pour `verified_action_claims_count` et ajouter `asserted_action_claims_count`.

- [x] **Tâche 5 — Écrire la suite de tests hermétiques `backend/tests/test_story_015_3_quality_gate_and_provenance.py` (`AC1` à `AC9`)** :
  - Créer [`backend/tests/test_story_015_3_quality_gate_and_provenance.py`](../../../backend/tests/test_story_015_3_quality_gate_and_provenance.py) contenant les tests nommés dans `AC1` à `AC9`, y compris la reproduction fidèle de l'anomalie R8 (`report_934d3254004b`).

- [x] **Tâche 6 — Vérifier le filet de non-régression complet et mettre à jour la documentation de suivi (`AC10`)** :
  - Exécuter `pytest`, `ruff check`, `pnpm --dir frontend test` et `validate_plans.py`.
  - Consigner les preuves d'exécution dans `## Notes de développement`, passer la story en `review` et mettre à jour `epic-015.md`, `sprint-status.yaml`, `STATUS.md` et `AGENTS.md`.

---

## Notes de développement

### 29 octobre 2026 — Implémentation de la Story 015-3

1. **Contrat structurel `ReportSection.section_role` (`AC4`)** :
   - Ajout du champ `section_role: Optional[str] = None` sur `ReportSection` dans `backend/app/services/report_agent.py` avec normalisation `str.strip().lower()` dans `__post_init__`.
   - Méthodes `to_dict()` et `from_dict(cls, data)` garantissant la sérialisation/désérialisation rétrocompatible (les plans `v1` sans clé `section_role` sont lus avec `section_role=None`).
   - `ReportManager.get_report` mis à jour pour instancier les sections via `ReportSection.from_dict(s)`.
   - `_get_default_outline` mis à jour pour injecter les trois rôles structurels canoniques : `"overview"`, `"analysis"`, `"limitations"`.
   - `PLAN_SYSTEM_PROMPT` documente le champ optionnel `section_role` et ordonne d'assurer la présence d'au moins une section `section_role="limitations"` dès que des réserves ou refus existent.
   - `plan_outline` inspecte les sections générées par le LLM, lit `section_role` et, si `has_objections` est vrai alors qu'aucune section n'a le rôle `"limitations"`, recherche par marqueurs structurels élargis (verrous, blocages, freins, refus, réserves, limites, risques) pour lui attribuer `section_role="limitations"`, ou injecte la section dédiée canonique avec ce rôle.

2. **Validation structurelle `QualityCategory.LIMITATIONS_SECTION` (`AC5`, `AC8`)** :
   - Dans `backend/app/services/report_quality_gate.py` :
     - Voie primaire : identification de la section de `outline` avec `section_role == "limitations"`, recherche de son en-tête `## <title>` dans `report_markdown`, vérification d'un corps de section `>= 50` caractères et d'une pertinence lexicale via `_LIMITATIONS_CONTENT_RE`.
     - Voie de repli `v1` : parcours des en-têtes `## ` du Markdown (hors `## Sources & Provenance`) avec matching d'intitulé via les chaînes historiques ou `_LIMITATIONS_HEADING_RE`, et vérification de la longueur `>= 50` caractères et de `_LIMITATIONS_CONTENT_RE`.
     - Exposition dans `details` de `"limitations_role_matched"`, `"matched_section_title"` aux côtés de `"limitations_heading_present"` et `"has_rejections_or_objections"`.

3. **Fermeture de l'angle mort « rapport conceptuel » et durcissement de `CLAIM_VERIFICATION` (`AC1`, `AC2`, `AC3`, `AC6`, `AC8`)** :
   - Calcul de `asserted_actions` : rassemble les `OBSERVED_SOCIAL_ACTION` et les affirmations déclassées ayant `asserted_as_action=True`.
   - Calcul de `action_ratio = len(verified_action_claims) / len(asserted_actions)`.
   - Quand `len(asserted_actions) > 0` et `len(verified_action_claims) == 0` : émission systématique de `QualityStatus.FAILED` (`r6_anomaly_detected=True`), interdisant à un rapport dont toutes les actions ont été déclassées d'obtenir un simple `WARNING`.
   - Quand `len(asserted_actions) == 0` : appel à `_markdown_alleges_simulated_actions(report_markdown)` qui inspecte le Markdown hors `## Sources & Provenance` et hors citations. Si des actions simulées exécutées sont alléguées, le contrôle échoue en `QualityStatus.FAILED` (`unparseable_action_claims=True`). Sinon, le statut `QualityStatus.WARNING` (« Rapport conceptuel ») est maintenu.
   - Durcissement de la détection d'affabulation d'adoption via `_ADOPTION_CLAIM_RE` à frontières de mots `\b` et garde de négation `_NEGATION_GUARD_RE`, éliminant les faux positifs sur `signal`, `souligne`, `signifie`.

4. **Section `## Sources & Provenance` 100 % calculée et alignement de l'historique (`AC7`, `AC8`, `AC9`)** :
   - Résolution unique de `registry` en amont de la sous-section 3 dans `ReportAgent.build_sources_provenance_section`.
   - Suppression définitive de la phrase statique inconditionnelle de certification de la règle anti-affabulation. Remplacement par un libellé 100 % calculé depuis `registry.asserted_action_claims` et `registry.verified_action_claims`.
   - Sous-section 7 enrichie avec l'exposition explicite de `Actions sociales affirmées (asserted_as_action)` et `Actions sociales vérifiées (OBSERVED_SOCIAL_ACTION + VERIFIED)`.
   - Dans `ReportAgent.generate_report`, `verified_action_claims_count` et `asserted_action_claims_count` sont alimentés directement depuis `claims_registry.verified_action_claims` et `asserted_action_claims`.

5. **Filet de tests et non-régression (`AC10`)** :
   - Création de `backend/tests/test_story_015_3_quality_gate_and_provenance.py` (9 tests passants couvrant AC1 à AC9, dont la reproduction exacte de l'anomalie R8 `report_934d3254004b`).
   - Exécution complète de la suite backend : `2 130 passed, 1 warning in 211.82s` (filet élargi de 2 121 à 2 130 tests).
   - Exécution de la suite frontend : `43 passed, 0 failed in 170ms`.
   - Linter : `ruff check app/services/report_agent.py app/services/report_quality_gate.py tests/test_story_015_3_quality_gate_and_provenance.py` -> `All checks passed!`.
   - Validateur de plan : `python scripts/validate_plans.py` -> `✓ structure de planification valide — 15 epics, 73 fichier(s) de story`.

---

## Revue

### Review Findings

- [x] [Review][Patch] Utiliser persona_name au lieu de name, exiger le préfixe evt_* dans evidence_refs et détecter l'affabulation d'adoption quand adopted_count == 0 [backend/app/services/report_quality_gate.py:664-692]
- [x] [Review][Patch] Exiger le lexique de limites sur le corps de section dans la voie de validation par rôle et intégrer la locale chinoise zh (_LIMITATIONS_HEADING_RE, _LIMITATIONS_CONTENT_RE et plan_outline) [backend/app/services/report_quality_gate.py:34-41,527, backend/app/services/report_agent.py:2184-2195]
- [x] [Review][Patch] Assainir _extract_markdown_section_body sur les titres vides ou d'espaces et borner sur les titres Markdown # et ## [backend/app/services/report_quality_gate.py:491-510]
- [x] [Review][Patch] Durcir _markdown_alleges_simulated_actions face aux retours à la ligne, aux verbes pluriels ont et aux marqueurs temporels français [backend/app/services/report_quality_gate.py:58-92]
- [x] [Review][Patch] Extraire la fonction pure contractuelle _format_anti_affabulation_status et fiabiliser les décomptes contre les taux négatifs [backend/app/services/report_agent.py:3398-3434]
- [x] [Review][Patch] Documenter section_role parmi les clés JSON anglaises de plan_outline, normaliser les synonymes de rôles et doter ReportOutline de from_dict [backend/app/services/report_agent.py:538-550,2104]
- [x] [Review][Patch] Combler les angles morts de tests : test unitaire réel de plan_outline, persistance effective de report_history.json, test positif d'adoption vérifiée et fixture hermétique autonome R8 sans skip [backend/tests/test_story_015_3_quality_gate_and_provenance.py]
- [x] [Review][Patch] Nettoyer la duplication des sections de fin de story et synchroniser l'en-tête de epic-015.md [docs/plans/015-contrats-preuve-roles-et-ihm/story-015-3.md, docs/plans/015-contrats-preuve-roles-et-ihm/epic-015.md:3]

---

## Notes de complétion

### 29 octobre 2026 — Clôture de la Story 015-3 après revue BMAD

La story 015-3 a été validée à l'issue de la revue contradictoire BMAD à 4 couches (*Blind Hunter*, *Edge Case Hunter*, *Verification Gap Reviewer*, *Acceptance Auditor*).
Les 8 groupes de patchs identifiés ont été intégralement implémentés, testés et vérifiés :
1. **Correction d'adoption dans `ReportQualityGate`** : utilisation de `persona_name` (au lieu de l'attribut inexistant `name`), contrôle de présence d'un identifiant `evt_*` dans `evidence_refs` (D5) avec repli sur `m.observed_event_ids`, et détection d'affabulation d'adoption lorsque `adopted_count == 0` sur toute affirmation d'adoption vérifiée.
2. **Contrôle strict et support de la locale chinoise (`zh`) pour `LIMITATIONS_SECTION`** : exigence stricte du lexique de limites sur le corps de section (`_LIMITATIONS_CONTENT_RE.search(body)`), intégration des idéogrammes et racines chinoises (异议, 局限, 风险, 阻碍, 拒绝, 障碍) dans `_LIMITATIONS_HEADING_RE`, `_LIMITATIONS_CONTENT_RE` et `plan_outline`.
3. **Assainissement Markdown** : garde `title.strip()` et délimitation sur les titres de niveau 1 et 2 (`#` et `##`) dans `_extract_markdown_section_body`.
4. **Analyse narrative robuste** : intégration de l'auxiliaire pluriel français `ont`, des marqueurs temporels (« au cours de la simulation »), et tolérance aux paragraphes multi-lignes sans interférence des négations locales.
5. **Extraction pure de `_format_anti_affabulation_status`** : fonction pure de module avec protection contre tout taux négatif ou division par zéro.
6. **Contrat `section_role` et factory `ReportOutline`** : conservation des clés JSON obligatoirement en anglais avec `'section_role'`, normalisation des synonymes (`limites` $\to$ `limitations`) et implémentation de `ReportOutline.from_dict`.
7. **Comblement des angles morts de tests** : test unitaire réel de `agent.plan_outline` (attribution de rôle et anti-doublon), persistance effective de `report_history.json` via `ReportManager._append_to_history` et `_load_history`, test nominal d'adoption vérifiée par persona, et fixture autonome R8 sous `backend/tests/fixtures/r8_report_934d3254004b/` éliminant tout `pytest.skip` en CI.
8. **Documentation et agrégats** : nettoyage des sections dupliquées et alignement des statuts sur `done`.

**Résultats de qualification finale** :
- Backend : **2 130 tests passants** (0 échec, 1 warning tiers Pydantic)
- Frontend : **43 tests Node passants** (0 échec)
- Linter : `ruff check` 100 % propre
- Validation des plans : `validate_plans.py` valide (15 epics, 73 stories)
