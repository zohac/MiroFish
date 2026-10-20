---
id: "013-6"
epic: "013"
titre: "Banc de benchmark contrôlé A/B et qualification globale de l'Epic 013"
statut: in-progress
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 013-6 — Banc de benchmark contrôlé A/B et qualification globale de l'Epic 013

**Lot E (qualification), priorité P0.** En tant qu'architecte d'évaluation de MiroFish, je veux
soumettre deux variantes de rédaction du `ReportAgent` — même jeu de preuves figées, même code
vérificateur, seul l'effort de raisonnement du modèle change — à une **grille de score figée et
purement mécanique**, afin de mesurer ce que l'effort de raisonnement change réellement dans un
rapport, sans jamais confondre la qualité du modèle avec un défaut du vérificateur.

Cette story répond à l'exigence fonctionnelle **FR-10** du [PRD de l'epic](prd.md) (banc
d'orchestration global A/B) et sert le critère de sortie **C7** (rapport formel de qualification
consignant la comparaison contrôlée `gemini-3.8-flash` `medium` vs `high` sur R7). Elle consomme
les capacités livrées par les stories 013-1 à 013-5 et clôt l'Epic 013 au sens de son critère
**C8** (non-régression).

Elle rend possible : une campagne rejouable, chiffrée, bornée en coût, et **non concluante
quand les preuves ne permettent pas de conclure**. Elle refuse : désigner un « modèle gagnant »,
corriger le code vérificateur entre deux variantes, relancer OASIS, et conclure à la supériorité
d'un effort de raisonnement à partir d'une seule génération par variante.

**Traçabilité vers l'epic.** Cette story porte le critère de sortie **C7** de l'Epic 013
(benchmark A/B documenté) par les AC1 à AC11, et le critère **C8** (non-régression globale) par
l'AC12. Elle satisfait l'exigence fonctionnelle **FR-10** du PRD de l'epic (banc d'orchestration
global A/B) par l'ensemble du périmètre, et les NFR-1 (généricité : les profils viennent du
catalogue, aucun modèle en dur), NFR-3 (concurrence : les variantes sont séquentielles et
l'empreinte est recontrôlée entre chacune) et NFR-4 (zéro fuite de secret : AC12). Elle sert les
FR-08 (`dry_run`) et FR-11 (export) du PRD source par l'AC2 et par les livrables JSON + Markdown.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :

  **Le banc de mesure.** Un script autonome orchestre une campagne : il capture l'empreinte des
  preuves figées, exécute chaque variante demandée sur cette simulation, relit les artefacts
  produits, calcule une grille de score figée et écrive un rapport formel versionné.

  - **Empreinte des preuves** : `EvidenceSnapshotService(simulation_id).capture_snapshot(strict=True)`
  produit le `sha256_hash` du jeu de preuves rejoué. Il est capturé **avant** la première
  variante et comparé **après chaque variante**. Toute divergence exclut la variante du
  comparatif.
  - **Variante** : un couple (profil LLM du catalogue, nombre de répétitions). Les profils viennent
  de `ReportLLMProfile.standard_profile_ids()` — **jamais une liste écrite en dur dans le
  banc** (NFR-1 de l'epic).
  - **Grille de score** : une liste **fermée** de métriques, toutes derivatives mécaniquement des
  artefacts d'un rapport. Aucune n'est une interprétation. La grille est **versionnée** et sa
  version est écrite dans le rapport : elle ne change pas au milieu d'une campagne.
  - **Rapport formel** : un fichier Markdown versionné dans le dossier de plan, écrit par le banc
  lui-même (jamais rédigé à la main comme celui de l'Epic 004), accompagné d'une charge utile
  JSON machine.

  **Les invariants — ce que le banc ne peut pas faire.**

  - **Jamais de verdict de supériorité.** Le rapport compare des chiffres côte à côte ; il ne
  désigne aucun « meilleur » modèle et ne colore aucun écart. L'arbitrage appartient à la revue
  aveugle (décision d'ingénierie n° 9).
  - **Jamais de correction du code entre deux variantes.** Toute modification du code
  vérificateur entre la variante A et la variante B annule la comparaison : le rapport compare
  alors deux systèmes différents. Le banc recontrôle donc l'empreinte des preuves et l'état du
  graphe après chaque variante, et **exclut** toute variante dont l'un des deux a changé.
  - **Jamais de dénominateur nul traité comme un succès.** Si le nombre d'assertions d'action est
  nul, le taux de vérification des actions vaut `null` et la couverture est marquée en échec —
  jamais `100 %`.
  - **Jamais de métrique inventée.** Une métrique absente des artefacts vaut `null` et s'affiche
  « indisponible ». Le coût estimé reste une estimation, jamais une facture.
  - **Jamais de secret dans la sortie.** Ni clé d'API, ni URL de passerelle, ni prompt, ni
  contenu de message brut dans le rapport, le JSON ou la paire anonymisée.

  **Ce que le banc n'est pas.** Il ne relance pas OASIS, ne rejoue pas de rounds, ne reconstruit
  pas de graphe, ne compare pas deux simulations différentes, et ne remplace pas la revue humaine :
  il prépare le matériau d'une revue aveugle et l'outille, il ne la fait pas à la place de
  l'humain.

- [x] **Documents consultés** :

  - [PRD de l'epic](prd.md) : §3 (objectifs 2, 3, 5), §4 (FR-10), §5 (NFR-1, NFR-3, NFR-4).
  - [Architecture de l'epic](architecture.md) : §2.2 (`EvidenceSnapshot`), §2.3 (`ReportUsageMetrics`),
  §4 (isolation multi-rapports), §5 (mode replay figé).
  - [PRD source](../../PRD-MiroFish-benchmark-LLM-ReportAgent-replay-2026-10-19.md) : §7 (protocole
  A/B, phases 0 à 3), §8 (mesures de qualité, règle du dénominateur nul), §9 (FR-08 `dry_run`,
  FR-11 export), §10 (Story 013-6 et son DoD), §11 (AT-02, AT-03, AT-04, AT-12), §12.5 (grille
  de revue humaine aveugle).
  - [Hub de l'epic](epic-013.md) : FR-10, C2, C7, C8.
  - [Story 013-2](story-013-2.md) : contrat `EvidenceSnapshot`, `ReplayNotReproducibleError`, ensemble
  canonique des fichiers de preuves et règle d'empreinte SHA-256.
  - [Story 013-4](story-013-4.md) : contrat `ReportUsageMetrics`, `PricingTable`, champ `billing_mode`
  (`auto` / `free` / `metered`), plafonds `max_total_cost_usd` / `max_wall_seconds`.
  - [Story 013-5](story-013-5.md) : règle de comparabilité fondée sur l'empreinte SHA-256, bandeau de
  télémétrie, honnêteté d'affichage.
  - `backend/app/services/evidence_snapshot_service.py` : `EvidenceSnapshotService.capture_snapshot(strict=True)`,
  `gather_evidence_files`, `compute_sha256_footprint`, `ReplayNotReproducibleError`.
  - `backend/app/services/report_agent.py` : `ReportAgent.__init__`, `ReportAgent.generate_report(report_id=...)`,
  `ReportManager.save_report`, `ReportManager._get_report_claims_path`, `_get_cohort_coverage_path`,
  `_get_quality_path`, `_get_usage_path`.
  - `backend/app/models/report_claim.py` : `ReportClaimRegistry.load_from_file`, propriétés
  `total_claims`, `verified_claims`, `unsupported_claims`, `contradicted_claims`, `verification_ratio`.
  - `backend/app/models/cohort_coverage.py` : `CohortCoverageTable.load_from_file`, propriétés
  `total_members`, `silent_members`, `adoption_rate`.
  - `backend/app/models/report_quality.py` : `QualityGateResult.load_from_file`, `publication_status`,
  `is_publishable`, `final_status`.
  - `backend/app/models/report_usage.py` : `ReportUsageMetrics.load_from_file`, `summary()`,
  `CallUsageRecord` (sans `cached_tokens` ni `finish_reason` — voir décision n° 8).
  - `backend/app/models/report_llm_profile.py` : `ReportLLMProfile.standard_profile_ids()`,
  `get_standard_profile`, `gateway_alias`.
  - `backend/app/utils/graph_store/base.py` : `GraphStore.get_all_nodes(graph_id)`,
  `get_all_edges(graph_id)`, `get_graph_info(graph_id)`.
  - `backend/app/utils/graph_store/factory.py` : `get_graph_store()`.
  - `backend/app/utils/zep_lifecycle.py` : `graph_lifecycle_lock(graph_id)`.
  - `backend/scripts/verifier_qualification_epic_012.py` : gabarit du banc d'epic — sondes
  `verifier_critere_cN()`, `generer_rapport_qualification()`, code retour `0` / `1`.
  - `backend/tests/fixtures/qualification_epic_012/r6_bundle/` : jeu d'artefacts de rapport complet
  (10 fichiers) utilisable comme entrée hermétique du moteur de score.
  - `frontend/src/utils/reportComparison.js` : `evaluateComparability`, `readEvidenceFingerprint` —
  règle de comparabilité déjà appliquée par l'IHM, à laquelle le banc doit s'aligner.
  - `AGENTS.md` : §2.1 (couches `api → services → utils`), §2.2 (tests hermétiques), §2.9 (Docker
  d'abord, ADR 0006), §2.10 (français), §10 (faits déjà réglés : l'identifiant d'instantané n'est
  pas une adresse de contenu ; l'égalité de `snapshot_id` implique l'égalité de la capture).

- [x] **Dépendances résolues** :

  - **Stories amont** : 013-1 (`ReportLLMProfile` et effort effectif), 013-2 (`replay_frozen` et
  empreinte), 013-3 (isolation `reports/<report_id>/` et historique), 013-4 (télémétrie et
  plafonds), 013-5 (catalogue de profils, historique enrichi, comparabilité). Toutes `done`.
  - **Story aval** : aucune. La 013-6 est la dernière de l'epic ; elle produit l'artefact de
  clôture de l'Epic 013.
  - **Filet de tests mesuré à la rédaction** : **1 971 tests backend** + **43 tests Node frontend**
  au vert, mesuré le 20 octobre 2026 (`cd backend && uv run pytest tests/ -q` → `1971 passed` ;
  `pnpm --dir frontend test` → `43 pass`).
  - **Dépendances techniques** : **aucune nouvelle dépendance**. Le banc n'utilise que la
  bibliothèque standard (banc d'epic 007/009/011/012 : `argparse`, `json`, `pathlib`, `subprocess`).
  - **Environnement de référence** : la stack Docker de référence (ADR 0006) est **opérante** —
  `mirofish-backend` (healthy), `mirofish-frontend`, `mirofish-neo4j` (healthy) ; la passerelle
  Antigravity locale répond sur `http://127.0.0.1:18081/health` (`{"status": "ok"}`) et sert
  `gemini-3.8-flash` et `gemini-3.8-flash-tiered` dans `/v1/models`.
  - **Cas de référence, mesuré le 20 octobre 2026** : R7 = `sim_80a54d7bbd7b`
  (`project_id` `proj_cc8bc57b87fe`, `graph_id` `mirofish_c34a65988c24496b`, `locale` `fr`,
  `status` `completed`). Son empreinte figée est
  `26cf493ea7bbd579be7162c0eec3ee7074f905f0e5532a3c004cb9c017989f56` (5 fichiers de preuves,
  **737 événements**, **41 acteurs**, `has_archived_interviews=False`), **stable sur deux captures
  consécutives** (mesuré). Sa baseline : `report_claims.json` = 167 affirmations, 0 vérifiée,
  152 non vérifiée, 15 contradictoire, ratio `0.0` ; `quality_checks.json` = `needs_review`,
  `is_publishable=false`, `final_status=warning`.

- [x] **Décisions d'ingénierie arrêtées avant code** :

  1. **Le banc s'exécute dans la stack Docker de référence, pas sur l'hôte.** Sur l'hôte, `.env` ne
   déclare pas `ZEP_BACKEND`, dont le défaut est `cloud` (`backend/app/config.py:34`) : les outils
   graphe du `ReportAgent` (`insight_forge`, `panorama_search`, `quick_search`,
   `get_edge_provenance`) viseraient alors un Zep Cloud sans clé, là où le conteneur tourne en
   `graphiti` sur le Neo4j local (160 nœuds pour le graphe de R7, mesuré). Deux variantes ainsi
   générées ne seraient pas comparables. Le banc doit donc refuser de s'exécuter si le backend
   de graphe résolu n'est pas celui attendu, plutôt que produire un comparatif dégradé.
  2. **L'empreinte des preuves est capturée avant la campagne et comparée après chaque variante.**
   Raison : le fingerprint est stable (mesuré sur R7, deux captures consécutives) ; une dérive
   entre A et B — un fichier de preuve modifié entre les deux générations — invalide la
   comparaison et doit **exclure** la variante, pas être notée en annexe.
  3. **Le graphe n'est pas dans l'empreinte : un garde-fou de cohérence graphe est ajouté.** Le
   `replay_frozen` gèle les **interviews live** et rien d'autre (`report_agent.py` : l'appel OASIS
   d'`interview_agents` est neutralisé, la clôture d'environnement est neutralisée, mais les
   outils graphe interrogent toujours Neo4j). Le banc mesure donc l'état du graphe (nombre de
   nœuds et d'arêtes de `graph_id`) avant la première variante et après la dernière ; toute
   variation rend la comparaison **non contrôlée**. Ce point est le principal **biais résiduel**
   du protocole et il est déclaré comme tel dans le rapport.
  4. **Le score est une grille figée, purement mécanique, calculée par un module pur.** Le moteur de
   score est une fonction pure sur des artefacts (dictionnaires), sans E/S, sans réseau, sans LLM.
   Raison : la règle de score doit être écrite **avant** la campagne et ne doit pas pouvoir
   changer au milieu de celle-ci ; un module pur la rend testable sans réseau et réutilisable
   plus tard par l'IHM.
  5. **Le banc compare les empreintes qu'il a lui-même capturées ; il ne réimplémente pas la règle
   de comparabilité de l'IHM.** Le module `frontend/src/utils/reportComparison.js` porte la règle
   côté navigateur (`evaluateComparability`) ; le banc n'en a pas besoin, puisqu'il connaît les
   deux `sha256_hash` qu'il a capturés. Il doit en revanche **asser** que l'empreinte **stockée**
   dans les artefacts du rapport (`meta.json`, `evidence_snapshot.sha256_hash`) est égale à celle
   qu'il a capturée : c'est là que se niche le risque de comparatif trompeur.
  6. **La grille de score ne contient aucun champ interprétatif.** Elle ne note pas la qualité
   rédactionnelle et ne classe pas les variantes. Elle publie des mesures et des statuts de
   couverture, jamais un classement : l'arbitrage qualitatif est humain et aveugle.
  7. **Un dénominateur nul est un échec de couverture, jamais `100 %`.** Raison : PRD source §8,
   et le fait que R7 n'a produit aucune assertion d'action vérifiée alors que son Markdown en
   contient — la couverture doit être distinguable d'un score parfait.
  8. **La télémétrie est étendue (`cached_tokens`, `finish_reason`) avant la campagne, pas
   pendant.** Le PRD source §6.3/§6.6 demande de comptabiliser séparément entrée, sortie,
   cache et raisonnement, et de conserver erreurs et reprises par appel ; `CallUsageRecord` ne
   porte aujourd'hui ni l'un ni l'autre. Le travail différé assigne explicitement ce point à la
   013-6. Il doit être posé **avant** la première génération : corriger le code de télémétrie
   entre deux variantes annulerait la comparaison.
  9. **La revue aveugle est outillée, pas exécutée.** Le banc produit la paire de rapports
   anonymisée et la grille à remplir, et place la correspondance dans un fichier distinct. La
   règle de procedure est explicite : **la correspondance ne s'ouvre qu'après remplissage de la
   grille**. Raison : PRD source §12.5 ; un agent ne peut pas être son propre juge aveugle, et
   une « revue aveugle » exécutée par celui qui sait quelle variante est laquelle ne serait pas
   une revue aveugle.
  10. **Le second modèle est conditionnel et hors périmètre par défaut.** `deepseek-v4-pro` n'est
    lancé que si le résultat `medium` vs `high` est ambigu ; sinon le rapport le déclare
    « non exécuté, condition non remplie ». Raison : PRD source §7 phase 2 (conditionnelle) et
    §10. Le banc n'escalade jamais de modèle tout seul.
  11. **Le banc appelle `ReportAgent` en direct, pas l'API HTTP.** `POST /api/report/generate`
    répond `task_id` + `status: "generating"` et exécute la génération dans un
    `threading.Thread` ; un banc a besoin d'un appel **bloquant** et d'un contrôle par variante.
    Le banc reproduit donc explicitement les préconditions de l'API : `graph_id` et
    `simulation_requirement` sont lus du **projet** de la simulation
    (`ProjectManager.get_project(state.project_id)` → `project.graph_id`,
    `project.simulation_requirement`), le projet doit être `GRAPH_COMPLETED`, le `graph_id` du
    projet et celui de l'état doivent concorder, et la génération est exécutée sous
    `graph_lifecycle_lock(graph_id)` — le même verrou que l'API, qui empêche la suppression du
    graphe pendant la lecture.

- [x] **Stratégie de tests identifiée** :

  - **Ce qui est hermétique** : le moteur de score (fonction pure sur des dictionnaires) et le
  pilote de campagne (testé en injectant un `ReportAgent` factice). **Aucun test du banc
  n'appelle le réseau ni un LLM.** Le fichier `backend/tests/test_report_benchmark_score.py`
  s'exerce sur la fixture réelle `backend/tests/fixtures/qualification_epic_012/r6_bundle/`
  (artefacts de rapport complets, 258 affirmations) et sur des jeux d'artefacts minimaux
  fabriqués dans le test pour les chemins dégradés.
  - **Ce qui ne l'est pas** : la campagne réelle sur R7, qui appelle la passerelle Antigravity et
  écrit des rapports. Elle est **exécutée une fois**, sur la stack Docker de référence, et son
  résultat est consigné dans le rapport formel.
  - **Fichier de test créé** : `backend/tests/test_report_benchmark_score.py` (moteur de score, cas
  nommés : métriques de claims, métriques de qualité, métriques de cohorte, métriques d'usage,
  couverture à dénominateur nul, artefacts absents, grille vide, version de grille).
  - **Fichier de test créé** : `backend/tests/test_report_benchmark_bench.py` (pilote : refus des
  preuves insuffisantes, exclusion d'une variante à empreinte divergente, garde-fou graphe,
  campagne à deux variantes factices, `--dry-run` sans génération, code retour `0` / `1`, écriture
  du rapport).
  - **Ce qui doit être vérifié à l'œil** : sur la stack Docker, le rapport
  `rapport-qualification-epic-013.md` affiche bien les deux variantes côte à côte, la mention
  « comparaison contrôlée » ou son motif, le coût et la durée réellement consommés, et **aucune**
  mention de modèle gagnant.

  ---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Pré-contrôle de la preuve figée** : sur une simulation dont les preuves obligatoires manquent ou sont vides, le banc **s'arrête avant toute génération**, déclare un verdict « non concluant — preuves insuffisantes » et **0 rapport** n'est créé (`reports/` inchangé). | `backend/tests/test_report_benchmark_bench.py::test_campagne_refusee_si_preuves_insuffisantes` (le dossier `reports/` est vérifié vide) ; exécution réelle sur R7 : `benchmark-013-<date>/mesure-benchmark-013.json` porte `evidence.sha256_hash == "26cf493ea7bbd579be7162c0eec3ee7074f905f0e5532a3c004cb9c017989f56"`, `evidence.total_events == 737`, `evidence.total_actors == 41`. |
| **AC2** | **`--dry-run` et contrôle d'environnement, sans génération** : `python backend/scripts/verifier_benchmark_epic_013.py --dry-run --simulation-id sim_80a54d7bbd7b` affiche l'empreinte, l'état du graphe, les profils du catalogue et le plafond budgétaire estimé, et **ne crée aucun dossier de rapport**. Le banc **refuse de s'exécuter** si le backend de graphe résolu n'est pas celui attendu (`graphiti` vers le Neo4j local) : sinon les outils graphe du `ReportAgent` viseraient une passerelle absente et les deux variantes seraient dégradées de façon non comparable. | `backend/tests/test_report_benchmark_bench.py::test_dry_run_ne_genere_aucun_rapport` et `::test_banc_refuse_un_backend_de_graphe_inattendu` ; exécution réelle : la sortie contient l'empreinte `26cf493e…` et le backend ne journalise aucune création de `report_id`. |
| **AC3** | **Preuves identiques et graphe inchangé** : chaque rapport généré porte, dans ses artefacts (`meta.json` → `evidence_snapshot.sha256_hash`), une empreinte **strictement égale** à celle du pré-contrôle ; une variante dont l'empreinte diverge est **exclue** du comparatif et le rapport le déclare avec son motif. En outre, l'état du graphe (nombre de nœuds et d'arêtes de `graph_id`) est mesuré avant la première variante et après la dernière : toute variation exclut le comparatif, car le graphe **n'est pas** dans l'empreinte des preuves. | `backend/tests/test_report_benchmark_bench.py::test_variante_exclue_si_empreinte_divergente` et `::test_variante_exclue_si_le_graphe_a_change` ; le JSON du benchmark porte `variantes[].evidence_sha256`, `variantes[].graph_state` et `variantes[].exclue` + `motif_exclusion`. |
| **AC4** | **Deux variantes, zéro écrasement** : la campagne produit un `report_id` distinct par variante, chaque dossier `reports/<report_id>/` contient son dossier complet (`meta.json`, `full_report.md`, `report_claims.json`, `cohort_coverage.json`, `quality_checks.json`, `usage.json`, `run_manifest.json`), et le dossier de la première variante est **intact** après la seconde. | `backend/tests/test_report_benchmark_bench.py::test_campagne_produit_deux_dossiers_complets_sans_ecrasement` ; vérification réelle : `ls backend/uploads/reports/<report_id_A>` après la campagne, `full_report.md` non vide. |
| **AC5** | **Grille de score figée et purement mécanique** : le moteur de score calcule pour chaque variante un ensemble **fermé** de métriques, sans aucun champ interprétatif ; la grille est versionnée (`SCORE_GRID_VERSION`) et le rapport affiche la version utilisée. La version ne change pas pendant une campagne. | `backend/tests/test_report_benchmark_score.py` (≥ 12 tests, dont `test_grille_expose_les_metriques_attendues` et `test_version_de_grille_stable`) ; le JSON porte `score_grid_version`, le rapport l'affiche dans son en-tête. |
| **AC6** | **Couverture : un dénominateur nul est un échec** : si le nombre d'assertions d'action est nul, le taux de vérification des actions vaut `null` (jamais `100 %`) et la couverture porte le statut « échec de couverture » ; le rapport n'affiche aucun pourcentage **pour cette métrique** dans ce cas. | `backend/tests/test_report_benchmark_score.py::test_denominateur_nul_vient_echec_de_couverture` ; le rapport de la campagne R7 affiche la mention de couverture et aucun `100 %` sur un taux à dénominateur nul. |
| **AC7** | **Comparabilité déclarée, jamais supposée** : le rapport énonce la règle appliquée (empreinte SHA-256 d'abord, identifiant d'instantané en repli) et le verdict par paire ; si les empreintes divergent, le verdict est « non contrôlé » **avec le motif**, et le rapport ne présente pas les deux variantes comme comparables. | `backend/tests/test_report_benchmark_score.py::test_verdict_de_comparabilite_et_son_motif` ; section « Comparabilité » du rapport : verdict explicite et motif en toutes lettres. |
| **AC8** | **Honnêteté de la sortie** : toute métrique absente des artefacts vaut `null` et s'affiche « indisponible » ; le coût est libellé « estimation » ; un arrêt contrôlé affiche son code **et** son message ; le rapport n'affiche jamais `0 $` pour une donnée inconnue. | `backend/tests/test_report_benchmark_score.py::test_metrique_absente_vaut_null_et_non_zero` ; le rapport de campagne : les métriques absentes sont « indisponible », le coût porte la mention estimation. |
| **AC9** | **Aucun verdict de supériorité** : le rapport ne contient aucune section, colonne, couleur ni formule désignant un modèle, un effort ou une variante comme gagnant ; les écarts sont présentés comme des différences brutes, dans les deux sens. | `backend/tests/test_report_benchmark_bench.py::test_rapport_ne_designe_aucun_gagnant` (recherche de marqueurs interdits dans le Markdown produit) ; relecture du rapport par l'humain. |
| **AC10** | **Matériel de revue aveugle** : le banc écrit la paire de rapports anonymisée (`variante-A.md`, `variante-B.md`) et une grille de revue à remplir, et place la correspondance A ↔ profil dans un **fichier distinct** ; la règle de procedure (« la correspondance ne s'ouvre qu'après remplissage ») est écrite dans la grille elle-même. | `backend/tests/test_report_benchmark_bench.py::test_materiel_aveugle_ecrit_avec_correspondance_separee` ; le dossier `benchmark-013-<date>/` contient `variante-A.md`, `variante-B.md`, `grille-aveugle.md` et `correspondance.json`. |
| **AC11** | **Budget borné et aucune escalade** : la campagne respecte les plafonds du profil (`max_total_cost_usd`, `max_wall_seconds`), s'arrête en arrêt contrôlé si un plafond est atteint, et ne bascule jamais d'un modèle vers un autre. Le rapport déclare le coût estimé et la durée réellement consommés, ainsi que le nombre de répétitions par variante. | `backend/tests/test_report_benchmark_bench.py::test_campagne_arretee_sur_plafond_sans_escalade` ; le rapport déclare `repetitions`, `cout_estime_usd_total`, `duree_murale_secondes`. |
| **AC12** | **Non-régression** : ≥ 1 971 tests backend et 43 tests Node frontend au vert après la story ; aucune dépendance ajoutée ; aucun secret dans les artefacts produits (rapport, JSON, paire anonymisée). | `cd backend && uv run pytest tests/ -q` → ≥ 1 971 passed ; `pnpm --dir frontend test` → 43 pass ; `pnpm --dir frontend build` ; `git diff --stat frontend/package.json backend/pyproject.toml` vide ; scan de motifs de secrets sur les fichiers produits par le banc. |

---

## Définition de fini

- [ ] Moteur de score pur créé dans `backend/app/utils/report_benchmark_score.py`, avec la grille
      fermée, versionnée, et aucun champ interprétatif.
- [ ] Banc créé dans `backend/scripts/verifier_benchmark_epic_013.py`, exécutable sur la stack
      Docker de référence, avec `--dry-run`, `--simulation-id`, `--profiles`, `--repetitions`,
      `--output`.
- [ ] `backend/tests/test_report_benchmark_score.py` créé et au vert (≥ 12 tests).
- [ ] `backend/tests/test_report_benchmark_bench.py` créé et au vert (≥ 8 tests), sans réseau ni LLM.
- [ ] Télémétrie étendue : `cached_tokens` et `finish_reason` portés par `CallUsageRecord`
      (`backend/app/models/report_usage.py`), avec tests dans `backend/tests/test_report_usage_telemetry.py`.
- [ ] Campagne réelle exécutée sur R7 (`sim_80a54d7bbd7b`) : deux variantes `flash-medium` et
      `flash-high`, un `report_id` chacune, dossiers complets sous `backend/uploads/reports/`.
- [ ] Charge utile machine écrite :
      `docs/plans/013-benchmark-llm-report-replay/benchmark-013-<date>/mesure-benchmark-013.json`
      (un dossier par campagne, pour qu'une relance n'écrase pas la mesure précédente).
- [ ] Rapport formel écrit par le banc : `docs/plans/013-benchmark-llm-report-replay/rapport-qualification-epic-013.md`,
      avec verdict, métriques par variante, comparabilité et son motif, couverture, coût, durée,
      biais résiduels (dont le graphe non figé) et domaines couverts / non couverts.
- [ ] Matériel de revue aveugle écrit dans le **même** dossier de campagne
      `docs/plans/013-benchmark-llm-report-replay/benchmark-013-<date>/` : `variante-A.md`,
      `variante-B.md`, `grille-aveugle.md`, `correspondance.json`.
- [ ] `AGENTS.md` §10 complété du fait nouveau « le graphe n'est pas dans l'empreinte des
      preuves », et de l'empreinte mesurée de R7.
- [ ] Suite backend complète au vert (≥ 1 971 tests), tests Node au vert (43), `ruff check` propre,
      `validate_plans.py` propre, aucune dépendance ajoutée, aucun secret dans les artefacts produits.
- [ ] Vérification visuelle sur la stack Docker de référence consignée en Notes de complétion.
- [ ] Revue de code contradictoire BMAD à 4 couches menée et consignée en section « Revue ».

---

## Tâches

- [ ] 1. Étendre `CallUsageRecord` (`backend/app/models/report_usage.py`) avec `cached_tokens` et
       `finish_reason`, les extraire de façon défensive dans le traqueur, et couvrir les chemins
       dégradés dans `backend/tests/test_report_usage_telemetry.py`. *(AC8, AC11, AC12 — avant
       toute génération : corriger la télémétrie entre deux variantes annulerait la comparaison.)*
- [ ] 2. Écrire le moteur de score `backend/app/utils/report_benchmark_score.py` : grille fermée
       versionnée, calcul des métriques de claims, de qualité, de cohorte, d'usage et de
       couverture, verdict de comparabilité avec motif, et gestion des artefacts absents.
       *(AC5, AC6, AC7, AC8)*
- [ ] 3. Écrire `backend/tests/test_report_benchmark_score.py` : métriques de claims, métriques de
       qualité, métriques de cohorte, métriques d'usage, couverture à dénominateur nul, artefacts
       absents, grille vide, version de grille stable, verdict de comparabilité et son motif.
       *(AC5, AC6, AC7, AC8)*
- [ ] 4. Écrire `backend/scripts/verifier_benchmark_epic_013.py` : pré-contrôle de l'empreinte,
       garde-fou de cohérence du graphe, boucle de variantes, relecture des artefacts, appel du
       moteur de score, écriture du JSON et du rapport, code retour `0` / `1`. *(AC1, AC3, AC4, AC9, AC10, AC11)*
- [ ] 5. Ajouter le mode `--dry-run` au banc : pré-contrôle et plan, **aucune** génération.
       *(AC2)*
- [ ] 6. Écrire `backend/tests/test_report_benchmark_bench.py` : preuves insuffisantes, variante
       exclue sur empreinte divergente, garde-fou graphe, campagne à deux variantes factices,
       `--dry-run` sans génération, absence de « gagnant » dans le rapport, matériel de revue
       aveugle écrit, code retour. *(AC1, AC2, AC3, AC4, AC9, AC10, AC11)*
- [ ] 7. Exécuter la campagne réelle sur R7 dans la stack Docker de référence : deux variantes
       `flash-medium` / `flash-high`, une répétition chacune, puis consigner les `report_id`
       obtenus. *(AC1, AC4, AC11)*
- [ ] 8. Écrire le matériel de revue aveugle (paire anonymisée, grille, correspondance séparée) et
       le rapport formel versionné. *(AC9, AC10)*
- [ ] 9. Vérifier la non-régression complète (pytest, tests Node, build Vite, `ruff`,
       `validate_plans.py`, scan de secrets) et consigner la vérification visuelle.
       *(AC12)*
- [ ] 10. Mettre à jour `AGENTS.md` (§10), `docs/sprint-status.yaml`, `docs/STATUS.md` et le hub
       `epic-013.md`. *(AC12)*
- [ ] 11. Exécuter la revue de code contradictoire BMAD à 4 couches et consigner les conclusions.
       *(AC9, AC12)*

---

## Notes de développement

- à remplir pendant l'implémentation : ce qui a été décidé en codant, et pourquoi ; les points
  non résolus ; les pièges rencontrés.

---

## Revue

- à remplir par la revue contradictoire : findings retenus et leur gravité, correctif appliqué,
  points différés, rejets motivés.

---

## Notes de complétion

- à remplir à la clôture : statut final, tests exécutés, lint, validation de plan, écarts avec le
  plan et pourquoi, ce que la story ne fait pas, effets de bord observés.
