# PRD — Epic 015 : Contrats de preuve de bout en bout, pertinence des rôles et ergonomie IHM de suivi

> **Statut** : Rédigé le 29 octobre 2026, à partir de l'audit du run R8 (`sim_7a1b02b8c092`, rapport `report_934d3254004b`), de la proposition externe [`docs/PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md`](../../PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md) et du contrôle visuel des étapes 3/5 et 4/5.
> **Dossier de plan** : `docs/plans/015-contrats-preuve-roles-et-ihm/`
> **Épic amont** : 014 (clos, 4/4 stories validées — 2 099 tests hôte + 43 tests Node frontend).

---

## 1. Résumé de décision

L'audit du run R8 (`sim_7a1b02b8c092` / `report_934d3254004b`, exécuté avec `deepseek-v4.1-flash`, effort demandé `high`) et l'inspection directe du code au `HEAD` montrent que l'architecture posée par les Epics 011 à 014 (`EvidencePack`, `ReportClaimRegistry`, `ProvenanceRegime`, `SimulationActionVerifier`, `CohortCoverageTable`, `ReportQualityGate`, `brief_consistency.py`) est saine, mais souffre de **courts-circuits précis aux coutures entre composants**, doublés de **deux régressions d'affichage IHM** aux étapes 3/5 et 4/5.

**Principe non négociable.** Comme dans l'ensemble du dépôt, le cas métier du run R8 est une **fixture de qualification** et jamais une dépendance métier : aucune constante, règle, nom d'entreprise, offre, tarif ou persona de ce cas ne doit apparaître dans le code applicatif ou les prompts globaux de MiroFish. Tous les invariants sont génériques et s'appliquent à n'importe quel sujet de simulation (crise de transport public, débat associatif sans transaction, lancement industriel ou logiciel).

**Décision d'ingénierie (KISS / DRY).** Ne **pas** recréer une couche parallèle de ledgers ou de moteurs de rendu (`EvidenceLedger`, `InterviewLedger`, `DocumentaryLedger`, `ReportRenderer`, `FactLedger` suggérés dans la proposition brute), qui dupliquerait l'existant. Corriger et enrichir chirurgicalement les contrats existants de bout en bout, puis qualifier en mode `replay_frozen` avant toute nouvelle simulation complète.

---

## 2. Constats vérifiés dans le code et les artefacts R8

Tous les faits ci-dessous ont été vérifiés ligne par ligne dans le code actuel et les artefacts de `report_934d3254004b` :

### 2.1 Écrasement du `provenance_regime` et aveuglement de l'extracteur d'actions (P0)

| Fait mesuré | Cause racine vérifiée dans le code |
|---|---|
| **165/165 claims** ont `provenance_regime: null` dans `report_claims.json` (alors que `limitations` porte bien `"Régime de provenance non établi (unknown)."`) | `ReportAgent.extract_claims_from_content` (`backend/app/services/report_agent.py:3584-3654`) calcule et affecte `provenance_regime`, **mais** `SimulationActionVerifier.verify_report_claim` (`backend/app/services/simulation_action_verifier.py:909-1340`) ré-instancie un nouvel objet `ReportClaim(...)` dans ses **11 points de `return`** sans passer `provenance_regime=claim.provenance_regime`. |
| **0 `OBSERVED_SOCIAL_ACTION`** et **83 `REPORTED_INTENTION`** extraits alors que la prose relate des publications, réponses et suivis | Dans `extract_claims_from_content` (`report_agent.py:3562-3572`), `elif any(k in text_lower for k in ("va", "veut", "compte", ...))` est évalué **avant** les verbes d'action par **sous-chaîne brute (`in`)** : `"va"` matche *travail*, *avaient*, *avant*, *valide*, *observation*, et `"compte"` matche *compte Twitter*, *compte tenu*, *rendre compte*. |
| Les actions affirmées mais non prouvées **disparaissent** du compteur d'actions et trompent `ReportQualityGate` | Lorsqu'une `OBSERVED_SOCIAL_ACTION` échoue à la réconciliation dans `verify_report_claim` (`simulation_action_verifier.py:1232-1243`), son `claim_kind` est écrasé en `REPORTED_INTENTION` sans conserver de trace `asserted_as_action`. Derrière, `ReportQualityGate.evaluate_report` (`report_quality_gate.py:494-502, 639-656`) voit `len(action_claims) == 0` et émet un simple `WARNING` (« Rapport conceptuel sans allégation d'actions observées ») au lieu d'échouer en `FAILED` (contournement involontaire de QA-08). |

### 2.2 Aplatissement des entretiens de rédaction dans `report_interviews.json` (P0)

| Fait mesuré | Cause racine vérifiée dans le code |
|---|---|
| `report_interviews.json` contient 4 entrées et 63 courts extraits aplatis sans lien répondant ↔ citation ↔ réponse complète | Dans `ReportAgent._execute_tool_impl` (`report_agent.py:1595-1610`), `_interview_records` stocke `subject`, `agents` (liste de noms) et `citations` (concaténation plate de `key_quotes`), sans identifiant stable par tour/répondant ni texte complet de réponse (`answer_text`). Impossible d'authentifier qu'une citation entre guillemets appartient bien à tel persona en entretien sans jamais la confondre avec un événement OASIS. |

### 2.3 Section « limites » rejetée sur titre littéral et reliquat statique dans « Sources & Provenance » (P0)

| Fait mesuré | Cause racine vérifiée dans le code |
|---|---|
| `quality_checks.json` échoue (`FAILED`) sur `limitations_section` alors que le rapport consacre toute sa section 3 aux blocages et refus (`## Les verrous réels et les leviers qui fonctionnent (ou pas)`) | `ReportQualityGate.evaluate_report` (`report_quality_gate.py:424-430`) teste uniquement 4 sous-chaînes de titres codées en dur FR/EN, sans identifiant ou rôle contractuel de section porté par `ReportOutline` / `ReportSection`. |
| Contradiction interne dans `## Sources & Provenance` : la sous-section 3 certifie la liaison de toutes les actions, tandis que la sous-section 7 affiche `0 affirmation portant evidence_refs` | La sous-section 7 ajoutée en Story 014-2 (`report_agent.py:3217-3272`) est bien calculée depuis le registre, mais la sous-section 3 (`report_agent.py:3137`) contient encore le littéral statique : *« Toute affirmation qualifiée d'action observée est reliée à un événement horodaté du run »*. |

### 2.4 Confusion entre éligibilité ontologique, participation au scénario, filtrage du prompt et dénominateur de cohorte (P0)

| Fait mesuré | Cause racine vérifiée dans le code |
|---|---|
| Des outils logiciels tiers, une institution et l'organisation étudiée sont incarnés comme comptes sociaux actifs (18/18 actifs) | `ActorClassifier` qualifie légitimement `organization -> eligible` au plan ontologique (`actor_classifier.py:40-79`), mais aucun contrat de **participation au scénario** ne distingue une organisation *actrice du débat* (ex. syndicat ou opérateur dans une grève) d'un outil/objet simplement *mentionné* ou de l'entité objet de l'étude. |
| **Corruption du prompt de planification par `[persona non admis]`** sur les noms d'offres, de domaines et de logiciels (visible sur l'étape 4/5 : `"[persona non admis] coûte 29 €"`, `"praticienne.[persona non admis]"`) | `_filter_simulation_requirement_for_report` (`backend/app/api/report.py:48-59`) passe à `filter_non_admitted_personas_from_text` **toutes** les entités de `actors.json` dont `eligibility_status != "eligible"` — ce qui inclut les produits, offres, domaines et concepts (`role != person`), qui ne sont **pas** des personas rejetés mais le vocabulaire factuel du sujet ! |
| `adoption_denominator = 11` dans `cohort_coverage.json` alors que la cible compte moins de prospects | `CohortCoverageTable.prospect_members` (`cohort_coverage.py:427-433`) procède par exclusion partielle (`NOT_APPLICABLE`, `FOUNDER`, `TEAM_MEMBER`, `INSTITUTION`), laissant entrer tous les `ScenarioRole.UNKNOWN` dans le dénominateur commercial. |

### 2.5 Divergences biographiques dans la prose finale et métadonnées d'exécution incomplètes (P1)

| Fait mesuré | Cause racine vérifiée dans le code |
|---|---|
| `brief_consistency.json` est `is_consistent: true`, mais le rapport final invente une ancienneté contradictoire avec la fiche de départ d'un persona | `audit_brief_persona_consistency` (`brief_consistency.py`) vérifie `brief ↔ fiches générées` à la préparation, mais aucun contrôle ne confronte les attributs factuels/chiffrés des fiches personas aux affirmations biographiques de la **prose finale** du rapport. |
| `git_commit: "unknown-git-commit"` et `simulation.time_horizon: null` dans `run_manifest.json` | Le conteneur Docker n'embarque pas `.git` (exclusion volontaire `.dockerignore`) et aucune variable `GIT_COMMIT` de build/runtime n'alimente `SimulationAuditService` en repli ; par ailleurs l'horizon temporel inféré depuis `brief.goal` (`extract_inferred_horizon`) est utilisé au calcul mais reste `null` dans l'export du manifeste. |

### 2.6 Défauts d'ergonomie et de télémétrie IHM aux étapes 3/5 et 4/5 (P1)

| Fait observé à l'écran | Cause racine vérifiée dans le code frontend/backend |
|---|---|
| **Étape 3/5 (`Step3Simulation.vue`)** : les 3 cartes (`Info Plaza`, `Topic Community`, `Mémoire du Graphe`) sont tassées, `0 min` casse sur 2 lignes, le compteur `ATTENTE 366` déborde hors de la bordure droite de la carte orange et touche directement le bouton `SYNCHRONISATION DU GRAPHE...` | Dans `frontend/src/components/Step3Simulation.vue:830-860, 952-1018`, `.control-bar` impose `height: 64px` fixe sans `flex-wrap` ni `gap` entre `.status-group` et `.action-controls`, et `.stat` n'impose pas `white-space: nowrap`. En vue `Scindé` (50 % de largeur), les 3 cartes et le bouton entrent en collision. |
| **Étape 4/5 (`Step4Report.vue`)** : pendant toute la génération (et en cas d'arrêt erreur ou de course en fin de run), les 5 indicateurs (`TOKENS CONSOMMÉS`, `DURÉE D'INFÉRENCE`, `TEMPS MURAL`, `COÛT ESTIMÉ`, `AFFIRMATIONS VÉRIFIÉES / TOTAL`) affichent tous **`indisponible`** | 1) `ReportAgent` ne persiste `usage.json` qu'à la toute fin (`report_agent.py:2795`), jamais au fil des phases/sections ; 2) `Step4Report.vue` (`:2716`, `:2560-2568`) n'appelle `loadCurrentTelemetry` qu'au montage initial (où `/usage` et `/claims` renvoient `404`) puis sur `report_complete` (jamais pendant le polling ni sur `error`) ; 3) `log_report_complete` (`:2841`) est émis **avant** `ReportManager.save_report` (`:2847`), créant une fenêtre de course `404` ; 4) un compteur non encore calculé pendant une génération active devrait afficher un état « en cours… » plutôt qu'« indisponible ». |

---

## 3. Objectifs et Non-objectifs

### Objectifs
1. **Zéro perte de régime ni d'allégation d'action** entre l'extraction, la vérification (`SimulationActionVerifier`), la section « Sources & Provenance » et `ReportQualityGate`.
2. **Authentification déterministe des entretiens de rédaction** par répondant et réponse complète (`report_interviews.json`), sans jamais promouvoir un entretien en événement OASIS.
3. **Pertinence scénaristique des acteurs et pureté du prompt** : distinguer capacité ontologique d'agir, participation au scénario et éligibilité à une conversion ; ne jamais caviarder des produits/concepts en `[persona non admis]`.
4. **Ergonomie irréprochable du suivi IHM (Step 3 & Step 4)** : cartes aérées et sans débordement en vue scindée comme établie, télémétrie vivante pendant la rédaction et exacte dès la complétion.
5. **Contrôle biographique aval et reproductibilité** : détecter dans la prose finale les contradictions biographiques chiffrées vis-à-vis des fiches, tracer `git_commit` et `time_horizon` effectif dans Docker, et qualifier sur R8 en `replay_frozen`.

### Non-objectifs
- Créer des doublons d'architecture (`EvidenceLedger`, `ReportRenderer`, `FactLedger` RDF) parallèles aux modèles existants.
- Remplacer la rédaction Markdown des sections ReACT par une génération intégrale en JSON brut qui casserait la fluidité analytique et `SectionCompletionGuard`.
- Coder la moindre règle, constante ou heuristique spécifique au domaine d'une fixture de test.
- Changer de fournisseur ou de modèle LLM par défaut avant d'avoir stabilisé et mesuré les garde-fous en `replay_frozen`.

---

## 4. Exigences Fonctionnelles (FR)

| ID | Exigence | Priorité |
|---|---|---|
| FR-01 | `SimulationActionVerifier.verify_report_claim` préserve intégralement `provenance_regime` sur tous ses chemins de retour, et l'extracteur distingue actions observées et intentions par frontières lexicales strictes sans faux positifs par sous-chaîne (`"va"`, `"compte"`) | P0 |
| FR-02 | Toute affirmation extraite comme action observée puis déclassée faute de preuve conserve un marqueur explicite (`asserted_as_action = True`) et vérifie que l'`event_id` appartient bien à l'acteur résolu | P0 |
| FR-03 | `report_interviews.json` enregistre chaque réponse structurée par entretien, tour et répondant (`interview_id`, `turn_index`, `agent_id`, `persona_name`, `question`, `answer_text`, `key_quotes`, `mode`), permettant de vérifier les citations d'entretien sans les promouvoir en actions OASIS | P0 |
| FR-04 | `ReportQualityGate` échoue (`FAILED`) si des actions affirmées sont toutes non vérifiées (même après déclassement), valide la section `limitations` via un contrat structurel du plan (`section_role`) et non seulement 4 titres littéraux, et `Sources & Provenance` conditionne 100 % de ses affirmations de couverture au registre réel | P0 |
| FR-05 | La sélection des acteurs sépare l'éligibilité ontologique de la participation au scénario ; le filtre de `simulation_requirement` ne masque **que** les personas écartés (jamais les produits, offres, domaines ou concepts) ; le dénominateur de conversion procède par inclusion positive (`conversion_eligible` / `PROSPECT`) | P0 |
| FR-06 | L'IHM Step 3 affiche les cartes `Info Plaza`, `Topic Community` et `Mémoire du Graphe` sans débordement ni collision avec le bouton d'action (y compris en mode `Scindé`), et l'IHM Step 4 rafraîchit en continu la télémétrie d'usage pendant la génération puis à tout état terminal (`completed`, `failed_validation`, `error`) | P1 |
| FR-07 | Un contrôle déterministe confronte les faits biographiques chiffrés de la prose finale aux fiches personas admises (sans bloquer les divergences d'opinion), et `run_manifest.json` expose le `git_commit` injecté au conteneur ainsi que le `time_horizon` effectif (explicite ou inféré avec origine) | P1 |
| FR-08 | Un banc de qualification rejouable valide les scénarios de recette sur la fixture R8 (`replay_frozen`) et sur au moins trois scénarios synthétiques multi-domaines (logiciel, débat associatif sans vente, crise de transport avec institution active) | P1 |

---

## 5. Exigences Non Fonctionnelles (NFR)

| ID | Exigence |
|---|---|
| NFR-1 | **Zéro régression** : les 2 099 tests backend hôte et 43 tests Node frontend restent intégralement verts ; compatibilité ascendante de lecture sur les rapports historiques (`v1`) |
| NFR-2 | **Généricité absolue** : zéro nom d'entreprise, d'offre, de domaine, de tarif ou de persona issu d'une fixture dans `backend/app/`, `frontend/src/` ou `locales/` |
| NFR-3 | **KISS & DRY** : enrichissement des modèles et services existants (`ReportClaim`, `SimulationActionVerifier`, `ReportQualityGate`, `CohortCoverageTable`, `brief_consistency.py`), zéro couche dupliquée |
| NFR-4 | **Zéro fuite de secret** : ni `report_interviews.json`, ni `usage.json` incrémental, ni `run_manifest.json` n'exposent de clé API, d'URL privée ou de prompt système interne |
| NFR-5 | **Honnêteté épistémique et télémétrique** : distinction stricte entre « en cours… » (calcul non encore échu), « gratuit / non tarifé » et « indisponible » ; aucune certification textuelle non prouvée par le registre |
| NFR-6 | **Parité i18n et responsive** : parité 100 % des clés et variables `{var}` entre `locales/fr.json`, `locales/en.json` et `locales/zh.json` ; rendu propre en mode `Graphe`, `Scindé` et `Établi` |

---

## 6. Critères de sortie de l'Epic (C1 à C8)

| C | Critère falsifiable |
|---|---|
| C1 | **0 perte de `provenance_regime`** à la traversée de `verify_report_claim`, **0 faux positif par sous-chaîne** (`"va"`, `"compte"`), et toute action affirmée non prouvée reste comptabilisée comme action affirmée non vérifiée (`asserted_as_action=True`) |
| C2 | **100 % des réponses d'entretien** de rédaction sont tracées par répondant et texte complet dans `report_interviews.json` ; une citation verbatim d'entretien est authentifiée comme `INTERVIEW` (auteur vérifié) et jamais comptée comme action OASIS |
| C3 | `ReportQualityGate` ne classe plus jamais en « rapport conceptuel (`WARNING`) » un rapport contenant des allégations d'actions non vérifiées ; la section `limitations` est reconnue par rôle structurel (`section_role="limitations"`) ; `Sources & Provenance` ne contient plus aucun littéral statique de certification |
| C4 | Aucun produit, offre, domaine ou concept (`role != person`) n'est remplacé par `[persona non admis]` dans le contexte du rapport ; les organisations/outils non participants ne sont pas instanciés par défaut en agents sociaux sauf pertinence scénaristique ; le dénominateur d'adoption repose sur l'inclusion positive |
| C5 | Sur Step 3 (`Scindé` ≥ 1280px bureau et `Établi`), 0 texte débordant hors des 3 cartes de statut et espacement ≥ 12px avec le bouton d'action ; sur Step 4, les tokens et durées se mettent à jour en cours de génération et s'affichent sans `404` en fin de run |
| C6 | Une contradiction biographique chiffrée entre la fiche d'un persona et la prose finale est détectée sans bloquer les opinions ; `git_commit` et `time_horizon` effectif sont renseignés dans `run_manifest.json` sous Docker |
| C7 | Qualification validée en `replay_frozen` sur R8 et sur 3 scénarios synthétiques multi-domaines (vente logicielle, débat associatif sans conversion, perturbation de transport avec institution active) |
| C8 | Filet de tests enrichi et 100 % vert (backend `pytest`, frontend `node --test`, `ruff check`, `validate_plans.py`, parité i18n) |

---

## 7. Documents de référence

- [`architecture.md`](architecture.md) — choix techniques détaillés, contrats de données enrichis et flux IHM/backend
- [`epic-015.md`](epic-015.md) — hub de l'epic, découpage en 6 stories et dépendances
- [`docs/PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md`](../../PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md) — audit externe R8 à l'origine du chantier
- [`docs/plans/014-integrite-preuves-redaction/epic-014.md`](../014-integrite-preuves-redaction/epic-014.md) — Epic 014 clos
- [`AGENTS.md`](../../../AGENTS.md) — constitution du dépôt

