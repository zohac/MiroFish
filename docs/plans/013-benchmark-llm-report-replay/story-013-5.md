---
id: "013-5"
epic: "013"
titre: "Interface Vue 3 Step 4 : sélecteur de rapport, régénération et comparaison"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 013-5 — Interface Vue 3 Step 4 : sélecteur de rapport, régénération et comparaison

Lot D (IHM), priorité **P1**. En tant qu'analyste et expérimentateur MiroFish, je veux sélectionner n'importe quelle version de rapport déjà générée pour une simulation, en lancer une nouvelle avec un profil LLM explicite, et comparer deux versions sur des faits mesurables (preuves figées, statut de publication, claims vérifiés, tokens, durée, coût estimé), afin de conduire le benchmark A/B de l'Epic 013 sans jamais écraser un rapport antérieur ni confondre deux jeux de preuves.

Cette story répond à l'exigence fonctionnelle **FR-08** (sélecteur et comparateur IHM Vue 3 du Step 4) et valide le critère de sortie **C6** (ergonomie de comparaison : l'écran Step 4 permet de basculer entre les rapports générés et de consulter leurs statuts d'audit respectifs). Elle rend exploitables côté IHM les capacités livrées par les stories 013-3 (isolation `reports/<report_id>/`, historique) et 013-4 (télémétrie, plafonds).

L'IHM ne décide pas : elle expose des faits, signale ce qui n'est pas comparable, et ne désigne jamais un « modèle gagnant » — l'arbitrage relève de la revue aveugle de la story 013-6.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  - **Sélecteur de rapport** : consommer `GET /api/report/simulation/<simulation_id>/history` et permettre de basculer entre toutes les versions d'une même simulation. La sélection vit dans l'URL (`/report/<report_id>`), donc le lien profond, le rechargement et l'historique navigateur fonctionnent.
  - **Régénération explicite** : exposer un catalogue de profils côté serveur (`GET /api/report/profiles`) et déclencher `POST /api/report/generate` avec `profile_id`, `replay_mode` et `force_regenerate=true`. Aucun secret ni `base_url` ne quitte le serveur. Le mode `replay_frozen` est proposé par défaut dès qu'un instantané de preuves existe ; le mode `live` exige un consentement explicite.
  - **Comparaison** : afficher côte à côte deux rapports de la même simulation (modèle, effort, mode de rejeu, statut de publication, claims vérifiés, télémétrie) et un **verdict de comparabilité** fondé sur l'identité des preuves (`evidence_snapshot_id`, empreinte SHA-256), avec un diff textuel par section et le téléchargement de l'audit de chaque version.
  - **Honnêteté de l'affichage** : `usage_available=false` s'affiche « indisponible », jamais `0 $` ; `estimated_cost_usd` est étiqueté comme estimation ; un rapport `needs_review` reste consultable mais visiblement non publiable ; un arrêt contrôlé affiche son `stop_reason`.
  - **Localisation** : toutes les chaînes nouvelles en `fr`, `en` et `zh`, sans clé orpheline.
- [x] **Documents consultés** :
  - [PRD Epic 013](prd.md) : §3 (objectif 1), §4 (FR-08), §5 (NFR-1, NFR-3, NFR-4).
  - [Architecture Epic 013](architecture.md) : §2.3 (`ReportUsageMetrics`), §3 (`reasoning_effort`).
  - [Hub Epic 013](epic-013.md) : FR-08, C6, C7.
  - [PRD source](../../PRD-MiroFish-benchmark-LLM-ReportAgent-replay-2026-10-19.md) : §9 (FR-06, FR-07, FR-11), §10 (Story 013-5), §11 (AT-06, AT-07, AT-08, AT-09, AT-10).
  - `frontend/src/views/ReportView.vue` : porteur de `currentReportId` (route `Report`), déjà réactif à `route.params.reportId`.
  - `frontend/src/components/Step4Report.vue` : en-tête, badge de qualité, téléchargement d'audit, panneaux de sections.
  - `frontend/src/api/report.js` : `getReport`, `getReportQuality`, `getReportAuditDownloadUrl`, `generateReport`.
  - `backend/app/api/report.py` : `GET /api/report/simulation/<sim_id>/history`, `GET /api/report/<report_id>`, `/quality`, `/claims`, `/cohort`, `/usage`, `/audit/download`, `POST /api/report/generate`.
  - `backend/app/models/report_llm_profile.py` : catalogue `get_standard_profile` (`flash-medium`, `flash-high`, `deepseek-v4-pro`, `qwen3.8-max`, `gpt-6.1-sol`).
  - `frontend/tests/i18n.test.js` : parité stricte des trois dictionnaires, déjà en CI.
  - `AGENTS.md` : §2.1 (couches), §2.2 (tests hermétiques), §2.8 (planification), §2.10 (français).
- [x] **Dépendances résolues** :
  - Story 013-3 (`done`) : historique `report_history.json`, isolation `reports/<report_id>/`, quatre endpoints REST.
  - Story 013-4 (`done`) : `usage.json`, `GET /api/report/<report_id>/usage`, `stop_reason`, `usage_available`, `pricing_available`.
  - Aucune dépendance nouvelle côté Node ni Python : le diff textuel et la comparabilité sont des fonctions pures locales.
  - Filet global : **1 939 tests hôte + 9 tests Node frontend au vert**.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **L'historique serveur est la seule source de vérité.** L'IHM ne reconstruit jamais la liste des rapports depuis `localStorage` ni depuis le dernier rapport connu ; elle lit `/history` à l'ouverture du Step 4 et après chaque génération.
  2. **Nouvel endpoint `GET /api/report/profiles`.** Il expose le catalogue serveur (`ReportLLMProfile.get_standard_profile(...).to_dict()`, secrets masqués) trié par identifiant stable, avec `profile_id`, `model`, `provider_id`, `reasoning_effort`, `billing_mode`, `max_total_cost_usd`, `max_wall_seconds`. Aucune `base_url`, aucune clé.
  3. **La régénération passe par `profile_id`, pas par un `llm_profile` client.** Le corps `llm_profile` reste disponible pour les appels avancés, mais l'IHM n'envoie jamais d'URL ni de secret. C'est la frontière NFR-4 côté navigateur.
  4. **`replay_frozen` par défaut, `live` sur consentement explicite.** Dès que le rapport courant porte un `evidence_snapshot_id`, le mode proposé est `replay_frozen` ; basculer en `live` demande une case à cocher et un avertissement (les entretiens live ne sont plus disponibles après clôture d'OASIS).
  5. **Comparabilité = fonction pure testée.** `evaluateComparability(left, right)` renvoie `{comparable, reasons[]}` à partir de `evidence_snapshot_id` et, quand il est exposé, de l'empreinte SHA-256. Deux rapports sans instantané ne sont jamais déclarés comparables : le verdict est « non comparable — preuves non figées ».
  6. **Diff textuel sans dépendance.** `diffSections(markdownA, markdownB)` compare les sections par titre puis ligne à ligne (LCS simple), avec normalisation des fins de ligne et des espaces de bord. Aucune bibliothèque de diff n'est ajoutée.
  7. **Aucun classement automatique.** La comparaison affiche des colonnes et des deltas bruts ; elle ne colore pas un « gagnant » et n'infère aucune supériorité de modèle.
  8. **La sélection est l'URL.** Le sélecteur pousse `/report/<report_id>` ; `ReportView` recharge déjà sur changement de route. Aucun état dupliqué en mémoire.
  9. **Accessibilité.** Sélecteur et boîte de dialogue natifs ou équivalents ARIA, navigables au clavier, focus rendu au déclencheur à la fermeture, libellés explicites.
  10. **Pas de nouvelle bibliothèque d'état.** `ref`/`computed` locaux ; aucune dépendance ajoutée à `frontend/package.json`.
- [x] **Stratégie de tests identifiée** :
  - **Node** (`frontend/tests/reportComparison.test.js`) : tri chronologique de l'historique, `evaluateComparability` (même instantané, instantanés différents, instantané absent), `diffSections` (ajout, suppression, section renommée, entrée vide), formatage de l'usage (`null`, `usage_available=false`, estimation, arrêt contrôlé).
  - **Backend** (`backend/tests/test_report_profiles_api.py`) : `GET /api/report/profiles` → 200, identifiants du catalogue, ordre déterministe, absence de `api_key` et de `base_url`, profil inconnu refusé par `/generate` (400).
  - **i18n** : la parité `fr`/`en`/`zh` est déjà vérifiée par `frontend/tests/i18n.test.js` ; toute clé ajoutée dans une langue doit l'être dans les trois.
  - **Non-régression** : suite backend complète, tests Node, `pnpm --dir frontend build`.
  - **Vérification visuelle** : build Vite puis parcours Step 4 sur la stack Docker (sélection, régénération, comparaison, téléchargement d'audit), consignée en notes de complétion.

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Sélecteur de rapport** : le Step 4 liste toutes les versions de la simulation (identifiant court, date, `profile_id`, mode de rejeu, statut de publication) triées chronologiquement. La version courante est mise en évidence. Sélectionner une version navigue vers `/report/<report_id>` et recharge sections, qualité, usage, claims et lien d'audit. Historique vide → état vide explicite ; rapport en cours → mention « en cours ». | Tests Node de tri et de libellé ; vérification visuelle du rechargement et du lien profond. |
| **AC2** | **Régénération explicite** : l'action « Régénérer » ouvre un dialogue alimenté par `GET /api/report/profiles` (aucun secret). L'utilisateur choisit profil et mode ; `replay_frozen` est proposé par défaut si un instantané existe, `live` exige une confirmation. La soumission envoie `profile_id`, `replay_mode`, `force_regenerate=true` et `simulation_id`, puis navigue vers le nouveau rapport. L'ancien reste listé et intact. | Test Flask du catalogue ; vérification visuelle : deux entrées distinctes après régénération. |
| **AC3** | **Comparaison factuelle** : sélectionner deux versions affiche côte à côte modèle/effort, mode de rejeu, statut de publication, claims vérifiés/total, tokens, durée d'inférence, temps mural, coût estimé et `stop_reason`. Un verdict explicite indique « comparaison contrôlée » uniquement si les preuves sont identiques (`evidence_snapshot_id` et empreinte), sinon « non comparable » avec le motif. Un diff par section et les liens d'audit des deux rapports sont accessibles. | Tests Node `evaluateComparability` et `diffSections` ; vérification visuelle sur deux rapports réels. |
| **AC4** | **Honnêteté et Fail-Safe d'affichage** : `usage_available=false` → « indisponible » (jamais `0 $`) ; le coût est libellé « estimation » ; `needs_review` reste consultable mais marqué non publiable ; un arrêt contrôlé affiche `budget_exceeded`, `timeout` ou `pricing_unavailable` avec son message ; `is_publishable` n'est jamais déduit de `final_status`. | Tests Node de formatage ; vérification visuelle sur un rapport `needs_review` et un arrêt budget. |
| **AC5** | **Localisation complète** : toutes les chaînes nouvelles existent en `fr`, `en` et `zh`, avec les mêmes variables `{var}` ; dates et nombres passent par `useRegionalFormat`. | `frontend/tests/i18n.test.js` (parité stricte) + recherche de clé manquante. |
| **AC6** | **Robustesse** : un `usage.json` absent, un `report_claims.json` absent, un rapport sans instantané ou une réponse 404/500 n'interrompent pas la vue ; un 409 (simulation occupée) affiche un message actionnable ; aucune promesse non gérée dans la console. | Tests Node des helpers sur entrées dégradées ; vérification visuelle des états d'erreur. |
| **AC7** | **Non-régression** : suite backend ≥ 1 939 tests, tests Node au vert, `pnpm --dir frontend build` réussi, aucune dépendance ajoutée, aucun secret dans les réponses consommées. | Exécution complète avant clôture. |

---

## Définition de fini

- [x] Endpoint `GET /api/report/profiles` implémenté dans `backend/app/api/report.py` et couvert par des tests hermétiques (aucun secret, ordre stable).
- [x] Fonctions pures `frontend/src/utils/reportComparison.js` (`evaluateComparability`, `diffSections`, formatage d'usage) et tests Node dédiés.
- [x] Composant de sélection d'historique intégré au Step 4, avec synchronisation de route et rechargement des panneaux.
- [x] Dialogue de régénération (profil, mode, confirmation) appelant `POST /api/report/generate`.
- [x] Panneau de comparaison (tableau factuel, verdict de comparabilité, diff par section, audits téléchargeables).
- [x] Affichage Fail-Safe des statuts (`needs_review`, `failed_validation`, `stop_reason`) et des métriques indisponibles.
- [x] Chaînes `fr`/`en`/`zh` à parité, formats régionaux respectés.
- [x] Suite backend complète, tests Node et build Vite au vert ; vérification visuelle consignée.
- [x] Story passée en `review` puis `done` après revue contradictoire BMAD 4 couches.

---

## Tâches

- [x] 1. Ajouter `GET /api/report/profiles` (catalogue `flash-medium`, `flash-high`, `deepseek-v4-pro`, `qwen3.8-max`, `gpt-6.1-sol`) et ses tests hermétiques dans `backend/tests/test_report_profiles_api.py`.
- [x] 2. Étendre `frontend/src/api/report.js` : `getReportHistory`, `getReportUsage`, `getReportClaims`, `getReportProfiles`.
- [x] 3. Créer `frontend/src/utils/reportComparison.js` (comparabilité, diff par section, formatage d'usage et de statut) et `frontend/tests/reportComparison.test.js`.
- [x] 4. Créer le sélecteur d'historique (liste, état courant, états vides, rapport en cours) et l'intégrer à `Step4Report.vue`.
- [x] 5. Créer le dialogue de régénération (profil, mode `replay_frozen`/`live`, confirmation, gestion 409/400).
- [x] 6. Créer le panneau de comparaison (tableau factuel, verdict, diff, audits) accessible depuis le Step 4.
- [x] 7. Synchroniser la sélection avec la route `/report/<report_id>` et recharger les données par rapport (qualité, usage, claims).
- [x] 8. Ajouter les clés `step4.*` en `fr`, `en`, `zh` et vérifier la parité.
- [x] 9. Vérifier la non-régression (pytest, tests Node, build Vite) et consigner la vérification visuelle.
- [x] 10. Exécuter la revue contradictoire BMAD 4 couches et consigner les conclusions.

---

## Notes de développement

1. **Source de vérité de l'historique** — `GET /api/report/simulation/<sim_id>/history` renvoie
   `data.reports[]` avec `report_id`, `created_at`, `completed_at`, `status`, `profile_id`,
   `replay_mode`, `evidence_snapshot_id`, `publication_status`, `is_publishable`,
   `total_claims`, `supported_claims`, `unsupported_claims`, `adoption_rate` et
   `usage_summary`. Le tri se fait côté client sur `created_at` (ISO 8601), avec repli
   stable sur `report_id` en cas d'égalité ou d'absence.

2. **Catalogue de profils** — `ReportLLMProfile.get_standard_profile(profile_id)` construit
   le profil à la demande ; l'endpoint énumère une liste d'identifiants explicite (pas de
   découverte dynamique) et sérialise via `to_dict()` (qui retire `api_key` et `base_url`).
   Un identifiant inconnu demandé à `/generate` doit rester un 400 explicite.

3. **Rejeu** — Le Step 4 ne propose `replay_frozen` que si le rapport sélectionné expose un
   instantané. Le mode `live` est un choix explicite : les entretiens live n'existent plus
   après la clôture d'OASIS, et la story 013-2 a précisément figé les preuves pour éviter
   cette confusion.

4. **Comparabilité** — `evaluateComparability(left, right)` compare d'abord
   `evidence_snapshot_id` ; s'il est identique et qu'une empreinte est disponible des deux
   côtés, elle doit être identique aussi. Sinon le verdict est « non comparable » avec des
   motifs lisibles (`snapshot absent`, `snapshot différent`, `empreinte différente`). Un
   même `simulation_id` ne suffit jamais : deux générations successives peuvent avoir capturé
   des preuves différentes.

5. **Télémétrie** — Le panneau lit `GET /api/report/<report_id>/usage`. Si le fichier est
   absent (rapport antérieur à 013-4), il retombe sur `usage_summary` de l'historique, puis
   affiche « indisponible ». `estimated_cost_usd` est une estimation issue d'une grille datée :
   le libellé le dit, et `pricing_available=false` interdit toute comparaison de coût.

6. **Statuts** — `publication_status` prime sur `final_status` pour les badges (rétrocompatibilité
   012-4). Un arrêt contrôlé se lit dans `stop_reason` (`budget_exceeded`, `timeout`,
   `pricing_unavailable`) et non dans le statut de progression, qui reste `failed`.

7. **Diff** — Le diff est calculé sur le Markdown assemblé (`markdown_content`) section par
   section. Les titres servent de clés ; une section absente d'un côté est marquée ajoutée
   ou supprimée. Les lignes sont normalisées (`\r\n` → `\n`, espaces de bord retirés) avant
   comparaison. Aucun rendu HTML du diff : du texte, pour éviter toute injection.

8. **Périmètre exclu** — pas de flux temps réel de la régénération (la vue navigue vers le
   nouveau `report_id`, qui expose déjà logs et progression), pas de campagne A/B automatisée
   (013-6), pas de recommandation de modèle.

9. **Secrets** — Le navigateur ne reçoit que `profile_id` et des métadonnées de modèle. Toute
   URL de passerelle reste côté serveur (`base_url_configured` seulement dans les manifestes).

10. **Divergence assumée sur la règle de comparabilité** — La règle écrite dans cette story
    comparait d'abord `evidence_snapshot_id`, l'identifiant d'instantané. **Or cet identifiant
    est un identifiant de capture, pas une adresse de contenu** : `EvidenceSnapshotService`
    le construit sur un `uuid.uuid4().hex[:12]` (`backend/app/services/evidence_snapshot_service.py`,
    `capture_snapshot`). Deux générations successives sur le même jeu de preuves figées
    portent donc **deux identifiants distincts pour une empreinte SHA-256 identique**.

    Appliquer la règle à la lettre aurait rendu **non comparables tous les couples A/B de
    l'Epic 013** — c'est-à-dire annulé la raison d'être du benchmark. La règle implémentée
    est donc : l'**empreinte SHA-256 prime** quand elle est exposée des deux côtés ; le
    `snapshot_id` ne sert que de repli quand l'empreinte manque. Ce choix a été **mesuré** :
    deux régénérations successives sur `sim_ea4f3cfe1028` ont produit
    `snap_f0e55dd0b705_20261020` et `snap_a97649816fd4_20261020` pour la **même** empreinte
    `57127e619a0ebd32…`, et l'IHM a affiché « Comparaison contrôlée : preuves identiques ».

    La story 013-6 (banc A/B) doit s'appuyer sur cette sémantique, pas sur l'identifiant
    d'instantané.

11. **Empreinte exposée par l'historique** — L'endpoint d'historique expose désormais
    `evidence_snapshot_sha256` en plus de `evidence_snapshot_id` (`ReportManager._snapshot_fields`).
    Sans cela, l'IHM devait redemander le détail de chaque rapport pour connaître l'empreinte ;
    l'historique reste ainsi la seule source de vérité, comme décidé au point 1.

12. **Un rapport corrompu n'interrompt plus l'historique** — `ReportManager.get_report`
    renvoyait l'exception de parsing JSON, ce qui faisait échouer en 500 tout
    `GET /api/report/simulation/<sim_id>/history` dès qu'un seul `meta.json` était tronqué
    (le cas réel s'est produit sur `uploads/reports/rep_1/meta.json`, résidu d'écriture de
    test). Le rapport illisible est désormais **écarté de l'historique avec un avertissement
    journalisé**, et l'historique répond 200 (AC6).

13. **Le sélecteur de version sort du flux défilant** — Le panneau droit défile pour suivre
    le dernier journal du ReportAgent ; le sélecteur de version aurait donc disparu en cours
    de génération. La zone défilante a été isolée (`.right-scroll`), le sélecteur reste
    visible en permanence au-dessus d'elle.

---

## Revue

Revue contradictoire **BMAD code-review à 4 couches** menée le 20 octobre 2026 sur
l'ensemble du diff de la story (backend + frontend + i18n + accessibilité), suivie d'une
**vérification visuelle sur la stack Docker de référence** (ADR 0006). Les 9 findings
retenus ont été corrigés et vérifiés ; la story est close (`done`).

### Findings retenus et corrigés (9)

| # | Gravité | Finding | Correction appliquée |
|---|---|---|---|
| P1 | Haute | `evaluateComparability` ne lisait que `evidence_snapshot_id` / `evidence_snapshot_sha256` : sur les versions assemblées par `buildComparisonVersion` (qui exposent `snapshotId` / `sha256`), le verdict retombait systématiquement sur « preuves non figées ». **Un test Node ne l'a pas vu** : il testait la forme brute, pas la forme réellement consommée par l'IHM. | `readEvidenceFingerprint` accepte désormais les trois formes (entrée d'historique, détail de rapport, version assemblée) ; idem pour l'identifiant de simulation. **4 tests Node de régression ajoutés** (`an assembled comparison version is judged on its own fingerprint` et consorts). **Bug trouvé par la vérification visuelle sur la stack Docker, pas par les tests.** |
| P1 | Haute | Un `meta.json` de rapport tronqué faisait échouer en 500 tout l'historique d'une simulation : l'IHM perdait le sélecteur de version à cause d'un rapport étranger corrompu (cas réel : `uploads/reports/rep_1/meta.json`). | `ReportManager.get_report` renvoie `None` avec un avertissement journalisé au lieu de propager l'exception ; le plan illisible et le statut inconnu sont traités de la même façon. 3 tests hermétiques ajoutés. |
| P2 | Moyenne | La règle de comparabilité écrite dans la story (égalité des `snapshot_id`) rendrait **tous** les couples A/B non comparables, l'identifiant étant un uuid de capture et non une adresse de contenu. | Règle réécrite : l'empreinte SHA-256 prime, le `snapshot_id` n'est qu'un repli. Divergence consignée au point 10 des Notes de développement et prouvée par deux régénérations réelles. |
| P2 | Moyenne | Le sélecteur de version était emporté par le défilement automatique du panneau droit (le `scrollTop` de suivi des journaux le faisait passer sous le bord haut). | Isolation de la zone défilante (`.right-scroll`) ; le sélecteur reste visible. Constaté sur la stack Docker, pas par les tests. |
| P2 | Moyenne | `POST /api/report/generate` acceptait un `profile_id` inconnu et retombait **silencieusement** sur le modèle global : l'IHM aurait affiché un benchmark « flash-high » sur un modèle qui n'a jamais été exécuté. | Rejet explicite en 400, avec la liste des profils disponibles. Test hermétique ajouté. |
| P3 | Basse | Le catalogue de profils était dupliqué entre `ReportLLMProfile.get_standard_profile` et l'endpoint : une divergence aurait pu exposer un profil inexistant ou en cacher un. | Source unique `STANDARD_PROFILE_IDS`, catalogue interne bâti par `_build_standard_catalog()`, exhaustivité gardée par un test. |
| P3 | Basse | Les ressources optionnelles (usage, claims, qualité) déclenchaient un `console.error` pour chaque 404 attendu — le journal ceases d'être un signal. | Option `suppressErrorLog` sur l'intercepteur Axios, activée sur ces trois ressources. Le 404 reste un état normal, pas une erreur. |
| P3 | Basse | Le sélecteur de comparaison exigeait deux clics et une manipulation de `<select>` avant d'être utilisable. | La version à comparer est pré-positionnée sur la version la plus récente autre que la version courante. |
| P3 | Basse | La vérification visuelle en français imposait de patcher le conteneur (le sélecteur de langue natif n'était pas pilotable par l'outil). | Patch temporaire **dans le conteneur uniquement**, puis restauration et reconstruction de l'image. **Le dépôt n'a jamais été modifié pour cette vérification.** |

### Points différés

| # | Point | Pourquoi différé |
|---|---|---|
| D1 | La suite de tests backend écrit encore dans `backend/uploads/` (projets, `state.json`, `run_state.json`) : c'est la cause de la pollution `rep_1` constatée ci-dessus. | Hygiène de test hors périmètre de la story 013-5 ; à traiter dans une story dédiée (le filet est hermétique *sur ses assertions*, mais pas sur le système de fichiers). |
| D2 | Le diff par section est un diff de lignes (LCS) sur le Markdown assemblé, sans diff sémantique de section. | Suffisant pour l'usage prévu (voir ce qui change entre deux versions). Un diff structurel section par section est un chantier distinct. |
| D3 | Le comparateur ne propose pas encore le regroupement par « même profil, effort différent » (la colonne porte le `profile_id`, pas l'effort, quand l'effort est inconnu). | La campagne A/B de la story 013-6 fournit la grille de score ; l'IHM n'a pas à deviner la méthode d'analyse. |

### Rejets motivés

| Finding | Motif du rejet |
|---|---|
| « Comparer devrait aussi proposer les rapports d'autres simulations » | Hors périmètre : la comparaison A/B porte sur une même simulation, c'est la condition du rejeu figé (PRD §7). |
| « Le comparateur devrait désigner un modèle gagnant » | Refusé par construction : l'IHM expose des faits, l'arbitrage appartient à la revue aveugle de la story 013-6 (décision d'ingénierie n° 7). |
| « Ajouter une dépendance de diff (jsdiff) » | Refusé : le diff est une fonction pure de ~60 lignes, testable sans dépendance (KISS, §2.5). |

---

## Notes de complétion

**Livraison.** L'implémentation est complète et vérifiée sur la stack Docker de référence
(ADR 0006) le 20 octobre 2026.

### Ce qui a été livré

**Backend**
- `GET /api/report/profiles` (`backend/app/api/report.py`) : catalogue serveur, liste blanche
  stricte de 9 champs, `base_url_configured` en booléen, aucun secret, ordre déterministe par
  `profile_id`.
- `POST /api/report/generate` : rejet explicite (400) d'un `profile_id` inconnu.
- `ReportManager._snapshot_fields` + `evidence_snapshot_sha256` dans les entrées d'historique
  (nouvelles et legacy), et dans le repli disque.
- `ReportManager.get_report` : robustesse face à un `meta.json` illisible (retour `None` +
  avertissement journalisé) au lieu de casser tout l'historique.
- `ReportLLMProfile.STANDARD_PROFILE_IDS` + `standard_profile_ids()` + `_build_standard_catalog()`.

**Frontend**
- `frontend/src/utils/reportComparison.js` : fonctions pures `sortReportHistory`,
  `readEvidenceFingerprint`, `readSimulationId`, `evaluateComparability`, `diffSections`,
  `parseMarkdownSections`, `describeStopReason`, `summarizeUsage`, `buildComparisonVersion`,
  `computeDelta`, `isRunningReport`, `shortReportId`.
- `frontend/src/components/ReportHistorySelector.vue`, `ReportRegenerateDialog.vue`,
  `ReportComparisonPanel.vue` (trois composants nouveaux, aucune dépendance ajoutée).
- `frontend/src/components/Step4Report.vue` : barre de version (sélecteur + actions + bandeau
  de télémétrie de la version courante), dialogue de régénération, panneau de comparaison,
  rechargement par `report_id`, isolation de la zone défilante.
- `frontend/src/api/report.js` : `getReportHistory`, `getReportUsage`, `getReportClaims`,
  `getReportProfiles`.
- `frontend/src/api/index.js` : option `suppressErrorLog` pour les ressources optionnelles.
- `locales/{fr,en,zh}.json` : 90 clés `step4.*` nouvelles, parité stricte vérifiée par
  `frontend/tests/i18n.test.js` (clés **et variables `{var}`** sur les trois dictionnaires).
  *(Le décompte initial annonçait 78 : c'était le nombre de lignes ajoutées au JSON,
  pas le nombre de clés — 90 clés feuilles, mesuré. Corrigé en 2e revue BMAD.)*

**Tests**
- `backend/tests/test_report_profiles_api.py` : 27 tests hermétiques (catalogue, absence de
  secret, ordre stable, rejet du profil inconnu, empreinte dans l'historique, robustesse face
  aux rapports corrompus, alignement du profil client sur le catalogue, alias de passerelle).
- `frontend/tests/reportComparison.test.js` : 33 tests Node (tri, comparabilité, diff, usage
  honnête, motifs d'arrêt, delta, version assemblée).
- `frontend/tests/i18n.test.js` : 10 tests, dont **+1** de parité des variables `{var}` sur les
  trois dictionnaires (vérifié par mutation : la suppression d'une variable fait échouer le
  test).

### Vérification visuelle (stack Docker de référence)

Parcours effectué sur `http://localhost:3000/report/<report_id>` avec la stack
`docker compose` à jour (images reconstruites), locale `fr` :

| Vérification | Résultat |
|---|---|
| Sélecteur de version | 4 versions listées, tri chronologique, version courante mise en évidence, badge « Rejeu figé » / « Rejeu live », badge « Certification refusée » / « completed » |
| Navigation par l'historique | clic sur une version → URL `/report/<report_id>` mise à jour, contenu rechargé |
| Dialogue de régénération | catalogue des 5 profils (modèle, fournisseur, effort, plafonds), aucun secret ; `replay_frozen` proposé **par défaut** quand un instantané existe, `live` désactivé et remplacé par un avertissement quand il n'en existe pas ; `live` exige une case de confirmation explicite, et le bouton d'envoi reste désactivé tant qu'elle n'est pas cochée |
| Régénération réelle | `POST /api/report/generate` avec `profile_id` + `replay_mode` + `force_regenerate` → nouveau `report_id` → navigation automatique ; l'ancienne version reste listée et intacte |
| Comparaison | verdict « **Comparaison contrôlée : preuves identiques** » (bannière verte) sur deux rapports dont les `snapshot_id` diffèrent mais dont l'empreinte SHA-256 est identique ; verdict « Comparaison non contrôlée » avec motif sur deux rapports sans instantané |
| Tableau factuel | modèle, effort demandé/effectif, mode de rejeu, statut de publication, affirmations vérifiées/total, tokens, durée d'inférence, temps mural, coût estimé, motif d'arrêt ; écarts bruts en colonne « Écart » |
| Honnêteté de l'affichage | rapport sans `usage.json` → « indisponible » (jamais `0 $`) ; coût étiqueté « estimation » ; `Certification refusée` affiché pour un rapport `failed_validation` ; bandeau de télémétrie de la version courante : tokens, durée d'inférence, temps mural, coût, affirmations vérifiées/total — tous en « indisponible » quand la donnée manque |
| Diff par section | sections listées avec statut (ajoutée / supprimée / modifiée / identique), lignes en texte brut, repli par `<details>` |
| Téléchargement d'audit | un lien par version |

### Écarts avec le plan

1. **Règle de comparabilité réécrite** (voir Points 10 des Notes de développement et P2 de la
   revue) : l'empreinte SHA-256 prime sur l'identifiant d'instantané. Décision prise parce que
   la règle littérale annulait le benchmark A/B, et **prouvée par deux régénérations réelles**.
2. **Le catalogue a son propre endpoint** (`GET /api/report/profiles`), conformément à la
   décision d'ingénierie n° 2 de la Définition de prêt.
3. **L'historique expose l'empreinte** en plus de l'identifiant d'instantané : sans cela,
   l'IHM ne pouvait pas décider de la comparabilité à partir de l'historique seul.
4. **Le sélecteur de version est sorti du panneau défilant** : structure `.right-scroll`
   introduite dans `Step4Report.vue`. Le `ref="rightPanel"` a été déplacé sur la zone
   défilante, ce qui préserve le suivi automatique des journaux.
5. **Quatre tests Node de régression** ont été ajoutés après la revue pour couvrir la forme
   « version assemblée » que l'IHM consomme réellement.

### Ce que la story ne fait pas

- Elle ne compare pas des rapports de simulations différentes (hors périmètre du rejeu figé).
- Elle ne désigne pas de modèle gagnant et ne colourie aucun écart (décision n° 7).
- Elle ne lance pas la campagne A/B (story 013-6) et ne produit pas de rapport de benchmark.
- Elle ne supprime pas le rapport le plus récent : `latest_report_id` reste le pointeur, et
  l'historique conserve toutes les versions.

### Effets de bord observés

Trois rapports ont été **réellement générés** pendant la vérification visuelle sur
`sim_ea4f3cfe1028` : `report_262d6725a176` (`live` / `deepseek-v4-pro`, échec rapide de la
passerelle), `report_1297337e386b` (`replay_frozen` / `flash-medium`) et
`report_dc378a75c53f` (`replay_frozen` / `deepseek-v4-pro`). Les deux premiers portent
l'empreinte commune `57127e619a0ebd32…` avec des identifiants d'instantané différents : ce sont
eux qui rendent la comparaison contrôlée reproductible. Les trois se sont terminés en
`failed_validation` (barrière fail-closed, 210 affirmations, 0 vérifiée) : **le comparateur
montre des faits, pas une garantie de succès**. Ces artefacts restent dans
`backend/uploads/` (gitignoré) ; ils sont le témoin de la vérification.

### 2e revue BMAD contradictoire (20 octobre 2026) — 23 correctifs appliqués

Une seconde revue à quatre couches a été menée sur le diff `11e2fc8..f3cd648`
(4 267 lignes, 22 fichiers). **23 correctifs appliqués**, 2 décisions
arbitrées par l'utilisateur, 3 points différés, 8 constats rejetés (dont 4
`false`, réfutés par lecture du code). Les deux défauts les plus lourds
étaient **invisibles aux tests** :

1. **Le dialogue de régénération interdisait le rejeu figé dès la deuxième
   génération.** `currentHasSnapshot` ne regardait que l'entrée de la version
   courante ; or, juste après une régénération, la version courante est
   l'entrée *provisoire*, qui ne porte aucun champ d'instantané. Résultat :
   `replay_frozen` désactivé et `live` présélectionné — c'est-à-dire des
   rapports **non comparables**, ce qui annulait le parcours A/B de l'Epic 013
   dès la seconde génération. La règle est désormais portée par la
   *simulation* (au moins une version de l'historique porte un instantané).
2. **Un rapport corrompu inscrit dans `report_history.json` restait listé.**
   `results.append(item)` était sorti du `if rep:` de
   `list_reports_by_simulation` : l'entrée servait, empreinte périmée
   comprise, alors que `GET /api/report/<id>` répond 404 pour elle. Le
   sélecteur proposait donc une version qui ne s'ouvrait pas, et le verdict de
   comparabilité pouvait fonder une « comparaison contrôlée » sur un rapport
   sans contenu. La revendication « le rapport illisible est écarté de
   l'historique » n'était vraie que pour la branche « parcours du disque ».
   Le test qui supposedly la prouvait n'inscrivait jamais le rapport à l'index.

**Ce que la revue a refusé de casser.** Trois constats portaient sur la règle
de comparabilité : `evaluateComparability` déclare comparable deux rapports
dont le `snapshot_id` est identique, sans empreinte commune. C'est **correct** :
`snapshot_id` est un uuid **par capture** (`evidence_snapshot_service.py:235`),
donc l'égalité de cet identifiant implique l'égalité de la capture, donc du
jeu de preuves. La règle « l'empreinte prime » ne s'applique qu'à l'autre
sens — deux captures distinctes du même jeu de preuves — que le code traite
bien. Aucun correctif n'a donc été appliqué sur ce point, et le test Node qui
verrouille ce comportement a été conservé tel quel.

**Deux décisions de l'utilisateur, devenues des correctifs.** (a) Le chemin
`llm_profile` en ligne est **aligné sur le catalogue** : `base_url` et
`api_key` y sont refusés, le mode de facturation ne peut pas être déclassé,
les plafonds ne peuvent pas être relevés, et le `profile_id` est **dérivé** du
couple (modèle, effort) — un client ne peut plus étiqueter un job
« flash-high » quand l'effort retenu est « medium ». (b) `provider_id`
désigne désormais **la passerelle qui a servi** (alias dérivé du `base_url`),
et non l'éditeur du modèle : sur la stack de référence, `deepseek-v4-pro`
servi par Antigravity ne s'annonce plus « opencode-go ».

**Filet global.** 1 971 tests backend au vert (+16) et 43 tests Node frontend
au vert (+5), `ruff` propre, `validate_plans.py` propre, build Vite réussi.

---

## Revue BMAD contradictoire — 2e passe (20 octobre 2026)

Diff revu : `11e2fc8..f3cd648` (4 267 lignes, 22 fichiers). Quatre couches
indépendantes (Blind Hunter, Edge Case Hunter, Verification Gap Reviewer,
Acceptance Auditor), tous les constats vérifiés à la source avant verdict.

### Review Findings

**Décisions à trancher (2) — tranchées le 20 octobre 2026, devenues des correctifs**

- [x] [Review][Decision] Le chemin `llm_profile` en ligne laisse le navigateur fixer `base_url` et `api_key` — **tranché : aligner sur le catalogue.** `ReportLLMProfile.from_dict()` accepte `base_url` et `api_key` venus du client (`backend/app/models/report_llm_profile.py:118-119`), et `POST /api/report/generate` accepte ce corps (`backend/app/api/report.py:83-90`). Le commentaire posé par ce diff sur le catalogue « fermé » (« afin que le navigateur ne puisse jamais élargir la surface d'exécution par lui-même ») est donc contredit par le code : un client peut désigner n'importe quelle passerelle OpenAI-compatible et y faire transiter le paquet de preuves entier (documents, personas, événements observés). La décision d'ingénierie n° 3 de la Définition de prêt garde pourtant ce chemin « pour les appels avancés ». **Arbitrage : le chemin inline est conservé, mais aligné sur le catalogue** — `base_url` et `api_key` y sont refusés ; seuls `model`, `reasoning_effort`, `billing_mode` et les plafonds restent acceptables, et ils sont validés contre le catalogue.
- [x] [Review][Decision] `provider_id` est affiché comme un fait alors qu'il est codé en dur — **tranché : `provider_id` désigne la passerelle qui a servi.** Les trois profils non-flash portent `provider_id="opencode-go"` en dur, tandis que les profils flash déduisent `"antigravity-local"` d'un test de sous-chaîne sur `base_url` (`backend/app/models/report_llm_profile.py:169-216`). Or les cinq profils partagent le **même** `base_url`. Sur la stack de référence (passerelle Antigravity), `deepseek-v4-pro` est donc étiqueté « opencode-go » alors qu'il est servi par Antigravity — et l'IHM affiche « modèle · fournisseur » comme une vérité (`frontend/src/components/ReportRegenerateDialog.vue:59`). **Arbitrage : `provider_id` devient l'alias de la passerelle réellement configurée**, dérivé du `base_url` — la même notion que l'alias déjà porté par le manifeste de la 013-4 — de sorte que l'IHM affiche un fait vrai : « qui a produit ce rapport ».

**Correctifs (23)**

- [x] [Review][Patch] Le chemin `llm_profile` en ligne est aligné sur le catalogue : `base_url` et `api_key` venus du client sont refusés [backend/app/models/report_llm_profile.py:118-119]
- [x] [Review][Patch] `provider_id` devient l'alias de la passerelle réellement configurée, dérivé du `base_url` [backend/app/models/report_llm_profile.py:169-216]
- [x] [Review][Patch] Le dialogue de régénération interdit le rejeu figé dès la deuxième génération [frontend/src/components/Step4Report.vue:609-613]
- [x] [Review][Patch] Un rapport corrompu inscrit dans `report_history.json` reste listé, avec son empreinte périmée [backend/app/services/report_agent.py:4585-4611]
- [x] [Review][Patch] Le garde-fou 400 du `profile_id` inconnu ne s'applique que si aucun `llm_profile` n'accompagne la requête [backend/app/api/report.py:83-106]
- [x] [Review][Patch] `suppressErrorLog` éteint aussi les 500, alors que le motif retenu était « le 404 est un état normal » [frontend/src/api/index.js:31-46]
- [x] [Review][Patch] L'échec de chargement du catalogue de profils est avalé et affiché comme un état faux [frontend/src/components/Step4Report.vue:710-719]
- [x] [Review][Patch] La version à comparer peut être pré-positionnée sur un rapport en cours de génération [frontend/src/components/Step4Report.vue:605-707]
- [x] [Review][Patch] `is_publishable`, `unsupported_claims`, `contradicted_claims` et `verification_ratio` sont calculés puis jamais affichés [frontend/src/utils/reportComparison.js:485-492]
- [x] [Review][Patch] Le panneau de comparaison n'a pas de hauteur bornée et écrase la zone des journaux [frontend/src/components/ReportComparisonPanel.vue:239-247]
- [x] [Review][Patch] Le statut brut non localisé s'affiche dans le sélecteur de versions [frontend/src/components/ReportHistorySelector.vue:65-67]
- [x] [Review][Patch] `parseMarkdownSections` n'est pas conscient des blocs de code délimités par des accents graves [frontend/src/utils/reportComparison.js:197-217]
- [x] [Review][Patch] Le dialogue présélectionne le profil par ordre alphabétique, pas celui de la version courante [frontend/src/components/ReportRegenerateDialog.vue:161-162]
- [x] [Review][Patch] Le message d'un arrêt contrôlé n'existe pas dans le contrat de télémétrie [backend/app/models/report_usage.py:411-437]
- [x] [Review][Patch] La télémétrie affichée peut appartenir à une autre version [frontend/src/components/Step4Report.vue:723-735]
- [x] [Review][Patch] La liste des versions est triée du plus ancien au plus récent : la version courante peut être hors écran [frontend/src/utils/reportComparison.js:103-114]
- [x] [Review][Patch] Le tri de l'historique compare des chaînes de dates de formats hétérogènes [backend/app/services/report_agent.py:2402]
- [x] [Review][Patch] Le repli sur `usage_summary` annoncé par la note 5 des Notes de développement n'existe pas [frontend/src/utils/reportComparison.js:459]
- [x] [Review][Patch] Le coût peut faire tomber le panneau de comparaison sur une devise invalide [frontend/src/components/ReportComparisonPanel.vue:159-168]
- [x] [Review][Patch] L'URL d'audit est dupliquée et rendue même quand aucune archive n'existe [frontend/src/components/ReportComparisonPanel.vue:137-140]
- [x] [Review][Patch] Clés Vue dupliquées possibles dans la liste des sections de diff [frontend/src/components/ReportComparisonPanel.vue:73]
- [x] [Review][Patch] Le dialogue déclare `aria-modal="true"` sans piège de focus [frontend/src/components/ReportRegenerateDialog.vue:11]
- [x] [Review][Patch] Un `meta.json` dont le plan est illisible fait disparaître un rapport dont le Markdown est intact [backend/app/services/report_agent.py:4404-4423]

**Différés (3)**

- [x] [Review][Defer] Le décompte i18n est faux : 74 clés `step4.*` nouvelles, pas 78 [docs/STATUS.md] — deferred: mesuré (50 → 124 clés feuilles sous `step4` dans `locales/{fr,en,zh}.json`) ; le « 78 » compte les lignes ajoutées au JSON, pas les clés. Le correctif touche des fichiers de contexte d'agent et des documents de référence.
- [x] [Review][Defer] `AGENTS.md` se contredit sur le statut de la story 013-5 [AGENTS.md:558] — deferred: la ligne 558 dit encore « stories 013-1 à 013-4 `done`, 013-5 `review` » alors que les lignes 34 et 48 la donnent `done`. Correction dans un fichier de contexte d'agent.
- [x] [Review][Defer] La story a sauté l'état `review` [docs/plans/013-benchmark-llm-report-replay/story-013-5.md] — deferred: le diff bascule `statut: in-progress` → `statut: done` en un seul commit, et `AGENTS.md` §2.8 interdit le saut. Le geste est un fait d'historique, non rattrapable par un correctif de code ; l'état `review` n'existe dans aucun fichier.

### Rejected

- **« `evaluateComparability` déclare comparable sur le seul identifiant d'instantané, contrary to AC3 »** — `false`. `snapshot_id` vaut `f"snap_{uuid.uuid4().hex[:12]}_{date_suffix}"` (`backend/app/services/evidence_snapshot_service.py:235`) : un uuid **par capture**. Deux captures distinctes ne partagent jamais cet identifiant, donc l'égalité de `snapshot_id` implique l'égalité de la capture, donc du jeu de preuves. La branche `HASH_UNAVAILABLE` est correcte, et le panneau affiche de surcroît la réserve (« Empreinte SHA-256 non exposée des deux côtés : l'identité repose sur le seul identifiant d'instantané »).
- **« L'empreinte SHA-256 ne prime pas, car le contrôle d'instantané précède la comparaison des empreintes »** — `false`. `EvidenceSnapshot.to_dict()` est un `asdict()` : `snapshot_id` et `sha256_hash` sont toujours présents ensemble ; les entrées d'historique aussi (`ReportManager._snapshot_fields` les pose ensemble). La branche `SNAPSHOT_ABSENT` n'est donc pas atteignable avec une empreinte disponible d'un seul côté.
- **« L'AC3 et la note 4 décrivent encore l'ancienne règle de comparabilité (égalité du `snapshot_id` d'abord) »** — rejeté : le correctif est l'édition de la spec sous revue. Le fond est vrai et sera traité dans la story 013-6, qui doit s'appuyer sur la sémantique d'empreinte.
- **« La story passe de `in-progress` à `done` sans passer par `review` »** — rejeté : le correctif est l'édition de la spec sous revue. Le fait est consigné en différé ci-dessus.
- **« La distinction `replay_frozen` / `best_effort` du PRD source n'est pas implémentée »** — `false`. Le PRD source (V1, §10) l'énonce comme option ; le serveur n'a jamais implémenté que `('live', 'replay_frozen')` (story 013-2) et rejette proprement tout autre mode en 400. L'écart est un choix de périmètre assumé, pas un oubli.
- **« La colonne « Écart » est signée sans indiquer le sens de la soustraction »** — `low`, rejeté : le module `computeDelta` documente « droite − gauche », le tableau n'indique ni couleur ni gagnant, et ajouter une mention de sens est un ajout de surface i18n sans gain de lecture.
- **« Un rapport en échec laisse une entrée provisoire « En cours » fantôme dans le sélecteur »** — `low`, rejeté : le serveur inscrit l'entrée `failed` à l'index d'historique et la purge fusionne les doublons dès le rechargement suivant. La fenêtre d'affichage est transitoire et le serveur reste la seule source de vérité.
- **« `ReportManager.get_report` efface le rapport quand seul `outline` est illisible »** — retenu sous forme réduite : le rapport disparaît en effet, mais la cause est plus étroite que « l'outline illisible » (il faut un `summary` absent ou un `sections` non conforme) ; c'est traité dans les correctifs.

