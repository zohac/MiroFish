---
id: "013-5"
epic: "013"
titre: "Interface Vue 3 Step 4 : sélecteur de rapport, régénération et comparaison"
statut: in-progress
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

- [ ] Endpoint `GET /api/report/profiles` implémenté dans `backend/app/api/report.py` et couvert par des tests hermétiques (aucun secret, ordre stable).
- [ ] Fonctions pures `frontend/src/utils/reportComparison.js` (`evaluateComparability`, `diffSections`, formatage d'usage) et tests Node dédiés.
- [ ] Composant de sélection d'historique intégré au Step 4, avec synchronisation de route et rechargement des panneaux.
- [ ] Dialogue de régénération (profil, mode, confirmation) appelant `POST /api/report/generate`.
- [ ] Panneau de comparaison (tableau factuel, verdict de comparabilité, diff par section, audits téléchargeables).
- [ ] Affichage Fail-Safe des statuts (`needs_review`, `failed_validation`, `stop_reason`) et des métriques indisponibles.
- [ ] Chaînes `fr`/`en`/`zh` à parité, formats régionaux respectés.
- [ ] Suite backend complète, tests Node et build Vite au vert ; vérification visuelle consignée.
- [ ] Story passée en `review` puis `done` après revue contradictoire BMAD 4 couches.

---

## Tâches

- [ ] 1. Ajouter `GET /api/report/profiles` (catalogue `flash-medium`, `flash-high`, `deepseek-v4-pro`, `qwen3.8-max`, `gpt-6.1-sol`) et ses tests hermétiques dans `backend/tests/test_report_profiles_api.py`.
- [ ] 2. Étendre `frontend/src/api/report.js` : `getReportHistory`, `getReportUsage`, `getReportClaims`, `getReportProfiles`.
- [ ] 3. Créer `frontend/src/utils/reportComparison.js` (comparabilité, diff par section, formatage d'usage et de statut) et `frontend/tests/reportComparison.test.js`.
- [ ] 4. Créer le sélecteur d'historique (liste, état courant, états vides, rapport en cours) et l'intégrer à `Step4Report.vue`.
- [ ] 5. Créer le dialogue de régénération (profil, mode `replay_frozen`/`live`, confirmation, gestion 409/400).
- [ ] 6. Créer le panneau de comparaison (tableau factuel, verdict, diff, audits) accessible depuis le Step 4.
- [ ] 7. Synchroniser la sélection avec la route `/report/<report_id>` et recharger les données par rapport (qualité, usage, claims).
- [ ] 8. Ajouter les clés `step4.*` en `fr`, `en`, `zh` et vérifier la parité.
- [ ] 9. Vérifier la non-régression (pytest, tests Node, build Vite) et consigner la vérification visuelle.
- [ ] 10. Exécuter la revue contradictoire BMAD 4 couches et consigner les conclusions.

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

---

## Revue

Aucune revue contradictoire menée à ce stade : la story est en cours de démarrage. La revue
BMAD 4 couches sera consignée ici après implémentation, avec les findings retenus, les patches
appliqués et les points différés.

---

## Notes de complétion

Aucune complétion consignée à ce stade. La story a été rédigée le 20 octobre 2026, après la
clôture de la story 013-4, pour préparer la suite de l'Epic 013 ; la Définition de prêt sera
revérifiée au moment de l'implémentation (filet de tests, disponibilité du catalogue et
instantanés de preuves réels).
