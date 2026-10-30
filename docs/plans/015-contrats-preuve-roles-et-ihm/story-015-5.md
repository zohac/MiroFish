---
id: "015-5"
epic: "015"
titre: "Ergonomie IHM Step 3 (cartes de statut sans débordement) et télémétrie vivante Step 4"
statut: in-progress
created: 2026-10-30
updated: 2026-10-30
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 015-5 : Ergonomie IHM Step 3 (cartes de statut sans débordement) et télémétrie vivante Step 4

## Contexte et objectif

Dans le cadre de l'[Epic 015](epic-015.md) (*Contrats de preuve, gouvernance des rôles et ergonomie IHM Step 3/4*, voir [`prd.md` §3.4](prd.md), §5 Axes E et F, §6 FR-15 à FR-17 et [`architecture.md` §5.8 et §5.9](architecture.md)), l'audit de la simulation `sim_7a1b02b8c092` (rapport `report_934d3254004b`) a mis en évidence deux frictions d'interface majeures aux étapes **3/5** (`Step3Simulation.vue`) et **4/5** (`Step4Report.vue`) :

1. **Étape 3/5 — Débordement des cartes de statut et collision du bouton d'action** :
   - Dans [`frontend/src/components/Step3Simulation.vue`](../../../frontend/src/components/Step3Simulation.vue), la barre `.control-bar` (`:4-158`, CSS `:829-838`) impose une hauteur rigide `height: 64px` sans `flex-wrap: wrap`.
   - Le groupe `.status-group` (`:5-139`, CSS `:840-843`) aligne les trois cartes `.platform-status` (`Info Plaza`, `Topic Community`, `Mémoire du Graphe`) sans retour à la ligne (`flex-wrap`) et le conteneur `.action-controls` (`:141-157`) ne possède **aucune règle CSS dédiée** dans `<style scoped>`.
   - À l'intérieur de chaque carte `.platform-status` (CSS `:846-859`), `.platform-stats` (`:19-32`, `:60-73`, `:117-132`, CSS `:952-955`) aligne les compteurs `.stat` (`:957-961`) sur une seule ligne non enveloppante sans `white-space: nowrap` sur chaque `.stat`.
   - En locale française (`fr`), les libellés plus longs (`TEMPS 48 h 0 min`, `ÉTAT Drain en cours...`, `INGESTÉES 120`, `ATTENTE 366`) provoquent :
     - la cassure de `48 h 0 min` sur deux lignes (`48 h 0` / `min`) qui fait déborder verticalement le texte hors de la barre de `64px` ;
     - le débordement horizontal de `ATTENTE 366` hors du cadre `.platform-status.memory.draining` ;
     - en mode `Scindé` (panneau droit réduit à 50 % de la fenêtre, soit `640px` sur un écran `1280px`), le chevauchement direct (`0px` de marge) entre la carte `Mémoire du Graphe` et le bouton noir `.action-controls` (`Générer le rapport` / `Synchronisation du graphe...`).

2. **Étape 4/5 — Télémétrie figée sur « indisponible » pendant toute la rédaction et course au statut terminal** :
   - Côté backend, dans [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py), `self._persist_usage_metrics(report_id, report)` (`:1533-1565`) n'est appelé qu'en toute fin de génération (`:3090`, `:3189`, `:3252`, `:3300`). Tant que la rédaction est en cours (`status: planning` ou `generating`), `usage.json` n'existe pas sur disque et `GET /api/report/<report_id>/usage` ([`backend/app/api/report.py:1303-1324`](../../../backend/app/api/report.py)) renvoie `404`.
   - De plus, `_persist_usage_metrics` pose immédiatement le sceau `self._usage_persisted = True` dès son premier appel (`:1547-1556`) : si on l'appelait tel quel après `plan_outline`, tous les appels suivants (sections, entretiens, complétion finale) renverraient le `usage.json` figé de la planification sans jamais le mettre à jour.
   - En fin de génération (`:3138-3146`), `self.report_logger.log_report_complete(...)` écrit l'événement `"action": "report_complete"` dans `agent_log.jsonl` **avant** `ReportManager.save_report(report)` (`:3144`) et `ReportManager.update_progress(...)` (`:3146`). De même, sur arrêt contrôlé (`:3174` vs `:3189-3214`) ou erreur (`:3250` vs `:3252-3279`), `log_error` est émis **avant** `_persist_usage_metrics`, `_append_to_history` et `save_report`. Lorsque le frontend détecte `report_complete` ou `error` dans `agent_log.jsonl`, il interroge immédiatement `/usage`, `/quality`, `/claims` et `/history` pendant la fenêtre où les fichiers finaux ne sont pas encore persistés.
   - Côté frontend, dans [`frontend/src/components/Step4Report.vue`](../../../frontend/src/components/Step4Report.vue), `loadCurrentTelemetry(props.reportId)` (`:772-786`) n'est appelé qu'à l'ouverture initiale du composant (`watch(() => props.reportId)` `:2716`, quand `usage.json` n'existe pas encore) et à la réception de `report_complete` (`:2566`). Il n'est jamais rafraîchi lors des jalons intermédiaires (`planning_complete`, `section_complete`, `tool_result`) ni lors d'un arrêt en erreur (`action === 'error'`).
   - Enfin, pendant qu'un rapport est activement en cours de génération, les propriétés calculées `currentTokens`, `currentInferenceDuration`, `currentWallDuration`, `currentCost` et `currentClaimsLabel` (`:648-702`) affichent toutes `indisponible` (`step4.metricUnavailable`) au lieu de distinguer honnêtement une mesure **en cours de calcul** (`en cours…`), un modèle **non tarifé** dans la table de prix (`non tarifé` alors que les tokens sont connus) et une télémétrie réellement **indisponible** sur un rapport terminé sans artefact.

**En tant qu'** utilisateur supervisant une simulation à l'étape 3/5 puis la rédaction du rapport à l'étape 4/5,
**je veux** que les cartes de statut de l'étape 3 s'adaptent sans débordement ni collision dans les trois modes d'affichage (`Graphe` / `Scindé` / `Banc d'essai`) et que le bandeau de télémétrie de l'étape 4 se mette à jour au fil des jalons de rédaction avec un vocabulaire d'état honnête (`en cours…`, `non tarifé`, `indisponible`),
**afin de** lire sans troncature l'état d'avancement des plateformes et de la mémoire GraphRAG, suivre en direct la consommation de tokens et les temps d'exécution du `ReportAgent`, et obtenir un état terminal cohérent dès la fin (nominale ou en échec) du rapport.

---

## Définition de prêt

- [x] Le PRD de l'Epic 015 ([`docs/plans/015-contrats-preuve-roles-et-ihm/prd.md`](prd.md) §3.4, §5 Axes E et F, §6 FR-15 à FR-17, §7 NFR-1 à NFR-5, §8 C9 et C10) et l'architecture ([`architecture.md`](architecture.md) §5.8 et §5.9) sont validés.
- [x] Les stories amont `015-1`, `015-2`, `015-3` et `015-4` sont closes (`done`, 2 145 tests backend + 43 tests frontend verts).
- [x] Les points d'ancrage exacts dans le code source ont été inspectés et vérifiés :
  - [`frontend/src/components/Step3Simulation.vue`](../../../frontend/src/components/Step3Simulation.vue) (template `.control-bar` `:4-158`, CSS `.control-bar` `:829-838`, `.status-group` `:840-843`, `.platform-status` `:846-859`, `.actions-tooltip` `:874-907`, `.platform-stats` `:952-955`, `.stat` `:957-961`) ;
  - [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) (`_persist_usage_metrics` `:1533-1565`, `_execute_tool` `:1567-1628`, `plan_outline` `:2777-2795`, boucle de sections `:2820-2890`, séquence de clôture `:3088-3305`) ;
  - [`backend/app/services/report_usage_tracker.py`](../../../backend/app/services/report_usage_tracker.py) (`record_call` `:617-697`, `build_metrics` `:762-805`) ;
  - [`frontend/src/components/Step4Report.vue`](../../../frontend/src/components/Step4Report.vue) (bandeau `.report-telemetry-strip` `:68-151`, métriques calculées `:648-702`, `loadCurrentTelemetry` `:772-786`, `fetchAgentLog` `:2539-2575`) ;
  - [`frontend/src/utils/reportComparison.js`](../../../frontend/src/utils/reportComparison.js) (`summarizeUsage` `:418-451`, `isRunningReport` `:371-379`) et [`frontend/tests/reportComparison.test.js`](../../../frontend/tests/reportComparison.test.js) ;
  - [`locales/fr.json`](../../../locales/fr.json), [`locales/en.json`](../../../locales/en.json), [`locales/zh.json`](../../../locales/zh.json) et [`backend/tests/test_i18n_parity.py`](../../../backend/tests/test_i18n_parity.py).

---

## Critères d'acceptation

- [ ] **AC1 — Barre `.control-bar` et cartes `.platform-status` extensibles sans débordement à l'étape 3 (FR-15, C9)** :
  - **Given** le composant [`frontend/src/components/Step3Simulation.vue`](../../../frontend/src/components/Step3Simulation.vue) affiché en locale `fr`, `en` ou `zh`, avec des valeurs longues (`ROUND 144 / 144`, `TEMPS 48 h 0 min`, `ACTES 669`, `ÉTAT Drain en cours...`, `INGESTÉES 120`, `ATTENTE 366`),
  - **When** la barre `.control-bar` est rendue en mode `Graphe`, `Scindé` (`50 %` d'une fenêtre `1280×800`, soit `640px`, et `1440×900`, soit `720px`) ou `Banc d'essai`,
  - **Then** :
    1. `.control-bar` utilise `min-height: 64px; height: auto; flex-wrap: wrap; gap: 12px 16px;` (plus de `height: 64px` fixe qui tronque ou fait déborder le contenu verticalement) ;
    2. `.status-group` utilise `display: flex; flex-wrap: wrap; gap: 12px; flex: 1 1 auto; min-width: 0; align-items: stretch;` ;
    3. chaque `.platform-status` utilise `min-width: 140px; max-width: 100%; box-sizing: border-box; overflow: visible;` (afin que chaque `.stat` reste dans le cadre de la carte tout en préservant l'affichage au survol de l'infobulle absolue `.actions-tooltip` positionnée à `top: 100%`) ;
    4. `.platform-stats` utilise `display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: baseline;` et chaque `.stat` utilise `white-space: nowrap;` pour interdire toute coupure interne d'un couple label/valeur (ex. `TEMPS 48 h 0 min` ou `ATTENTE 366` ne se coupe jamais au milieu de `0 min`).

- [ ] **AC2 — Séparation garantie entre `.status-group` et `.action-controls` (FR-15, C9)** :
  - **Given** la barre `.control-bar` de `Step3Simulation.vue` contenant `.status-group` et `.action-controls`,
  - **When** le conteneur est affiché en vue large ou en vue `Scindé` (`640px` / `720px`),
  - **Then** `.action-controls` possède une règle CSS explicite (`display: flex; align-items: center; flex-shrink: 0; margin-left: auto;`) et le `gap: 12px 16px` de `.control-bar` garantit un espacement minimal de `12px` (horizontal côte à côte ou vertical après retour à la ligne propre) entre la dernière carte `.platform-status` (`Mémoire du Graphe`) et le bouton `.action-btn` (`Générer le rapport` / `Synchronisation du graphe...`), sans aucun chevauchement (`0px`).

- [ ] **AC3 — Persistance incrémentale de `usage.json` sans scellement prématuré de `_usage_persisted` (FR-16, C10)** :
  - **Given** une génération de rapport en cours dans [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py),
  - **When** `_persist_usage_metrics(report_id, report, final=False)` est appelé aux jalons intermédiaires :
    1. immédiatement après `self.plan_outline(...)` ;
    2. après la génération de chaque section dans la boucle de rédaction ;
    3. après chaque exécution d'outil d'entretien (`interview_agents` / `interview_agents_batch`) dans `_execute_tool` ;
  - **Then** :
    1. `usage.json` est écrit atomiquement sur disque à chaque jalon avec les totaux cumulés courants (`total_calls`, `total_prompt_tokens`, `total_completion_tokens`, `total_tokens`, `total_Wall_seconds`, `total_inference_seconds`, `calls_by_phase`, `estimated_cost_usd`, `pricing_available`) ;
    2. tant que `final=False`, l'attribut `self._usage_persisted` reste `False` et `self._usage_tracker._completed_at` n'est pas figé définitivement, de sorte que les jalons suivants continuent d'actualiser `usage.json` ;
    3. lors de l'appel final `_persist_usage_metrics(report_id, report, final=True)` (avant `build_audit_package()` et dans les blocs d'arrêt/erreur/finally), `usage.json` est figé et `self._usage_persisted` passe à `True`, garantissant que le `usage.json` sur disque et celui embarqué dans `simulation_audit_<report_id>.zip` restent **octet pour octet identiques**.

- [ ] **AC4 — Élimination de la condition de course terminale entre `agent_log.jsonl` et la persistance du rapport (FR-16, C10)** :
  - **Given** la fin d'exécution de `ReportAgent._generate_report_internal` (succès nominal, arrêt contrôlé `ReportGenerationStopped`, ou exception générale),
  - **When** le backend finalise les artefacts (`usage.json` final, `report_history.json`, `ReportManager.save_report(report)` écrivant `meta.json` et `full_report.md`, `ReportManager.update_progress(...)`),
  - **Then** toutes ces écritures sur disque sont exécutées **avant** l'émission de l'événement terminal dans `agent_log.jsonl` (`self.report_logger.log_report_complete(...)` ou `self.report_logger.log_error(...)`), de sorte qu'un client qui détecte `report_complete` ou `error` au polling lit immédiatement les fichiers finaux cohérents sur `/usage`, `/quality`, `/claims` et `/history`.

- [ ] **AC5 — Rafraîchissement temps réel de la télémétrie dans `Step4Report.vue` aux jalons de polling et sur erreur (FR-16, FR-17, C10)** :
  - **Given** [`frontend/src/components/Step4Report.vue`](../../../frontend/src/components/Step4Report.vue) en cours de polling via `fetchAgentLog`,
  - **When** un lot `newLogs` contient au moins une entrée dont `action` appartient à `['planning_complete', 'section_complete', 'tool_result', 'report_complete', 'error']`,
  - **Then** :
    1. `loadCurrentTelemetry(props.reportId)` est invoqué pour rafraîchir `currentUsage` (et `currentClaims` dès qu'il est disponible) sans attendre la fin complète du rapport ;
    2. si un log porte `action === 'error'` (échec ou arrêt contrôlé de génération), `Step4Report.vue` met à jour l'état du rapport (`reportOutline.value.status = 'failed'` s'il était encore en cours), appelle `stopPolling()`, puis déclenche `loadCurrentTelemetry(props.reportId)`, `fetchQualityResult()` et `loadHistory()` afin que le bandeau reflète immédiatement le motif d'arrêt (`stop_reason`), les tokens consommés avant l'arrêt et le statut terminal.

- [ ] **AC6 — Distinction sémantique honnête entre « en cours… », « non tarifé » et « indisponible » (FR-17, C10)** :
  - **Given** le bandeau de télémétrie de `Step4Report.vue` et les helpers purs de [`frontend/src/utils/reportComparison.js`](../../../frontend/src/utils/reportComparison.js),
  - **When** les métriques sont formatées pour l'affichage :
    1. **Pendant la génération active** (`isActivelyGenerating === true`, c'est-à-dire rapport ni terminé ni en échec) :
       - tant que `currentUsage` n'a pas encore enregistré de premier appel (`usageAvailable === false`), `Tokens consommés`, `Durée d'inférence` et `Coût estimé` affichent `t('step4.metricPending')` (`"en cours…"` / `"in progress…"` / `"计算中…"`) et non `"indisponible"` ;
       - tant que `currentClaims` est `null` (avant la phase 3 de vérification), `Affirmations vérifiées / total` affiche `t('step4.metricPending')` (`"en cours…"`) et non `"indisponible"` ;
       - `Temps mural` (`currentWallDuration`) affiche `formatSeconds(currentUsage.wallSeconds)` dès que `usage.json` est présent, ou à défaut le temps écoulé depuis le début du rapport (`elapsedSeconds` issu des logs ou `startTime`), ou `t('step4.metricPending')` au tout début ;
    2. **Lorsque les tokens sont connus mais que le modèle est absent de la table de tarification** (`usageAvailable === true` et `pricingAvailable === false`, ex. `deepseek-v4.1-flash` sur passerelle non tarifée) :
       - `Coût estimé` affiche `t('step4.metricUnpriced')` (`"non tarifé"` / `"unpriced"` / `"未定价"`) au lieu de `"indisponible"`, afin de ne pas faire croire que la télémétrie est en panne alors que les tokens et durées sont bien mesurés ;
    3. **Une fois le rapport terminé ou échoué** (`isActivelyGenerating === false`) :
       - toute métrique dont l'artefact sous-jacent est réellement absent (`usageAvailable === false` ou `currentClaims === null`) affiche `t('step4.metricUnavailable')` (`"indisponible"` / `"unavailable"` / `"不可用"`).

- [ ] **AC7 — Parité i18n trilingue stricte (`fr.json`, `en.json`, `zh.json`) (NFR-5)** :
  - **Given** les fichiers [`locales/fr.json`](../../../locales/fr.json), [`locales/en.json`](../../../locales/en.json) et [`locales/zh.json`](../../../locales/zh.json),
  - **When** les nouvelles clés `step4.metricPending` et `step4.metricUnpriced` sont ajoutées dans les trois dictionnaires,
  - **Then** `backend/.venv/bin/pytest backend/tests/test_i18n_parity.py -v` passe à 100 % (parité stricte des clés et des placeholders `{var}` entre `fr`, `en` et `zh`).

- [ ] **AC8 — Tests hermétiques backend et frontend et zéro régression (NFR-3, NFR-4)** :
  - **Given** la suite de tests unitaires du dépôt,
  - **When** on exécute `backend/.venv/bin/pytest backend/tests/test_story_015_5_live_telemetry.py backend/tests/test_i18n_parity.py -v` et `pnpm --dir frontend test`,
  - **Then** tous les nouveaux tests unitaires backend et frontend passent en moins de 5 secondes et l'ensemble de la suite (`backend/.venv/bin/pytest backend/tests/ -q` et `pnpm --dir frontend test`) reste 100 % vert avec `ruff check` propre.

---

## Définition de fini

- [ ] Le CSS de [`frontend/src/components/Step3Simulation.vue`](../../../frontend/src/components/Step3Simulation.vue) est mis à jour pour `.control-bar`, `.status-group`, `.platform-status`, `.platform-stats`, `.stat` et `.action-controls` sans casser `.actions-tooltip`.
- [ ] [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) persiste `usage.json` de manière incrémentale (`final=False`) après `plan_outline`, après chaque section et après chaque appel d'outil d'entretien, et persiste tous les artefacts finaux avant d'émettre `log_report_complete` ou `log_error`.
- [ ] [`frontend/src/utils/reportComparison.js`](../../../frontend/src/utils/reportComparison.js) et [`frontend/src/components/Step4Report.vue`](../../../frontend/src/components/Step4Report.vue) rafraîchissent la télémétrie aux jalons de polling et sur erreur, et distinguent `metricPending` (`en cours…`), `metricUnpriced` (`non tarifé`) et `metricUnavailable` (`indisponible`).
- [ ] Les dictionnaires [`locales/fr.json`](../../../locales/fr.json), [`locales/en.json`](../../../locales/en.json) et [`locales/zh.json`](../../../locales/zh.json) contiennent `step4.metricPending` et `step4.metricUnpriced` avec parité trilingue validée par `test_i18n_parity.py`.
- [ ] Les tests unitaires [`backend/tests/test_story_015_5_live_telemetry.py`](../../../backend/tests/test_story_015_5_live_telemetry.py) et [`frontend/tests/reportComparison.test.js`](../../../frontend/tests/reportComparison.test.js) couvrent les critères AC1 à AC7.
- [ ] Le build Vite (`pnpm --dir frontend build`) et les suites de tests backend et frontend passent sans erreur.
- [ ] Les fichiers de suivi (`story-015-5.md`, `epic-015.md`, `docs/sprint-status.yaml`, `docs/STATUS.md`, `AGENTS.md`) sont à jour et validés par `backend/.venv/bin/python backend/scripts/validate_plans.py`.

---

## Tâches

- [ ] **Tâche 1 — Mise en page responsive sans débordement de `.control-bar` à l'étape 3 (`Step3Simulation.vue`)**
  - [ ] Dans [`frontend/src/components/Step3Simulation.vue`](../../../frontend/src/components/Step3Simulation.vue) (`:829-965`), remplacer `height: 64px` sur `.control-bar` par `min-height: 64px; height: auto; padding: 10px 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px 16px;`.
  - [ ] Sur `.status-group` (`:840-843`), ajouter `flex-wrap: wrap; flex: 1 1 auto; min-width: 0; align-items: stretch;`.
  - [ ] Sur `.platform-status` (`:846-859`), ajouter `max-width: 100%; box-sizing: border-box; overflow: visible;` (conserver `position: relative` et `overflow: visible` pour que `.actions-tooltip` reste visible au survol).
  - [ ] Sur `.platform-stats` (`:952-955`), ajouter `flex-wrap: wrap; gap: 6px 12px; align-items: baseline;` et sur `.stat` (`:957-961`), ajouter `white-space: nowrap;`.
  - [ ] Ajouter la règle `.action-controls { display: flex; align-items: center; flex-shrink: 0; margin-left: auto; }` pour garantir un espacement d'au moins `12px` avec `.status-group` en mode `Graphe`, `Scindé` et `Banc d'essai`.

- [ ] **Tâche 2 — Persistance incrémentale de `usage.json` et ordre de clôture atomique (`report_agent.py`)**
  - [ ] Dans [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py), étendre la signature de `_persist_usage_metrics(self, report_id: str, report: Optional["Report"] = None, *, final: bool = True) -> ReportUsageMetrics` (`:1533-1565`) :
    - Si `getattr(self, "_usage_persisted", False)` est déjà `True`, retourner les métriques scellées existantes.
    - Si `final=False`, ne pas figer définitivement `_completed_at` sur `self._usage_tracker` (restaurer `self._usage_tracker._completed_at = None` après `build_metrics()` s'il n'était pas déjà fixé), écrire `usage.json` atomiquement via `metrics.save_to_file(self._get_usage_metrics_path(report_id))`, mettre à jour `report.usage_metrics` si `report` est fourni, et laisser `self._usage_persisted = False`.
    - Si `final=True`, écrire `usage.json` final et poser `self._usage_persisted = True`.
  - [ ] Appeler `self._persist_usage_metrics(report_id, report, final=False)` :
    - juste après `outline = self.plan_outline(...)` et `self.report_logger.log_planning_complete(...)` (`:2792`) ;
    - à la fin de chaque itération de section après `self.report_logger.log_section_complete(...)` (`:2873`) ;
    - dans `_execute_tool` (`:1620`), après l'enregistrement dans le journal d'un appel `interview_agents` ou `interview_agents_batch`.
  - [ ] Dans `_generate_report_internal`, réordonner la séquence de clôture nominale (`:3135-3150`), d'arrêt contrôlé (`:3170-3218`) et d'erreur (`:3245-3282`) pour que `_persist_usage_metrics(..., final=True)`, `_append_to_history(report)`, `ReportManager.save_report(report)` et `ReportManager.update_progress(...)` soient toujours exécutés **avant** `self.report_logger.log_report_complete(...)` ou `self.report_logger.log_error(...)`.

- [ ] **Tâche 3 — Rafraîchissement live et sémantique des métriques à l'étape 4 (`reportComparison.js`, `Step4Report.vue`, `locales/*.json`)**
  - [ ] Ajouter les clés `step4.metricPending` (`"en cours…"` / `"in progress…"` / `"计算中…"`) et `step4.metricUnpriced` (`"non tarifé"` / `"unpriced"` / `"未定价"`) dans [`locales/fr.json`](../../../locales/fr.json), [`locales/en.json`](../../../locales/en.json) et [`locales/zh.json`](../../../locales/zh.json).
  - [ ] Dans [`frontend/src/utils/reportComparison.js`](../../../frontend/src/utils/reportComparison.js), ajouter un helper pur exporté `resolveLiveTelemetryDisplay({ usage, claims, isGenerating, fallbackElapsedSeconds })` (ou équivalent testé dans `reportComparison.test.js`) qui détermine de façon déterministe l'état de chaque métrique (`value`, `state`: `'ready' | 'pending' | 'unpriced' | 'unavailable'`) selon que le rapport est en cours de génération (`isGenerating`), que `usage.usageAvailable` / `usage.pricingAvailable` sont vrais ou faux, et que `claims` est disponible ou `null`.
  - [ ] Dans [`frontend/src/components/Step4Report.vue`](../../../frontend/src/components/Step4Report.vue) :
    - Dans `fetchAgentLog` (`:2539-2575`), détecter si `newLogs` contient une action parmi `['planning_complete', 'section_complete', 'tool_result', 'report_complete', 'error']` et appeler `loadCurrentTelemetry(props.reportId)`.
    - Si `newLogs` contient `log.action === 'error'`, marquer le rapport en échec si son statut était encore actif (`if (reportOutline.value && isRunningReport(reportOutline.value.status)) reportOutline.value.status = 'failed'`), appeler `stopPolling()`, `loadCurrentTelemetry(props.reportId)`, `fetchQualityResult()` et `loadHistory()`.
    - Brancher `currentTokens`, `currentInferenceDuration`, `currentWallDuration`, `currentCost` et `currentClaimsLabel` (`:648-702`) sur la distinction `metricPending` / `metricUnpriced` / `metricUnavailable`.

- [ ] **Tâche 4 — Tests unitaires hermétiques et validation globale**
  - [ ] Créer [`backend/tests/test_story_015_5_live_telemetry.py`](../../../backend/tests/test_story_015_5_live_telemetry.py) testant :
    - la persistance incrémentale `final=False` suivie de mises à jour additionnelles puis du scellement `final=True` (et l'identité octet pour octet avec l'archive d'audit) ;
    - l'ordre strict de persistance sur disque avant `log_report_complete` et `log_error` ;
    - la présence des règles CSS anti-débordement dans `Step3Simulation.vue` (`min-height: 64px`, `flex-wrap: wrap`, `white-space: nowrap`, `.action-controls`, `overflow: visible`) et des jalons de rafraîchissement dans `Step4Report.vue`.
  - [ ] Étendre [`frontend/tests/reportComparison.test.js`](../../../frontend/tests/reportComparison.test.js) pour tester tous les cas de `resolveLiveTelemetryDisplay` (génération active sans usage, génération active avec usage mais sans tarification, génération active avec usage et tarification mais sans claims, rapport terminé avec/sans usage et avec/sans tarification).
  - [ ] Exécuter `backend/.venv/bin/pytest backend/tests/ -q`, `pnpm --dir frontend test`, `pnpm --dir frontend build`, `backend/.venv/bin/ruff check` et `backend/.venv/bin/python backend/scripts/validate_plans.py`.

---

## Notes de développement

### Décisions d'ingénierie arrêtées avant code

1. **D1 — Pourquoi `overflow: visible` sur `.platform-status` est impératif à l'étape 3** :
   Chaque carte `.platform-status` (`Info Plaza`, `Topic Community`, `Mémoire du Graphe`) contient un enfant `.actions-tooltip` positionné en absolu sous la carte (`position: absolute; top: 100%; left: 50%; transform: translateX(-50%); z-index: 100;`, voir [`Step3Simulation.vue:874-907`](../../../frontend/src/components/Step3Simulation.vue)). Si l'on ajoutait `overflow: hidden` sur `.platform-status` pour masquer un débordement de texte, l'infobulle détaillée au survol serait totalement rognée et invisible. La bonne solution consiste donc à permettre à `.platform-stats` de revenir à la ligne (`flex-wrap: wrap; gap: 6px 12px;`), à figer chaque couple label/valeur `.stat` avec `white-space: nowrap`, à rendre `.control-bar` extensible en hauteur (`min-height: 64px; height: auto; flex-wrap: wrap;`), et à conserver `overflow: visible` sur `.platform-status`.

2. **D2 — Pourquoi `.action-controls` chevauchait `.status-group` en mode `Scindé`** :
   Dans [`Step3Simulation.vue:141`](../../../frontend/src/components/Step3Simulation.vue), `<div class="action-controls">` n'avait aucune déclaration CSS dans `<style scoped>`, et `.control-bar` utilisait `justify-content: space-between` sans `gap` ni `flex-wrap`. Dès que la largeur cumulée des trois cartes `.platform-status` atteignait la largeur disponible du panneau droit en mode `Scindé` (`640px`), `.status-group` touchait directement `.action-controls` (`0px`) ou débordait sous lui. En ajoutant `flex-wrap: wrap; gap: 12px 16px;` sur `.control-bar`, `flex: 1 1 auto; min-width: 0; flex-wrap: wrap;` sur `.status-group` et `display: flex; align-items: center; flex-shrink: 0; margin-left: auto;` sur `.action-controls`, le bouton d'action conserve toujours au moins `12px` d'écart et s'aligne proprement à droite s'il passe sur une seconde ligne.

3. **D3 — Gestion du sceau `_usage_persisted` et de `_completed_at` dans `ReportAgent`** :
   Dans [`backend/app/services/report_agent.py:1533-1565`](../../../backend/app/services/report_agent.py), `_persist_usage_metrics` a été conçu lors de l'Epic 013 pour garantir que `usage.json` ne change plus après la création du paquet d'audit (`simulation_audit_<report_id>.zip`). De plus, `ReportUsageTracker.build_metrics()` ([`report_usage_tracker.py:766-767`](../../../backend/app/services/report_usage_tracker.py)) affecte `if self._completed_at is None: self._completed_at = datetime.now()`.
   Pour concilier **persistance incrémentale** et **intégrité du sceau final** :
   - `_persist_usage_metrics(self, report_id: str, report: Optional["Report"] = None, *, final: bool = True)` :
     - lorsque `final=False` (jalon intermédiaire) et que `not getattr(self, "_usage_persisted", False)`, on sauvegarde la valeur courante `prev_completed = self._usage_tracker._completed_at`, on appelle `metrics = self._usage_tracker.build_metrics()`, on restaure `self._usage_tracker._completed_at = prev_completed` (pour que `total_wall_seconds` continue de progresser aux jalons suivants), on écrit `usage.json` via `metrics.save_to_file(...)` et on laisse `self._usage_persisted = False` ;
     - lorsque `final=True` (défaut, appelé juste avant `build_audit_package()` et dans les gestionnaires de fin/erreur), on appelle `build_metrics()`, on écrit `usage.json` et on pose `self._usage_persisted = True`.

4. **D4 — Élimination de la course entre `agent_log.jsonl` et `ReportManager.save_report`** :
   Dans [`backend/app/services/report_agent.py:3138-3146`](../../../backend/app/services/report_agent.py), `log_report_complete` était appelé avant `ReportManager.save_report(report)`. Or `Step4Report.vue` poll `agent_log.jsonl` toutes les 2 secondes : dès qu'il voit `report_complete`, il appelle immédiatement `/quality`, `/usage`, `/claims` et `/history` et arrête son timer de polling (`stopPolling()`). Si `save_report(report)` n'est pas encore terminé à cet instant précis, `meta.json` contient encore `status: "generating"` et n'a pas encore son `quality_gate_result` définitif. Déplacer `log_report_complete` (ainsi que `log_error` dans les blocs `except ReportGenerationStopped` et `except Exception`) **après** `save_report(report)`, `_persist_usage_metrics(..., final=True)` et `_append_to_history(report)` supprime définitivement cette fenêtre de course.

5. **D5 — Distinction entre `en cours…`, `non tarifé` et `indisponible` à l'étape 4** :
   Sur la stack locale de référence utilisant `deepseek-v4.1-flash` via une passerelle OpenAI-compatible non répertoriée dans la table de tarification, `usage.json` remonte `usage_available: true`, `total_tokens: 162165`, `pricing_available: false`, `estimated_cost_usd: null`. Afficher `indisponible` pour le coût donnait l'impression d'une panne de mesure, alors que la consommation est parfaitement tracée et que seul le barème tarifaire du modèle est absent. La clé `step4.metricUnpriced` (`non tarifé`) exprime ce fait sans ambiguïté, tandis que `step4.metricPending` (`en cours…`) indique qu'une mesure (ou le bilan `claims` calculé en phase 3) est en attente d'achèvement de l'étape correspondante.

### Risques et garde-fous

- **Incompatibilité du sceau d'audit (Epic 013)** : Toute écriture dans `usage.json` après `build_audit_package()` briserait l'égalité de hash entre le fichier sur disque et l'archive `.zip`. Le paramètre `final=True` appelé avant `build_audit_package()` scelle `self._usage_persisted = True` et bloque toute réécriture ultérieure, y compris dans le bloc `finally:`.
- **Surcharge réseau au polling** : `Step4Report.vue` poll `agent_log.jsonl` toutes les 2 secondes, où de nombreux événements `react_thought` ou `tool_call` transitent. En ne déclenchant `loadCurrentTelemetry` que sur les jalons significatifs (`planning_complete`, `section_complete`, `tool_result`, `report_complete`, `error`), on limite les appels `GET /usage` et `GET /claims` aux seuls instants où `usage.json` a réellement changé.

### Frontière de la story (Hors périmètre)

- Le contrôle biographique aval de la prose générée (`check_prose_biography_consistency`), l'injection de `GIT_COMMIT` dans le `Dockerfile` backend et l'exécution du banc de qualification finale R8 relèvent exclusivement de la **Story `015-6`**.
- Aucune refonte du système de grille global de l'application (`SimulationRunView.vue` / `ReportView.vue`) en dehors de `.control-bar` (`Step3Simulation.vue`) et `.report-telemetry-strip` (`Step4Report.vue`).

---

## Revue

*(Section réservée à la revue contradictoire `/bmad-code-review` après implémentation.)*

---

## Notes de complétion

*(Section à remplir lors de la clôture de la story.)*
