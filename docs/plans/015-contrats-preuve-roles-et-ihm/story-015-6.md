---
id: "015-6"
epic: "015"
titre: "Cohérence biographique fiches ↔ prose finale, métadonnées Docker (git_commit, horizon) et qualification multi-domaines"
statut: in-progress
created: 2026-10-30
updated: 2026-10-30
auteur: "Agent BMAD (rediger-story)"
format: "2"
---

# Story 015-6 : Cohérence biographique fiches ↔ prose finale, métadonnées Docker (`git_commit`, horizon) et qualification multi-domaines

> **Epic parent :** [EPIC-015 — Contrats de preuve, gouvernance des rôles et ergonomie IHM Step 3/4](epic-015.md)
> **Exigences couvertes :** `FR-07`, `FR-08` · `NFR-1`, `NFR-2`, `NFR-3`, `NFR-4`, `NFR-5`, `NFR-6` · Critères de sortie **C6**, **C7**, **C8**
> **Scénarios d'acceptation de l'audit source couverts :** `AT-11`, `AT-15`, `AT-16`, `AT-17`, `AT-18`, `AT-20` (et qualification de bout en bout de `AT-01` à `AT-20` en conjonction avec `015-1` à `015-5`)
> **Dépendances amont :** Stories [015-1](story-015-1.md) (`done`), [015-2](story-015-2.md) (`done`), [015-3](story-015-3.md) (`done`), [015-4](story-015-4.md) (`done`) et [015-5](story-015-5.md) (`done`)
> **Stories aval impactées :** Aucune (story de clôture et de qualification finale de l'Epic 015)

## Contexte et objectif

Les stories `015-1` à `015-5` ont résolu les ruptures de contrat sur le régime de provenance (`ProvenanceRegime`), l'authentification des citations d'entretien (`report_interviews.json` v2), la barrière `ReportQualityGate` sur les rapports sans actions affirmées, la gouvernance des rôles (`ParticipationPolicy` et filtre `[persona non admis]`) ainsi que l'ergonomie IHM des étapes 3/5 et 4/5. Il reste trois coutures de contrat révélées par l'audit externe du run R8 (`sim_7a1b02b8c092` / `report_934d3254004b`) et la qualification de bout en bout de l'Epic 015 :

1. **Angle mort aval sur la cohérence biographique entre fiches personas et prose finale (`FR-07`, C6, `AT-11`)** :
   - Lors de la préparation de la simulation (Step 2), `audit_brief_persona_consistency()` dans [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py#L469-L561) vérifie uniquement la cohérence amont `brief ↔ fiches personas` sur les épisodes monétaires. Sur le run R8, [`backend/uploads/simulations/sim_7a1b02b8c092/brief_consistency.json`](../../../backend/uploads/simulations/sim_7a1b02b8c092/brief_consistency.json#L1-L55) affiche `"is_consistent": true` et `"contradictions": []`, et ce même fichier est recopié tel quel dans le paquet d'audit du rapport par [`SimulationAuditService.gather_audit_files()`](../../../backend/app/services/simulation_audit_service.py#L254-L263).
   - Or, au moment de la rédaction finale (Step 4), la prose générée dans [`backend/uploads/reports/report_934d3254004b/full_report.md`](../../../backend/uploads/reports/report_934d3254004b/full_report.md#L34) affirme : *« **Sylvie**, pourtant installée depuis 17 ans avec un carnet plein, ajourne pour une raison inverse et contre-intuitive »*, alors que la fiche canonique de Sylvie dans [`backend/uploads/simulations/sim_7a1b02b8c092/reddit_profiles.json`](../../../backend/uploads/simulations/sim_7a1b02b8c092/reddit_profiles.json#L315) stipule explicitement : *« Sylvie Delaunay, 52 ans, naturopathe et réflexologue plantaire installée depuis deux ans et demi à Angers »*.
   - Aucun contrôle aval ne compare les attributs biographiques chiffrés (durée d'installation/exercice en années ou mois, montants biographiques spécifiques) attribués à un persona dans la prose finale du rapport contre sa fiche canonique (`reddit_profiles.json` / `profiles.json`).

2. **Métadonnées de reproductibilité incomplètes dans le paquet d'audit (`FR-08`, C7, `AT-15`, `AT-16`)** :
   - Sur le run R8 exécuté sous conteneur Docker, [`backend/uploads/reports/report_934d3254004b/run_manifest.json`](../../../backend/uploads/reports/report_934d3254004b/run_manifest.json#L5) expose `"git_commit": "unknown-git-commit"` et `"time_horizon": null` (ligne 21).
   - Côté Docker, [`backend/Dockerfile`](../../../backend/Dockerfile#L1-L44) ne déclare ni `ARG GIT_COMMIT=unknown-git-commit` ni `ENV GIT_COMMIT=${GIT_COMMIT}`, et [`docker-compose.yml`](../../../docker-compose.yml#L34-L79) ne transmet pas `GIT_COMMIT` au build ni à l'environnement du conteneur `backend` (qui ne contient pas `.git/`).
   - Côté horizon temporel, [`SimulationAuditService.build_run_manifest()`](../../../backend/app/services/simulation_audit_service.py#L102-L117) tente de lire `simulation_brief.json` sur disque ; mais lorsque ce fichier est absent du dossier de simulation (cas de R8 où le brief ou l'exigence de simulation réside dans le projet ou dans `simulation_config.json` / `state.json`), `time_horizon` reste `None`, sans repli sur le brief du projet ni sur `simulation_requirement` ("Les 72 premières heures..."), et sans exposer les métadonnées de traçabilité `time_horizon_is_inferred` et `time_horizon_source`.

3. **Qualification globale multi-domaines et rejeu déterministe R8 (`C1`–`C8`, `AT-01`–`AT-20`)** :
   - L'Epic 015 doit être qualifié de bout en bout par un banc d'orchestration autonome `backend/scripts/verifier_qualification_epic_015.py` et un rapport formel `docs/plans/015-contrats-preuve-roles-et-ihm/rapport-qualification-epic-015.md` démontrant :
     - la résolution des défauts R8 en mode `replay_frozen` déterministe (sans appel LLM payant) sur la fixture R8 (`sim_7a1b02b8c092` / `report_934d3254004b`) ;
     - la généricité inter-domaines (`NFR-2`, `AT-17`, `AT-18`, `AT-19`, `AT-20`) sur 3 scénarios synthétiques couvrant des domaines distincts (lancement logiciel commercial, débat associatif local à conversion nulle, grève de transport public avec organisation institutionnelle active) ;
     - l'absence totale de constantes ou règles codées en dur propres à la fixture d'audit dans le code de production (`backend/app/`, `frontend/src/`, `locales/`).

### Périmètre inclus

- **Sous-système 1 — Contrôle biographique aval `fiches personas ↔ prose finale` (`FR-07`, C6, `AT-11`)** :
  - Extension de [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py) avec l'extraction déterministe des attributs biographiques d'ancienneté/installation (`PracticeDurationAttribute` : durée normalisée en années flottantes, contexte d'installation/exercice, extrait source) en complément des épisodes monétaires (`BiographicalEpisode`) depuis les fiches personas admises (`reddit_profiles.json`, `profiles.json`, `twitter_profiles.json`).
  - Ajout d'une fonction pure `audit_prose_persona_consistency(markdown_content, profiles, allowed_names=None)` et intégration dans [`SimulationActionVerifier.verify_report_claim()`](../../../backend/app/services/simulation_action_verifier.py#L1305-L1840) et [`ReportAgent.audit_and_save_report_claims()`](../../../backend/app/services/report_agent.py#L4073-L4267) :
    - lorsqu'une affirmation du rapport attribuée à un persona admis énonce une durée d'installation/exercice en contradiction manifeste avec la durée d'installation de sa fiche canonique (écart relatif et absolu incompatible, ex. « installée depuis 17 ans » vs « installée depuis deux ans et demi »), ou attribue à un persona $B$ un épisode biographique chiffré exclusif du persona $A$, la claim est marquée `VerificationStatus.CONTRADICTED` avec une limitation explicite portant le code `PERSONA_BIOGRAPHY_CONTRADICTION` ;
    - enrichissement de `brief_consistency.json` côté rapport (`uploads/reports/<report_id>/brief_consistency.json`) et dans [`SimulationAuditService.gather_audit_files()`](../../../backend/app/services/simulation_audit_service.py#L254-L263) avec une section `"prose_consistency"` (liste `prose_contradictions`, `prose_is_consistent`, attributs d'ancienneté extraits par profil) sans écraser le diagnostic amont `brief ↔ fiches` ;
    - distinction stricte entre contradiction biographique factuelle (`PERSONA_BIOGRAPHY_CONTRADICTION`) et divergence d'opinion, d'attitude ou d'intention (`AT-11`) : un changement d'avis ou une réserve exprimée en simulation ou en entretien ne déclenche jamais `PERSONA_BIOGRAPHY_CONTRADICTION`.
- **Sous-système 2 — Métadonnées de reproductibilité Docker et horizon temporel (`FR-08`, C7, `AT-15`, `AT-16`)** :
  - Ajout de `ARG GIT_COMMIT=unknown-git-commit` et `ENV GIT_COMMIT=${GIT_COMMIT}` dans [`backend/Dockerfile`](../../../backend/Dockerfile) et câblage de `build.args.GIT_COMMIT: "${GIT_COMMIT:-unknown-git-commit}"` + `environment.GIT_COMMIT: "${GIT_COMMIT:-}"` dans [`docker-compose.yml`](../../../docker-compose.yml).
  - Durcissement de [`SimulationAuditService._get_git_commit()`](../../../backend/app/services/simulation_audit_service.py#L51-L70) pour ignorer les valeurs vides ou égales à la sentinelle `"unknown-git-commit"` dans les variables d'environnement avant de tenter `git rev-parse --short=12 HEAD` (ou `HEAD`), et ne retomber sur `"unknown-git-commit"` qu'en dernier recours explicite.
  - Enrichissement de [`SimulationAuditService.build_run_manifest()`](../../../backend/app/services/simulation_audit_service.py#L73-L234) et [`gather_audit_files()`](../../../backend/app/services/simulation_audit_service.py#L237-L445) :
    - résolution en cascade de l'horizon temporel : (1) `simulation_brief.json` du dossier simulation, (2) `project.get_brief()` via `SimulationManager.get_simulation()`, (3) extraction déterministe `extract_inferred_horizon()` depuis le `goal` du brief, le `simulation_requirement` de l'état de simulation ou de `simulation_config.json`, ou le titre/résumé du rapport ;
    - exposition dans `run_manifest["simulation"]` de `time_horizon`, `time_horizon_is_inferred: bool` et `time_horizon_source: str` (`"explicit_brief"`, `"inferred_from_goal"`, `"inferred_from_simulation_requirement"`, `"inferred_from_report"`, ou `"unresolved"`) ;
    - enrichissement de `simulation_brief.json` dans le paquet d'audit (`gather_audit_files()`) avec `time_horizon`, `time_horizon_is_inferred` et `time_horizon_source` lorsque l'horizon a été inféré.
- **Sous-système 3 — Banc de qualification globale Epic 015 (`C1`–`C8`, `AT-01`–`AT-20`)** :
  - Création du script autonome [`backend/scripts/verifier_qualification_epic_015.py`](../../../backend/scripts/verifier_qualification_epic_015.py) évaluant de bout en bout les critères **C1 à C8** et les scénarios **AT-01 à AT-20** (audit déterministe de la fixture R8 + 3 scénarios synthétiques multi-domaines + scan AST/regex de généricité `NFR-2`) et générant le rapport formel [`docs/plans/015-contrats-preuve-roles-et-ihm/rapport-qualification-epic-015.md`](rapport-qualification-epic-015.md).
  - Création des tests unitaires et d'intégration hermétiques [`backend/tests/test_story_015_6_biography_and_qualification.py`](../../../backend/tests/test_story_015_6_biography_and_qualification.py).

### Hors périmètre

- Aucune modification des composants frontend Vue 3 (`Step3Simulation.vue` et `Step4Report.vue` ont été livrés et clos en Story `015-5`).
- Aucun appel LLM externe requis pour l'exécution des tests automatisés ni du mode par défaut du banc de qualification (`NFR-4`).
- Aucune modification des règles de classification d'intention/action (`015-1`), du schéma `report_interviews.json` v2 (`015-2`), de la porte `ReportQualityGate` (`015-3`) ni de `ParticipationPolicy` (`015-4`), qui sont uniquement vérifiés de bout en bout par le banc de qualification.

---

## Définition de prêt

- [x] L'epic parent [`epic-015.md`](epic-015.md), le [`prd.md`](prd.md) (`FR-07`, `FR-08`, `C6`–`C8`, `AT-11`, `AT-15`–`AT-20`) et [`architecture.md`](architecture.md) (§2.6) sont lus et alignés.
- [x] Les stories amont [`story-015-1.md`](story-015-1.md), [`story-015-2.md`](story-015-2.md), [`story-015-3.md`](story-015-3.md), [`story-015-4.md`](story-015-4.md) et [`story-015-5.md`](story-015-5.md) sont toutes à l'état `done`.
- [x] Les fichiers du cas réel R8 (`sim_7a1b02b8c092` / `report_934d3254004b`) et le code source de `brief_consistency.py`, `simulation_action_verifier.py`, `report_agent.py`, `simulation_audit_service.py`, `backend/Dockerfile` et `docker-compose.yml` ont été inspectés ligne par ligne.
- [x] Le point de départ des tests est mesuré et vert : **2 152 tests pytest backend** + **50 tests Node frontend** le 30 octobre 2026.

### Causes racines exactes dans le code actuel (vérifiées ligne par ligne)

- **RC-1 — `brief_consistency.py` ne contrôle que `brief ↔ fiches` en amont et ignore les durées d'installation ainsi que la prose finale du rapport** :
  - Dans [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py#L469-L561), `audit_brief_persona_consistency()` compare uniquement les épisodes monétaires (`_AMOUNT_RE`) entre le texte du brief et les fiches personas.
  - Il n'existe ni extracteur de durée d'installation/exercice professionnel (ex. `installée depuis deux ans et demi` vs `installée depuis 17 ans`), ni contrôleur aval comparant les affirmations attribuées à un persona dans `full_report.md` / `ReportClaim` aux faits biographiques de sa fiche (`reddit_profiles.json` / `profiles.json`).
  - Sur R8, la ligne 34 de [`backend/uploads/reports/report_934d3254004b/full_report.md`](../../../backend/uploads/reports/report_934d3254004b/full_report.md#L34) affirme : `- **Sylvie**, pourtant installée depuis 17 ans avec un carnet plein...`, en contradiction directe avec [`backend/uploads/simulations/sim_7a1b02b8c092/reddit_profiles.json`](../../../backend/uploads/simulations/sim_7a1b02b8c092/reddit_profiles.json#L315) (`Sylvie Delaunay, 52 ans, naturopathe et réflexologue plantaire installée depuis deux ans et demi à Angers`).
- **RC-2 — `SimulationAuditService.gather_audit_files()` recopie `brief_consistency.json` amont sans évaluer la prose du rapport** :
  - Dans [`backend/app/services/simulation_audit_service.py`](../../../backend/app/services/simulation_audit_service.py#L254-L263), `gather_audit_files()` lit `uploads/simulations/<sim_id>/brief_consistency.json` (généré à l'étape 2 avant toute rédaction) et l'inclut tel quel dans le paquet ZIP d'audit du rapport, sans exécuter d'audit de cohérence sur `full_report.md`.
- **RC-3 — Absence de `GIT_COMMIT` dans `backend/Dockerfile` et `docker-compose.yml`, et résolution incomplète de `time_horizon` dans `SimulationAuditService`** :
  - [`backend/Dockerfile`](../../../backend/Dockerfile#L1-L44) ne définit pas `ARG GIT_COMMIT` / `ENV GIT_COMMIT`, et [`docker-compose.yml`](../../../docker-compose.yml#L34-L79) ne transmet pas `GIT_COMMIT` au service `backend`. En outre, [`SimulationAuditService._get_git_commit()`](../../../backend/app/services/simulation_audit_service.py#L54-L57) accepte toute chaîne non vide présente dans `os.environ.get("GIT_COMMIT")`, même si elle vaut la valeur par défaut `"unknown-git-commit"`, ce qui court-circuite le repli `git rev-parse HEAD` lorsque le dépôt `.git` est disponible.
  - Dans [`SimulationAuditService.build_run_manifest()`](../../../backend/app/services/simulation_audit_service.py#L102-L117), `time_horizon` n'est lu que depuis `uploads/simulations/<sim_id>/simulation_brief.json`. Si ce fichier n'existe pas sur disque (comme sur R8 où `uploads/simulations/sim_7a1b02b8c092/` contient `state.json`, `simulation_config.json`, `reddit_profiles.json`, mais pas `simulation_brief.json`), `time_horizon` reste `None` alors même que `state.json` et le titre du rapport mentionnent explicitement `72 heures` (`"Les 72 premières heures..."`). De plus, `time_horizon_is_inferred` et `time_horizon_source` ne sont pas exposés dans `run_manifest["simulation"]`.

### Invariants à préserver

- **Généricité absolue (`NFR-2`, C8, `AT-17`, `AT-18`)** : zéro identifiant ou nom propre de la fixture d'audit (`Keova`, `Menopulse`, `Simon`, `Nathalie`, `Sylvie`, `Florence`, `Émilie`, `Christine`, `Hélène`, `Martine`, `Marie-Claude`, `Sophie Jouan`, `Valérie Blandinières`, `Stripe`, `Wix`, `WordPress`, `CPAM`) dans `backend/app/`, `frontend/src/` et `locales/`. Les motifs d'extraction de durée d'exercice et de montants biographiques doivent reposer exclusivement sur des constructions grammaticales générales du français et de l'anglais.
- **Liberté d'opinion et d'évolution d'attitude (`AT-11`)** : le contrôle biographique aval ne sanctionne que les contradictions factuelles sur les attributs biographiques du profil (ancienneté d'installation/exercice, attribution croisée d'un épisode biographique chiffré). Un persona qui change d'avis, exprime un doute, refuse une offre ou nuance ses propos par rapport aux hypothèses de son profil ne doit **jamais** être marqué `CONTRADICTED` (`PERSONA_BIOGRAPHY_CONTRADICTION`).
- **Rétrocompatibilité de `brief_consistency.json` (`NFR-5`)** : les clés existantes de `brief_consistency.json` (`is_consistent`, `contradictions`, `diagnostics`) restent intactes pour ne casser aucun test de la Story `014-4` (`test_brief_consistency.py`). Les résultats du contrôle aval sur la prose sont exposés sous des clés additionnelles dédiées (`prose_is_consistent`, `prose_contradictions`, `diagnostics.practice_durations_by_profile`) et persistés dans le dossier du rapport (`uploads/reports/<report_id>/brief_consistency.json`).
- **Préservation du pipeline `verify_report_claim` (`015-1` à `015-4`)** : le contrôle biographique s'exécute sans altérer le `provenance_regime` (`INTERVIEW` reste `INTERVIEW`), ni promouvoir un entretien en `OBSERVED_SOCIAL_ACTION`, ni perturber les règles de silence (C7) ou de faits d'entreprise (QA-12).

### Références de documentation vérifiées

- PRD Epic 015 : [`docs/plans/015-contrats-preuve-roles-et-ihm/prd.md`](prd.md) (`FR-07`, `FR-08`, `NFR-1` à `NFR-6`, critères **C6**, **C7**, **C8**)
- Architecture Epic 015 : [`docs/plans/015-contrats-preuve-roles-et-ihm/architecture.md`](architecture.md) (§2.6 « Contrôle biographique aval, reproductibilité Docker et qualification »)
- Hub d'Epic : [`docs/plans/015-contrats-preuve-roles-et-ihm/epic-015.md`](epic-015.md) (Story `015-6`, critères C1 à C8)
- PRD d'audit externe R8 : [`docs/PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md`](../../PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md) (Constats #8, #11, #12 et scénarios `AT-01` à `AT-20`)
- Code d'ancrage vérifié :
  - [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py#L1-L634)
  - [`backend/app/services/simulation_action_verifier.py`](../../../backend/app/services/simulation_action_verifier.py#L1305-L1840)
  - [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py#L4073-L4267)
  - [`backend/app/services/simulation_audit_service.py`](../../../backend/app/services/simulation_audit_service.py#L51-L320)
  - [`backend/app/models/simulation_brief.py`](../../../backend/app/models/simulation_brief.py#L81-L162)
  - [`backend/Dockerfile`](../../../backend/Dockerfile#L1-L44)
  - [`docker-compose.yml`](../../../docker-compose.yml#L34-L79)

### Point de départ des tests (mesuré le 30 octobre 2026)

- **Backend pytest** : **2 152 tests passés**, 0 échec (`backend/.venv/bin/pytest`).
- **Frontend Node test runner** : **50 tests passés**, 0 échec (`pnpm --dir frontend test`).
- **Validateur de plans** : `backend/.venv/bin/python backend/scripts/validate_plans.py` vert (`OK — tous les fichiers de planification sont valides`).

### Décisions d'ingénierie de la story

- **D1 — Extraction déterministe des durées d'installation/exercice professionnel (`PracticeDurationAttribute`) dans `brief_consistency.py`** :
  - Ajouter un dataclass immuable `PracticeDurationAttribute(years: float, raw_value: str, context_kind: str, snippet: str)` dans [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py).
  - Supporter les nombres en chiffres et en toutes lettres (français : `un`/`une` à `trente`, demi-unités `et demi` = `+0.5`, ex. `deux ans et demi` $\rightarrow 2.5$ ans, `17 ans` $\rightarrow 17.0$ ans, `six mois` $\rightarrow 0.5$ an ; anglais : `one` à `thirty`, `two and a half years` $\rightarrow 2.5$).
  - Cibler strictement les syntagmes d'ancienneté d'installation ou d'exercice actuel de l'activité du persona :
    - FR : `(?:installée?|exerce|exercant|en\s+activité|en\s+libéral|pratique|cabinet\s+ouvert)\s+(?:à\s+[A-ZÀ-ÖØ-ß][\w\-]+\s+)?(?:en\s+libéral\s+)?depuis\s+(?:un\s+peu\s+plus\s+de\s+|environ\s+|près\s+de\s+)?(<durée>)\s*(ans?|années?|mois)` ;
    - EN : `(?:practicing|installed|in\s+practice|established|operating)\s+for\s+(?:over\s+|about\s+|nearly\s+)?(<duration>)\s*(years?|months?)`.
  - Exclure explicitement les durées d'une carrière antérieure révolue avant reconversion (ex. *« a exercé pendant quinze ans comme assistante de direction avant une reconversion »*, *« ancienne infirmière à l'hôpital pendant vingt-deux ans »*, *« a passé douze ans comme chargée de communication »*) grâce au marqueur grammatical (`depuis` rattaché à `installé(e)` / activité courante vs `pendant` / `a passé` / `ancienne` rattachés au passé antérieur). De même, si la fiche mentionne aussi une carrière passée (`pendant X ans`), conserver séparément l'ensemble des durées passées mentionnées dans la fiche afin de ne jamais déclencher de faux positif lorsqu'une phrase du rapport rappelle fidèlement cette carrière passée (ex. *« Christine, ancienne infirmière à l'hôpital pendant vingt-deux ans »* dans R8 ligne 44 est conforme à sa fiche et ne doit pas être signalée en contradiction).

- **D2 — Contrôle biographique aval `check_persona_biography_contradiction` et `audit_prose_persona_consistency`** :
  - Dans [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py) :
    1. `check_claim_persona_biography(claim_text, agent_name, profiles_by_name, all_profile_episodes=None)` vérifie une affirmation unitaire attribuée à `agent_name` :
       - **Règle d'ancienneté d'installation** : si `claim_text` affirme que `agent_name` est installé(e) / exerce son activité actuelle depuis $Y_{\text{claim}}$ années (ex. `installée depuis 17 ans`) alors que la fiche canonique de `agent_name` définit une ancienneté d'installation $Y_{\text{profile}}$ (ex. $2.5$ ans pour Sylvie), et que $|Y_{\text{claim}} - Y_{\text{profile}}| > \max(1.0, 0.35 \times Y_{\text{profile}})$ sans que $Y_{\text{claim}}$ ne corresponde à une autre durée biographique valide présente dans la fiche de `agent_name`, retourner une contradiction `PERSONA_BIOGRAPHY_CONTRADICTION`.
       - **Règle d'épisode monétaire biographique exclusif** : si `claim_text` attribue à `agent_name` un épisode biographique monétaire personnel (ex. perte de `1 500 €` sur un site, amende, dette personnelle — hors tarifs publics de l'offre étudiée partagés par plusieurs profils) qui est absent de la fiche de `agent_name` mais présent dans la fiche d'un autre persona admis, retourner une contradiction `PERSONA_BIOGRAPHY_CONTRADICTION`.
    2. `audit_prose_persona_consistency(markdown_content, profiles, allowed_names=None)` parcourt les paragraphes/puces du rapport, résout le persona sujet de chaque segment et agrège les `BriefContradiction` détectées (`prose_contradictions`, `prose_is_consistent: bool`).

- **D3 — Intégration dans `SimulationActionVerifier.verify_report_claim()` et `ReportAgent.audit_and_save_report_claims()`** :
  - Étendre la signature de [`SimulationActionVerifier.verify_report_claim()`](../../../backend/app/services/simulation_action_verifier.py#L1305-L1314) avec un paramètre optionnel `persona_profiles: Optional[Dict[str, Dict[str, Any]]] = None` (rétrocompatible : `None` par défaut).
  - Lorsque `persona_profiles` et `claim.agent_name` sont fournis, appeler `check_claim_persona_biography()`. Si une contradiction biographique factuelle est détectée :
    - marquer la claim `verification_status=VerificationStatus.CONTRADICTED`, `confidence=0.0` ;
    - ajouter dans `limitations` le message explicite préfixé par `"PERSONA_BIOGRAPHY_CONTRADICTION : "` détaillant l'attribut affirmé dans la prose et la valeur canonique de la fiche du persona ;
    - préserver strictement `claim.provenance_regime` et ne jamais promouvoir un entretien en `OBSERVED_SOCIAL_ACTION`.
  - Dans [`ReportAgent.audit_and_save_report_claims()`](../../../backend/app/services/report_agent.py#L4073-L4267), charger les profils personas de la simulation (filtrés aux acteurs admis via `actor_selection` si disponible), les transmettre à `verify_report_claim(..., persona_profiles=persona_profiles)` et mettre à jour `uploads/reports/<report_id>/brief_consistency.json` avec les résultats de `audit_prose_persona_consistency()`.

- **D4 — Injection de `GIT_COMMIT` dans Docker et durcissement de `SimulationAuditService._get_git_commit()`** :
  - Dans [`backend/Dockerfile`](../../../backend/Dockerfile) : déclarer `ARG GIT_COMMIT=unknown-git-commit` et `ENV GIT_COMMIT=${GIT_COMMIT}` avant `EXPOSE 5001`.
  - Dans [`docker-compose.yml`](../../../docker-compose.yml) : sous `services.backend.build`, ajouter `args: GIT_COMMIT: "${GIT_COMMIT:-unknown-git-commit}"` ; sous `services.backend.environment`, ajouter `GIT_COMMIT: "${GIT_COMMIT:-}"`.
  - Dans [`SimulationAuditService._get_git_commit()`](../../../backend/app/services/simulation_audit_service.py#L51-L70) :
    - ignorer toute variable d'environnement (`GIT_COMMIT`, `COMMIT_SHA`, `GITHUB_SHA`) dont la valeur nettoyée est vide ou égale (insensible à la casse) à `"unknown-git-commit"` ou `"unknown"` ;
    - tenter alors `git rev-parse HEAD` (depuis la racine du projet) ;
    - ne retourner `"unknown-git-commit"` que si ni les variables d'environnement ni `git rev-parse HEAD` ne fournissent un SHA valide.

- **D5 — Résolution en cascade et traçabilité de `time_horizon` dans `SimulationAuditService`** :
  - Dans [`SimulationAuditService`](../../../backend/app/services/simulation_audit_service.py), extraire un helper déterministe `_resolve_time_horizon_metadata(sim_id, sim_dir, report_dir=None)` retournant `{"time_horizon": Optional[str], "time_horizon_is_inferred": bool, "time_horizon_source": str}` selon l'ordre de priorité suivant :
    1. `simulation_brief.json` dans `sim_dir` :
       - si `time_horizon` explicite non vide (et hors `"unknown"`, `"inconnu"`, `"none"`, `"null"`) $\rightarrow$ `(time_horizon, False, "explicit_brief")` ;
       - sinon, si `extract_inferred_horizon(goal, "")` trouve un horizon $\rightarrow$ `(inferred.time_horizon, True, "inferred_from_goal")`.
    2. Brief du projet associé via `ProjectManager.get_project(project_id)` :
       - même logique (`"explicit_brief"` ou `"inferred_from_goal"`).
    3. `simulation_requirement` lu depuis `sim_dir/state.json` ou `sim_dir/simulation_config.json` via `extract_inferred_horizon(simulation_requirement, "")` $\rightarrow$ `(inferred.time_horizon, True, "inferred_from_simulation_requirement")`.
    4. Titre / chapeau de `report_dir/outline.json` ou `report_dir/full_report.md` (500 premiers caractères) via `extract_inferred_horizon(head_text, "")` $\rightarrow$ `(inferred.time_horizon, True, "inferred_from_report")`.
    5. Repli final si aucune source ne contient d'horizon $\rightarrow$ `(None, False, "unresolved")`.
  - Dans `build_run_manifest()`, inclure `time_horizon`, `time_horizon_is_inferred` et `time_horizon_source` dans `manifest["simulation"]`.
  - Dans `gather_audit_files()`, si `simulation_brief.json` est inclus ou synthétisé à partir du projet, y injecter `time_horizon`, `time_horizon_is_inferred` et `time_horizon_source` pour garantir la parité entre `run_manifest.json` et `simulation_brief.json` (`AT-16`).

- **D6 — Enrichissement de `SimulationAuditService.gather_audit_files()` pour `brief_consistency.json`** :
  - Lors de la constitution du paquet d'audit d'un rapport (`gather_audit_files(sim_id, report_id)`), si `full_report.md` et les profils de la simulation sont disponibles, calculer `audit_prose_persona_consistency()` et fusionner le bloc `"prose_consistency"` (`prose_is_consistent`, `prose_contradictions`, `practice_durations_by_profile`) dans le `brief_consistency.json` embarqué dans l'archive et sauvegardé dans `uploads/reports/<report_id>/brief_consistency.json`.

- **D7 — Architecture du banc de qualification `verifier_qualification_epic_015.py`** :
  - Le script [`backend/scripts/verifier_qualification_epic_015.py`](../../../backend/scripts/verifier_qualification_epic_015.py) s'exécute de manière 100 % déterministe et hors-ligne par défaut (aucun appel LLM requis, `NFR-4` < 60 s) et vérifie :
    - **Critère C1 (`AT-01`, `AT-02`, `AT-03`, `AT-04`)** : préservation de `provenance_regime=INTERVIEW`, séparation `\b` action/intention (`suit`, `comment`, `rendre compte`), compteur `asserted_action_claims` et filtrage strict des événements OASIS passifs/transactions.
    - **Critère C2 (`AT-05`, `AT-06`, `AT-10`)** : schéma `report_interviews.json` v2 par répondant et authentification des citations d'entretien avec identifiants stables `ivw_*`.
    - **Critère C3 (`AT-07`, `AT-12`, `AT-13`, `AT-14`)** : fermeture de l'angle mort « rapport conceptuel » dans `ReportQualityGate`, détection par `section_role == "limitations"`, et section « Sources & Provenance » 100 % calculée.
    - **Critère C4 (`AT-08`, `AT-09`, `AT-19`)** : `ParticipationPolicy` par rôle, inclusion d'une organisation active hors cohorte de décision, et dénominateur d'adoption en inclusion positive (`ADOPTER_ROLES`).
    - **Critère C5 (`AT-10`)** : substitution chirurgicale `[persona non admis]` préservant la phrase, la ponctuation et les personas admis adjacents.
    - **Critère C6 (`AT-11`)** : détection déterministe de la contradiction biographique sur la fixture R8 (`Sylvie` : « installée depuis 17 ans » dans `full_report.md` vs « installée depuis deux ans et demi » dans `reddit_profiles.json` $\rightarrow$ `PERSONA_BIOGRAPHY_CONTRADICTION`), détection d'un transfert d'épisode monétaire entre profils, et non-blocage d'une évolution d'opinion légitime.
    - **Critère C7 (`AT-15`, `AT-16`)** : présence de `ARG GIT_COMMIT` / `ENV GIT_COMMIT` dans `backend/Dockerfile` et `docker-compose.yml`, résolution d'un `git_commit` valide par `SimulationAuditService`, et inférence traçable `time_horizon = "72 heures"` (`time_horizon_is_inferred = True`) sur la fixture R8.
    - **Critère C8 (`AT-17`, `AT-18`, `AT-19`, `AT-20`)** : scan AST/regex de généricité (`0` occurrence de constante métier de la fixture R8 dans `backend/app/`, `frontend/src/`, `locales/`) et qualification sur 3 scénarios synthétiques multi-domaines (1 : lancement SaaS B2B, 2 : débat associatif local à conversion nulle, 3 : grève de transport public avec syndicat/institution active).

### Stratégie de tests

- **Tests unitaires hermétiques (`backend/tests/test_story_015_6_biography_and_qualification.py`)** :
  - Extraction des durées d'installation (`extract_practice_durations`) en français et en anglais (nombres en lettres `deux ans et demi`, chiffres `17 ans`, mois `6 mois`, exclusion des carrières antérieures `pendant vingt-deux ans` / `a passé douze ans`).
  - Détection de contradiction d'ancienneté dans `check_claim_persona_biography` et `SimulationActionVerifier.verify_report_claim` (`VerificationStatus.CONTRADICTED` + `PERSONA_BIOGRAPHY_CONTRADICTION`), y compris sur l'extrait réel R8 de Sylvie.
  - Non-régression sur les rappels fidèles de carrière passée (ex. Christine, 22 ans d'hôpital) et sur les divergences d'opinion ou d'intention (`AT-11` : changement d'avis sans contradiction biographique $\rightarrow$ non `CONTRADICTED`).
  - Détection d'attribution croisée d'un épisode biographique monétaire personnel d'un profil $A$ vers un profil $B$.
  - Enrichissement de `brief_consistency.json` avec `prose_is_consistent` et `prose_contradictions` dans `ReportAgent.audit_and_save_report_claims()` et `SimulationAuditService.gather_audit_files()`.
  - Résolution de `git_commit` dans `SimulationAuditService._get_git_commit()` (variable `GIT_COMMIT` valide, rejet de la sentinelle `"unknown-git-commit"` au profit de `git rev-parse HEAD`, et contrat `Dockerfile` / `docker-compose.yml`).
  - Résolution en cascade de `time_horizon`, `time_horizon_is_inferred` et `time_horizon_source` dans `SimulationAuditService.build_run_manifest()` et `gather_audit_files()` (y compris sur la structure de fichiers R8 sans `simulation_brief.json`).
  - Exécution programmatique du banc `verifier_qualification_epic_015.py` vérifiant que C1 à C8 et AT-01 à AT-20 passent avec un verdict `GO`.
- **Non-régression globale** :
  - Suite complète pytest backend ($\ge 2\,152$ tests) et suite Node frontend (`50` tests) intégralement vertes.

---

## Critères d'acceptation

### AC1 — Extraction déterministe des attributs biographiques d'ancienneté et d'épisodes monétaires (`FR-07`, C6)

- **Given** une fiche persona contenant une mention d'ancienneté d'installation ou d'exercice actuel en français ou en anglais (en chiffres ou en lettres, en années ou en mois, avec ou sans demi-unité, ex. *« installée depuis deux ans et demi à Angers »*, *« installée en libéral depuis un peu plus de trois ans »*, *« practicing for 4 years »*) ainsi qu'éventuellement une carrière passée révolue (*« a exercé pendant quinze ans comme assistante »*, *« ancienne infirmière à l'hôpital pendant vingt-deux ans »*),
- **When** `extract_practice_durations(text)` est appelée sur le texte de la fiche,
- **Then** la durée d'installation actuelle est extraite et normalisée en années flottantes (`2.5`, `3.0`, `4.0`) tandis que les durées de carrières antérieures révolues sont distinguées et ne remplacent jamais l'ancienneté d'installation courante.

### AC2 — Détection aval des contradictions biographiques dans `verify_report_claim` et sur la fixture R8 (`FR-07`, C6, `AT-11`)

- **Given** les fiches personas admises d'une simulation (notamment sur R8 où la fiche de Sylvie indique *« installée depuis deux ans et demi »* et celle d'Émilie indique une perte personnelle de *« 1 500 € »*) et une affirmation du rapport attribuée à l'un de ces personas,
- **When** `SimulationActionVerifier.verify_report_claim()` (ou `audit_prose_persona_consistency()`) évalue :
  1. une affirmation attribuant à ce persona une ancienneté d'installation incompatible avec sa fiche (ex. *« Sylvie, pourtant installée depuis 17 ans avec un carnet plein, ajourne... »*), ou
  2. une affirmation attribuant à un persona $B$ un épisode biographique monétaire personnel exclusif du persona $A$,
- **Then** l'affirmation est marquée `VerificationStatus.CONTRADICTED` avec `confidence == 0.0` et une entrée dans `limitations` contenant le code `PERSONA_BIOGRAPHY_CONTRADICTION`, tout en préservant son `provenance_regime` d'origine.

### AC3 — Respect de la liberté d'opinion et des carrières antérieures fidèles (`FR-07`, C6, `AT-11`)

- **Given** un persona dont la fiche mentionne une hypothèse de départ, une posture initiale ou une carrière antérieure (ex. *« ancienne infirmière à l'hôpital pendant vingt-deux ans »*),
- **When** la prose finale du rapport :
  1. rapporte que ce persona a changé d'avis, exprimé un doute, ajourné sa décision ou formulé une objection non prévue dans sa fiche sans contredire ses attributs biographiques chiffrés, ou
  2. mentionne fidèlement la durée de sa carrière antérieure présente dans sa fiche,
- **Then** aucune contradiction `PERSONA_BIOGRAPHY_CONTRADICTION` n'est levée et la claim n'est pas marquée `CONTRADICTED` par le contrôle biographique.

### AC4 — Enrichissement de `brief_consistency.json` dans le rapport et le paquet d'audit (`FR-07`, C6)

- **Given** la génération ou l'audit des claims d'un rapport (`ReportAgent.audit_and_save_report_claims()` et `SimulationAuditService.gather_audit_files()`),
- **When** le contrôle de cohérence est exécuté sur le rapport final,
- **Then** le fichier `brief_consistency.json` produit pour le rapport (`uploads/reports/<report_id>/brief_consistency.json` et dans le ZIP d'audit) conserve les clés amont (`is_consistent`, `contradictions`, `diagnostics`) et expose en plus `prose_is_consistent: bool`, `prose_contradictions: list` et `diagnostics.practice_durations_by_profile: dict`.

### AC5 — Injection de `GIT_COMMIT` dans Docker et résolution robuste dans `run_manifest.json` (`FR-08`, C7, `AT-15`)

- **Given** [`backend/Dockerfile`](../../../backend/Dockerfile), [`docker-compose.yml`](../../../docker-compose.yml) et [`SimulationAuditService._get_git_commit()`](../../../backend/app/services/simulation_audit_service.py#L51-L70),
- **When** l'image Docker backend est construite avec `--build-arg GIT_COMMIT=<sha>` (ou lancée via `docker compose` avec `GIT_COMMIT` défini dans l'environnement) ou que `SimulationAuditService.build_run_manifest()` s'exécute dans un environnement où `GIT_COMMIT` vaut la sentinelle par défaut `"unknown-git-commit"` mais où `.git` est accessible,
- **Then** `Dockerfile` déclare `ARG GIT_COMMIT=unknown-git-commit` et `ENV GIT_COMMIT=${GIT_COMMIT}`, `docker-compose.yml` propage `GIT_COMMIT` dans `build.args` et `environment`, et `_get_git_commit()` retourne le SHA effectif (en ignorant la sentinelle `"unknown-git-commit"` pour interroger `git rev-parse HEAD` si disponible).

### AC6 — Résolution en cascade et traçabilité de `time_horizon` dans `run_manifest.json` et `simulation_brief.json` (`FR-08`, C7, `AT-16`)

- **Given** une simulation dont `simulation_brief.json` a un champ `time_horizon` vide ou absent sur disque, mais dont le `goal` du brief projet, le `simulation_requirement` de `state.json` / `simulation_config.json` ou le titre du rapport contient un horizon temporel explicite (ex. `"Les 72 premières heures..."` sur la fixture R8 `sim_7a1b02b8c092`),
- **When** `SimulationAuditService.build_run_manifest(sim_id, report_id)` et `gather_audit_files(sim_id, report_id)` sont appelés,
- **Then** `run_manifest["simulation"]["time_horizon"]` vaut `"72 heures"` (et non `null`), `run_manifest["simulation"]["time_horizon_is_inferred"]` vaut `True`, `run_manifest["simulation"]["time_horizon_source"]` identifie la source d'inférence (`"inferred_from_goal"`, `"inferred_from_simulation_requirement"` ou `"inferred_from_report"`), et le `simulation_brief.json` embarqué dans le paquet d'audit reflète ce même horizon inféré.

### AC7 — Qualification déterministe sur la fixture R8 en mode `replay_frozen` (`C1`–`C7`, `AT-01`–`AT-16`, `AT-20`)

- **Given** les artefacts figés du run R8 (`sim_7a1b02b8c092` / `report_934d3254004b`),
- **When** le banc de qualification [`backend/scripts/verifier_qualification_epic_015.py`](../../../backend/scripts/verifier_qualification_epic_015.py) ré-évalue en mode `replay_frozen` (sans appel LLM) les contrats de l'Epic 015 sur R8,
- **Then** :
  - les citations d'entretien conservent `provenance_regime == "interview"` et ne sont jamais classées `OBSERVED_SOCIAL_ACTION` ;
  - le registre `report_claims.json` ré-audité expose `asserted_action_claims` cohérent et détecte la contradiction biographique de Sylvie (`PERSONA_BIOGRAPHY_CONTRADICTION`) ;
  - la section « Sources & Provenance » recalculée est 100 % alignée sur `report_claims.json` et `cohort_coverage.json` ;
  - le `run_manifest.json` recalculé expose un `git_commit` résolu ($\neq$ `"unknown-git-commit"`) et `time_horizon == "72 heures"` avec `time_horizon_is_inferred is True`.

### AC8 — Qualification multi-domaines et garde-fou de généricité (`NFR-2`, C8, `AT-17`, `AT-18`, `AT-19`)

- **Given** le code de production (`backend/app/`, `frontend/src/`, `locales/`) et les 3 scénarios synthétiques multi-domaines du banc `verifier_qualification_epic_015.py` :
  1. lancement d'une offre logicielle commerciale (avec prospects, fondateur et client existant),
  2. débat associatif local sans enjeu d'achat ni conversion commerciale (`AT-19`),
  3. grève de transport public avec organisation syndicale/institutionnelle active hors cohorte de décision (`AT-09`),
- **When** `verifier_qualification_epic_015.py` exécute le scan de généricité et les 3 scénarios,
- **Then** :
  - le scan de généricité confirme `0` occurrence des noms propres de la fixture R8 dans le code de production ;
  - les 3 scénarios multi-domaines passent l'ensemble des vérifications de contrat (rôles, dénominateur d'adoption nul sur le scénario associatif sans blocage, organisation active hors dénominateur sur la grève, contrôle biographique, barrière de publication) ;
  - le rapport formel [`docs/plans/015-contrats-preuve-roles-et-ihm/rapport-qualification-epic-015.md`](rapport-qualification-epic-015.md) est généré avec le **VERDICT GO**.

### AC9 — Non-régression globale et conformité documentaire (`NFR-4`, `NFR-5`)

- **Given** l'ensemble des suites de tests du dépôt et le validateur de plans,
- **When** on exécute `backend/.venv/bin/pytest`, `pnpm --dir frontend test` et `backend/.venv/bin/python backend/scripts/validate_plans.py`,
- **Then** 100 % des tests backend et frontend passent sans régression et tous les artefacts de planification sont valides.

---

## Définition de fini

- [ ] Contrôle biographique aval (`PracticeDurationAttribute`, `extract_practice_durations`, `check_claim_persona_biography`, `audit_prose_persona_consistency`) implémenté dans [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py) et câblé dans [`SimulationActionVerifier.verify_report_claim()`](../../../backend/app/services/simulation_action_verifier.py) et [`ReportAgent.audit_and_save_report_claims()`](../../../backend/app/services/report_agent.py).
- [ ] Injection de `GIT_COMMIT` ajoutée dans [`backend/Dockerfile`](../../../backend/Dockerfile) et [`docker-compose.yml`](../../../docker-compose.yml), et résolution durcie dans [`SimulationAuditService._get_git_commit()`](../../../backend/app/services/simulation_audit_service.py).
- [ ] Résolution en cascade et traçabilité de `time_horizon` (`time_horizon_is_inferred`, `time_horizon_source`) implémentées dans [`SimulationAuditService.build_run_manifest()`](../../../backend/app/services/simulation_audit_service.py) et `gather_audit_files()`, ainsi que l'enrichissement aval de `brief_consistency.json`.
- [ ] Banc de qualification [`backend/scripts/verifier_qualification_epic_015.py`](../../../backend/scripts/verifier_qualification_epic_015.py) implémenté, exécuté et générant [`docs/plans/015-contrats-preuve-roles-et-ihm/rapport-qualification-epic-015.md`](rapport-qualification-epic-015.md) avec **VERDICT GO** sur C1 à C8 et AT-01 à AT-20.
- [ ] Suite de tests hermétiques [`backend/tests/test_story_015_6_biography_and_qualification.py`](../../../backend/tests/test_story_015_6_biography_and_qualification.py) créée et passante.
- [ ] Suite complète pytest backend et suite Node frontend vertes.
- [ ] `backend/.venv/bin/python backend/scripts/validate_plans.py` vert.

---

## Tâches

### T1 — Extraction des durées d'installation et contrôle biographique aval (`FR-07`, C6, `AT-11`)

- [ ] **T1.1** : Dans [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py), ajouter `PracticeDurationAttribute`, le convertisseur de nombres en lettres FR/EN (incluant `et demi` / `and a half` et la conversion des mois en années), et `extract_practice_durations(text: str) -> List[PracticeDurationAttribute]` en distinguant l'ancienneté d'installation courante (`depuis ...`) des carrières antérieures révolues (`pendant ...`, `ancienne ... pendant ...`, `a passé ...`).
- [ ] **T1.2** : Dans [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py), implémenter `check_claim_persona_biography(claim_text, agent_name, profiles_by_name, all_profile_episodes=None)` et `audit_prose_persona_consistency(markdown_content, profiles, allowed_names=None)` retournant les contradictions factuelles `PERSONA_BIOGRAPHY_CONTRADICTION` (durée d'installation contradictoire ou épisode monétaire biographique exclusif attribué au mauvais persona) sans bloquer les divergences d'opinion (`AT-11`).
- [ ] **T1.3** : Dans [`backend/app/services/simulation_action_verifier.py`](../../../backend/app/services/simulation_action_verifier.py#L1305-L1840), ajouter le paramètre optionnel `persona_profiles` à `verify_report_claim()` et déclencher le marquage `VerificationStatus.CONTRADICTED` (`confidence=0.0`, limitation `PERSONA_BIOGRAPHY_CONTRADICTION`) lorsqu'une contradiction biographique factuelle est détectée, en préservant `provenance_regime`.
- [ ] **T1.4** : Dans [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py#L4073-L4267) (`audit_and_save_report_claims`), charger les profils personas admis de la simulation, les passer à `verify_report_claim(..., persona_profiles=...)`, et persister `uploads/reports/<report_id>/brief_consistency.json` enrichi de `prose_is_consistent`, `prose_contradictions` et `diagnostics.practice_durations_by_profile`.

### T2 — Métadonnées Docker (`GIT_COMMIT`) et horizon temporel (`time_horizon`) dans `SimulationAuditService` (`FR-08`, C7, `AT-15`, `AT-16`)

- [ ] **T2.1** : Ajouter `ARG GIT_COMMIT=unknown-git-commit` et `ENV GIT_COMMIT=${GIT_COMMIT}` dans [`backend/Dockerfile`](../../../backend/Dockerfile), et propager `GIT_COMMIT` dans `build.args` et `environment` du service `backend` dans [`docker-compose.yml`](../../../docker-compose.yml).
- [ ] **T2.2** : Dans [`backend/app/services/simulation_audit_service.py`](../../../backend/app/services/simulation_audit_service.py#L51-L70), durcir `_get_git_commit()` pour ignorer les valeurs vides ou égales à `"unknown-git-commit"` / `"unknown"` dans les variables d'environnement avant d'exécuter `git rev-parse HEAD`.
- [ ] **T2.3** : Dans [`backend/app/services/simulation_audit_service.py`](../../../backend/app/services/simulation_audit_service.py#L73-L320), implémenter `_resolve_time_horizon_metadata(sim_id, sim_dir, report_dir=None)` avec résolution en cascade (`simulation_brief.json` $\rightarrow$ brief projet $\rightarrow$ `simulation_requirement` dans `state.json`/`simulation_config.json` $\rightarrow$ titre/chapeau du rapport) et exposer `time_horizon`, `time_horizon_is_inferred` et `time_horizon_source` dans `run_manifest["simulation"]` ainsi que dans le `simulation_brief.json` embarqué par `gather_audit_files()`.
- [ ] **T2.4** : Dans [`SimulationAuditService.gather_audit_files()`](../../../backend/app/services/simulation_audit_service.py#L254-L263), enrichir le `brief_consistency.json` embarqué dans le paquet d'audit avec les résultats de `audit_prose_persona_consistency()` exécuté sur `full_report.md` du rapport ciblé.

### T3 — Banc de qualification globale `verifier_qualification_epic_015.py` et rapport formel (`C1`–`C8`, `AT-01`–`AT-20`)

- [ ] **T3.1** : Créer [`backend/scripts/verifier_qualification_epic_015.py`](../../../backend/scripts/verifier_qualification_epic_015.py) évaluant de bout en bout les critères **C1 à C8** et les scénarios **AT-01 à AT-20** :
  - rejeu déterministe (`replay_frozen` sans appel LLM) sur la fixture R8 (`sim_7a1b02b8c092` / `report_934d3254004b`) ;
  - validation sur 3 scénarios synthétiques multi-domaines (lancement logiciel commercial, débat associatif local sans conversion commerciale `AT-19`, grève de transport public avec organisation active `AT-09`) ;
  - scan AST/regex de généricité (`NFR-2`) sur `backend/app/`, `frontend/src/` et `locales/`.
- [ ] **T3.2** : Exécuter `backend/.venv/bin/python backend/scripts/verifier_qualification_epic_015.py` et générer le rapport formel [`docs/plans/015-contrats-preuve-roles-et-ihm/rapport-qualification-epic-015.md`](rapport-qualification-epic-015.md) avec **VERDICT GO**.

### T4 — Tests unitaires et d'intégration hermétiques (`AC1`–`AC9`)

- [ ] **T4.1** : Créer [`backend/tests/test_story_015_6_biography_and_qualification.py`](../../../backend/tests/test_story_015_6_biography_and_qualification.py) couvrant `AC1` à `AC8` (extraction d'ancienneté FR/EN, contradiction Sylvie R8 `17 ans` vs `2.5 ans`, respect des carrières passées et des divergences d'opinion `AT-11`, épisode monétaire croisé, enrichissement `brief_consistency.json`, `GIT_COMMIT` Docker/service, cascade `time_horizon` sur R8, et exécution de `verifier_qualification_epic_015.py`).
- [ ] **T4.2** : Exécuter la suite complète pytest backend, la suite Node frontend (`pnpm --dir frontend test`) et `backend/.venv/bin/python backend/scripts/validate_plans.py`.

### T5 — Synchronisation documentaire et préparation à la revue

- [ ] **T5.1** : Mettre à jour cette story (`Notes de complétion`, cases cochées, statut `review`), [`epic-015.md`](epic-015.md), [`docs/sprint-status.yaml`](../../sprint-status.yaml), [`docs/STATUS.md`](../../STATUS.md) et [`AGENTS.md`](../../../AGENTS.md).

---

## Notes de développement

### Fichiers à modifier ou créer

| Fichier | Action | Rôle |
|---|---|---|
| [`backend/app/services/brief_consistency.py`](../../../backend/app/services/brief_consistency.py) | Modifier | Ajout de `PracticeDurationAttribute`, `extract_practice_durations`, `check_claim_persona_biography` et `audit_prose_persona_consistency` (`FR-07`, C6, `AT-11`) |
| [`backend/app/services/simulation_action_verifier.py`](../../../backend/app/services/simulation_action_verifier.py) | Modifier | Câblage de `persona_profiles` et `check_claim_persona_biography` dans `verify_report_claim()` (`PERSONA_BIOGRAPHY_CONTRADICTION`) |
| [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) | Modifier | Chargement des profils personas dans `audit_and_save_report_claims()` et persistance de `brief_consistency.json` enrichi côté rapport |
| [`backend/app/services/simulation_audit_service.py`](../../../backend/app/services/simulation_audit_service.py) | Modifier | Durcissement de `_get_git_commit()`, résolution en cascade `_resolve_time_horizon_metadata()` (`time_horizon`, `time_horizon_is_inferred`, `time_horizon_source`) et enrichissement de `brief_consistency.json` et `simulation_brief.json` dans `gather_audit_files()` (`FR-08`, C7, `AT-15`, `AT-16`) |
| [`backend/Dockerfile`](../../../backend/Dockerfile) | Modifier | Ajout de `ARG GIT_COMMIT=unknown-git-commit` et `ENV GIT_COMMIT=${GIT_COMMIT}` |
| [`docker-compose.yml`](../../../docker-compose.yml) | Modifier | Propagation de `GIT_COMMIT` dans `services.backend.build.args` et `services.backend.environment` |
| [`backend/scripts/verifier_qualification_epic_015.py`](../../../backend/scripts/verifier_qualification_epic_015.py) | Créer | Banc de qualification globale de l'Epic 015 évaluant C1–C8 et AT-01–AT-20 (R8 `replay_frozen` + 3 scénarios multi-domaines + scan de généricité `NFR-2`) |
| [`docs/plans/015-contrats-preuve-roles-et-ihm/rapport-qualification-epic-015.md`](rapport-qualification-epic-015.md) | Créer | Rapport formel de qualification de l'Epic 015 |
| [`backend/tests/test_story_015_6_biography_and_qualification.py`](../../../backend/tests/test_story_015_6_biography_and_qualification.py) | Créer | Tests unitaires et d'intégration hermétiques de la Story `015-6` |

### Commandes de vérification

```bash
# Tests unitaires et d'intégration dédiés à la story 015-6
backend/.venv/bin/pytest backend/tests/test_story_015_6_biography_and_qualification.py backend/tests/test_brief_consistency.py -v

# Banc de qualification globale de l'Epic 015
backend/.venv/bin/python backend/scripts/verifier_qualification_epic_015.py

# Suite complète backend et frontend
backend/.venv/bin/pytest
pnpm --dir frontend test

# Validateur des artefacts de planification
backend/.venv/bin/python backend/scripts/validate_plans.py
```

---

## Revue

*(Section réservée à la revue de code contradictoire BMAD 4 couches une fois l'implémentation terminée.)*

---

## Notes de complétion

*(À remplir lors de la finalisation de l'implémentation de la story.)*
