---
id: "013-6"
epic: "013"
titre: "Banc de benchmark contrôlé A/B et qualification globale de l'Epic 013"
statut: done
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

- [x] Moteur de score pur créé dans `backend/app/utils/report_benchmark_score.py`, avec la grille
      fermée, versionnée, et aucun champ interprétatif.
- [x] Banc créé dans `backend/scripts/verifier_benchmark_epic_013.py`, exécutable sur la stack
      Docker de référence, avec `--dry-run`, `--simulation-id`, `--profiles`, `--repetitions`,
      `--output`.
- [x] `backend/tests/test_report_benchmark_score.py` créé et au vert (≥ 12 tests).
- [x] `backend/tests/test_report_benchmark_bench.py` créé et au vert (≥ 8 tests), sans réseau ni LLM.
- [x] Télémétrie étendue : `cached_tokens` et `finish_reason` portés par `CallUsageRecord`
      (`backend/app/models/report_usage.py`), avec tests dans `backend/tests/test_report_usage_telemetry.py`.
- [x] Campagne réelle exécutée sur R7 (`sim_80a54d7bbd7b`) : deux variantes `flash-medium` et
      `flash-high`, un `report_id` chacune, dossiers complets sous `backend/uploads/reports/`.
- [x] Charge utile machine écrite :
      `docs/plans/013-benchmark-llm-report-replay/benchmark-013-<date>/mesure-benchmark-013.json`
      (un dossier par campagne, pour qu'une relance n'écrase pas la mesure précédente).
- [x] Rapport formel écrit par le banc : `docs/plans/013-benchmark-llm-report-replay/rapport-qualification-epic-013.md`,
      avec verdict, métriques par variante, comparabilité et son motif, couverture, coût, durée,
      biais résiduels (dont le graphe non figé) et domaines couverts / non couverts.
- [x] Matériel de revue aveugle écrit dans le **même** dossier de campagne
      `docs/plans/013-benchmark-llm-report-replay/benchmark-013-<date>/` : `variante-A.md`,
      `variante-B.md`, `grille-aveugle.md`, `correspondance.json`.
- [x] `AGENTS.md` §10 complété du fait nouveau « le graphe n'est pas dans l'empreinte des
      preuves », et de l'empreinte mesurée de R7.
- [x] Suite backend complète au vert (≥ 1 971 tests), tests Node au vert (43), `ruff check` propre,
      `validate_plans.py` propre, aucune dépendance ajoutée, aucun secret dans les artefacts produits.
- [x] Vérification visuelle sur la stack Docker de référence consignée en Notes de complétion.
- [x] Revue de code contradictoire BMAD à 4 couches menée et consignée en section « Revue ».

---

## Tâches

- [x] 1. Étendre `CallUsageRecord` (`backend/app/models/report_usage.py`) avec `cached_tokens` et
       `finish_reason`, les extraire de façon défensive dans le traqueur, et couvrir les chemins
       dégradés dans `backend/tests/test_report_usage_telemetry.py`. *(AC8, AC11, AC12 — avant
       toute génération : corriger la télémétrie entre deux variantes annulerait la comparaison.)*
- [x] 2. Écrire le moteur de score `backend/app/utils/report_benchmark_score.py` : grille fermée
       versionnée, calcul des métriques de claims, de qualité, de cohorte, d'usage et de
       couverture, verdict de comparabilité avec motif, et gestion des artefacts absents.
       *(AC5, AC6, AC7, AC8)*
- [x] 3. Écrire `backend/tests/test_report_benchmark_score.py` : métriques de claims, métriques de
       qualité, métriques de cohorte, métriques d'usage, couverture à dénominateur nul, artefacts
       absents, grille vide, version de grille stable, verdict de comparabilité et son motif.
       *(AC5, AC6, AC7, AC8)*
- [x] 4. Écrire `backend/scripts/verifier_benchmark_epic_013.py` : pré-contrôle de l'empreinte,
       garde-fou de cohérence du graphe, boucle de variantes, relecture des artefacts, appel du
       moteur de score, écriture du JSON et du rapport, code retour `0` / `1`. *(AC1, AC3, AC4, AC9, AC10, AC11)*
- [x] 5. Ajouter le mode `--dry-run` au banc : pré-contrôle et plan, **aucune** génération.
       *(AC2)*
- [x] 6. Écrire `backend/tests/test_report_benchmark_bench.py` : preuves insuffisantes, variante
       exclue sur empreinte divergente, garde-fou graphe, campagne à deux variantes factices,
       `--dry-run` sans génération, absence de « gagnant » dans le rapport, matériel de revue
       aveugle écrit, code retour. *(AC1, AC2, AC3, AC4, AC9, AC10, AC11)*
- [x] 7. Exécuter la campagne réelle sur R7 dans la stack Docker de référence : deux variantes
       `flash-medium` / `flash-high`, une répétition chacune, puis consigner les `report_id`
       obtenus. *(AC1, AC4, AC11)*
- [x] 8. Écrire le matériel de revue aveugle (paire anonymisée, grille, correspondance séparée) et
       le rapport formel versionné. *(AC9, AC10)*
- [x] 9. Vérifier la non-régression complète (pytest, tests Node, build Vite, `ruff`,
       `validate_plans.py`, scan de secrets) et consigner la vérification visuelle.
       *(AC12)*
- [x] 10. Mettre à jour `AGENTS.md` (§10), `docs/sprint-status.yaml`, `docs/STATUS.md` et le hub
       `epic-013.md`. *(AC12)*
- [x] 11. Exécuter la revue de code contradictoire BMAD à 4 couches et consigner les conclusions.
       *(AC9, AC12)*

---

## Notes de développement

Ce qui a été décidé **en codant**, et pourquoi. Les décisions d'ingénierie
arrêtées avant code sont dans la Définition de prêt ; ce qui suit est ce que
l'implémentation a imposé.
1. **Le moteur de score reste un module pur, sur des dictionnaires.** Il
   n'importe aucun modèle métier et ne lit aucun fichier. Conséquence : les
   littéraux d'énumération du domaine (`OBSERVED_SOCIAL_ACTION`, `VERIFIED`) sont
   recopiés dans le module. C'est un compromis assumé — `app/utils/` n'importe
   jamais `app/models/` dans ce dépôt, et il n'y a pas de raison d'ouvrir
   l'exception pour deux constantes. *Contrôle : `grep "from ..models" app/utils/`
   ne renvoie rien.*

2. **Le banc appelle `ReportAgent` en direct, et reproduit les préconditions de
   l'API.** L'API répond `task_id` et travaille dans un thread de fond ; un banc
   a besoin d'un appel bloquant. Le banc reproduit donc ce que l'API vérifie :
   projet `GRAPH_COMPLETED`, `graph_id` concordant, exigence de simulation non
   vide, et exécution sous `graph_lifecycle_lock` (le même verrou que l'API,
   avec inscription puis désinscription du lecteur de graphe).

3. **Le pré-contrôle n'est effectué qu'une fois.** Une campagne capture deux
   empreintes de référence si elle en fait deux : la console, la charge utile et
   le rapport porteraient alors des valeurs différentes. Le pré-contrôle est
   donc calculé une fois et **passé** à la campagne.

4. **Le dossier d'un rapport est une source de vérité, pas une reconstruction.**
   Le banc lit `ReportManager.get_report_folder(report_id)` — l'emplacement réel
   — et non un chemin recalculé : un chemin recalculé pouvait désigner un dossier
   vide, dont les métriques seraient « indisponibles » sans que personne ne
   s'en aperçoive. Un accesseur **public** a été ajouté à `ReportManager` pour
   cela (`_get_report_folder` reste privé).

5. **Le garde-fou de cohérence du graphe mesure le contenu, pas seulement les
   cardinalités.** Une écriture peut enrichir un nœud *existant* sans en créer
   (le « merge » de Graphiti met à jour le résumé et les attributs) : les
   comptes de nœuds et d'arêtes resteraient inchangés alors que les outils
   graphe liraient un contenu différent. Le banc mesure donc en plus une
   **empreinte de contenu** (SHA-256 sur la liste triée des identifiants, noms
   et résumés des nœuds, et des identifiants et faits des arêtes).

6. **Le dénominateur du taux d'adoption est un fait persisté.** Le modèle
   renvoie `adoption_rate = 0.0` quand aucun prospect n'est éligible, ce qui est
   un « non applicable » sérialisé en zéro. `CohortCoverageTable.to_dict()`
   publie désormais `adoption_denominator` : le dénominateur est lisible par
   l'API, l'historique, l'IHM et la grille, et la règle d'éligibilité reste
   écrite à un seul endroit (le modèle).

7. **La règle de comparabilité a été alignée sur celle de l'IHM.** Le banc
   compare les empreintes qu'il a lui-même capturées, mais sa règle doit être
   la **même** que celle de `frontend/src/utils/reportComparison.js`, sinon le
   banc et l'IHM peuvent rendre des verdicts opposés pour le même couple. Les
   deux implémentations appliquent désormais les mêmes cas : instantané absent
   d'un côté → non contrôlé ; simulations différentes → non contrôlé ; empreinte
   SHA-256 en priorité ; identifiant d'instantané en repli.

8. **Le rapport est construit, contrôlé, puis écrit.** Le contrôle des
   marqueurs de désignation (AC9) porte sur le contenu **construit** : un
   rapport non conforme n'est jamais laissé sur le disque. La construction et
   l'écriture sont deux fonctions distinctes, et la CLI appelle la même
   fonction d'écriture que les tests.

9. **Les erreurs de fournisseur sont neutralisées avant d'être écrites.** Un
   message d'exception peut contenir une URI de passerelle, une URI de
   connexion porteuse d'identifiants ou un extrait de requête. Toutes les
   erreurs passent par `_description_erreur()` : type d'exception, message
   tronqué à 200 caractères, URI masquées.

10. **Le mode de rejeu est une constante, pas un paramètre.** `replay_frozen`
    n'a pas de sens autrement : une comparaison à preuves figées ne peut pas
    se faire en direct. Un paramètre configurable aurait pu rendre le rapport
    formel auto-contradictoire.

11. **Le déclassement de l'aveuglement est un constat de paire.** Un corps qui
    mentionne le modèle ou l'effort d'une *autre* variante trahit aussi la
    correspondance : le lecteur en déduit quelle variante il relit. La
    détection est donc faite de campagne, et l'effort n'est recherché
    qu'**accompagné d'un mot-clé** (« effort », « reasoning », « profil ») — le
    mot anglais « high » est un mot courant, et le chercher seul déclasserait à
    tort des rapports parfaitement anonymes.

12. **Le banc ne juge pas, il outille.** Aucune fonction du banc ne compare deux
    variantes pour en désigner une. La grille publie des décomptes, des taux et
    des statuts ; le rapport présente des différences brutes, dans les deux sens ;
    l'arbitrage appartient à la revue aveugle, dont le matériel est écrit mais
    **pas exécuté**.

13. **Le `--dry-run` ne crée aucun dossier.** Le mode rehearsal affiche
    l'empreinte, l'état du graphe, les profils du catalogue et les plafonds, et
    s'arrête avant toute création de rapport. Le test vérifie que le dossier
    `reports/` reste vide.

14. **Le plafond mural du catalogue a été relevé de 900 s à 5 400 s**, sur
    arbitrage explicite de l'utilisateur, après mesure : sur R7, la variante
    `flash-medium` demande ~1 270 s, la variante `flash-high` (plus de tokens de
    raisonnement) **~3,5 fois plus**, soit ~4 500 s. Un plafond de 900 s
    tronquait la variante `high` dès la deuxième section, et un plafond de
    1 800 s la tronquait encore en section 3 sur 5 : le banc concluait alors
    « non concluant — variante écartée » — un résultat honnête, mais qui ne
    répondait pas à la question posée, parce que la troncature était un
    artefact du **budget**, non une propriété de la variante. Le relevé est
    mesuré, documenté dans le code et borne toujours réellement la génération.
    Effet produit assumé : une régénération depuis l'IHM peut désormais durer
    jusqu'à 1 h 30. Le plafond **budgétaire** n'a pas été touché : sur une
    passerelle locale, le coût facturable est réellement nul, donc seul le
    plafond mural mord (le Fail-Closed tarifaire reste armé sur les profils
    `metered` pour un fournisseur facturant).

15. **La campagne doit tourner sur un hôte au repos.** Mesuré : la latence de
    la passerelle locale **double** quand une autre charge s'exécute sur la
    même machine (suite de tests, campagne concurrente). Une campagne menée en
    parallèle d'une suite de tests a atteint le plafond mural sur les deux
    variantes ; relancée seule, la variante `medium` a terminé sans peine.
    C'est une condition de validité de la mesure, pas un détail
    d'exécution : elle est consignée ici parce qu'elle affecte directement la
    comparabilité des durées publiées.

16. **Un rapport complet refusé par la barrière reste comparable.** La première
    version de la règle d'exclusion écartait toute variante au statut
    `failed_validation`. C'était une erreur : `ReportStatus.FAILED_VALIDATION`
    est posé **après** l'assemblage complet du rapport, quand la barrière de
    publication refuse de le certifier. Le rapport est alors complet, et son
    verdict de certification est une **mesure** du rapport — pas un défaut de
    la mesure. L'écarter perdait précisément l'information la plus instructive
    du benchmark. Seuls les statuts de **génération incomplète** (`failed` :
    arrêt sur plafond, plantage) écartent une variante ; la certification
    refusée est **publiée** dans le rapport, variante par variante.

17. **Une panne réseau est relancée, un résultat ne l'est pas.** Mesuré : la
    passerelle locale a renvoyé un `502` amont (« Remote end closed
    connection ») en cours de campagne, ce qui a fait échouer la génération
    d'une variante. Une panne d'infrastructure n'est pas un résultat : le banc
    relance donc une variante **une fois** (au maximum), avec le même profil
    et le même jeu de preuves, et consigne la relance. À l'inverse, un arrêt
    **contrôlé** (plafond mural, plafond budgétaire) n'est **pas** relancé :
    c'est un résultat, et il est publié tel quel. Le nombre de tentatives par
    variante figure dans la charge utile et dans le rapport.

18. **Le motif d'exclusion le plus précis est celui qui reste.** Un contrôle
    tardif (dossier de rapport incomplet) écrasait le motif du statut
    d'échec, qui expliquait mieux la cause. Les contrôles d'exclusion sont
    désormais ordonnés : le premier motif trouvé est conservé, les suivants
    ne font qu'ajouter une précision.

---

## Revue

Revue de code contradictoire **BMAD à quatre couches** conduite le 20 octobre
2026 sur le diff de la story, par quatre lecteurs indépendants :

| Couche | Angle | Findings |
|---|---|---|
| 1 | Correction logique | 12 findings |
| 2 | Secrets, fuite de données, honnêteté des valeurs | 12 findings |
| 3 | Qualité et véracité des tests | 12 findings + annexe de branches non couvertes |
| 4 | Architecture, SOLID, KISS, DRY, généricité | 10 findings |

**Findings retenus et corrigés (24 patchs appliqués)** :

- *Logique* : l'empreinte de référence et l'état du graphe n'étaient plus
  reportés dans la charge utile (le rapport affichait `None`) — le pré-contrôle
  est désormais calculé une fois et transmis ; une variante dont le rapport ne
  porte **aucune** empreinte n'était pas écartée ; une variante au statut
  d'échec (`failed`, `failed_validation`) était comparée à un rapport complet ;
  un échec de mesure du graphe était rapporté comme « le graphe a changé » ;
  « état du graphe identique » était affirmé alors qu'aucune variante n'avait
  été mesurée ; le tableau des métriques publiait les mesures d'une variante
  écartée ; les écarts bruts annoncés n'étaient pas calculés ; le dossier du
  rapport était recalculé au lieu d'être lu.
- *Secrets et honnêteté* : le coût total de campagne valait `0.0 $` quand il
  était inconnu ; la durée s'affichait « `None s` » ; les messages d'erreur
  bruts pouvaient contenir une URL de passerelle ; la charge utile n'était pas
  passée par `sanitize_usage_payload` ; le coût théorique n'était jamais
  publié ; le rapport citait la version de la *grille de score* comme version de
  la *grille tarifaire* ; le taux d'adoption était publié sans son dénominateur ;
  le garde-fou « aucun gagnant » s'exécutait **après** l'écriture du rapport ;
  le scan de secrets ne couvrait pas les URL de passerelle.
- *Tests* : le chemin d'écriture de la CLI n'était jamais exercé ;
  `verifier_preconditions()` ne l'était pas non plus ; l'exclusion « empreinte
  stockée ≠ empreinte recontrôlée » n'était jamais atteinte ; les chemins
  dégradés de `lire_artefacts` ne l'étaient pas ; le test de déclassement ne
  testait pas ce qu'il annonçait ; la détection croisée du **modèle** d'une
  autre variante n'était pas testée ; la fixture de cohorte du double n'avait
  pas la forme de l'artefact réel ; `usage_stop_reason` et `usage_stop_message`
  n'étaient assertés nulle part ; la validation de `ConfigurationCampagne` et
  la traduction CLI d'une configuration invalide n'étaient pas testées ; la
  troncature des messages d'erreur n'était pas testée ; le nom du test cité par
  la table de traçabilité de la story
  (`test_banc_refuse_un_backend_de_graphe_inattendu`) n'existait pas.
- *Architecture* : la règle de comparabilité Python divergeait de la règle
  JavaScript sur deux entrées ; le dénominateur d'adoption était une convention
  privée injectée par le banc ; les préconditions et le contexte étaient lus
  deux fois ; `replay_mode` était un paramètre fantôme ; deux fonctions
  d'écriture du rapport coexistaient, dont une sans contrôle ; le banc
  dépendait d'un membre **privé** de `ReportManager` ; les statuts d'échec
  étaient recopiés en chaînes au lieu d'être lus dans l'énumération.

**Points différés (4)** — consignés dans `docs/deferred-work.md` : le paquet de
revue exportable (la clé de l'aveuglement reste dans le dossier de campagne,
comme l'exige la définition de fini de la story) ; la table de cas partagée
entre les implémentations Python et JavaScript de la règle de comparabilité ; le
service d'admission partagé entre l'API et le banc ; l'empreinte de contenu du
graphe qui ne couvre pas l'objet d'attributs complet.

**Rejets motivés (3)** : (a) *sortir les tokens de raisonnement du compte du
fournisseur* — la passerelle Antigravity ne les expose pas dans l'objet `usage`,
et le banc ne peut pas les inventer : `usage_thinking_tokens` vaut 0 sur les deux
variantes de la campagne, ce qui est une **mesure** du fournisseur, pas une
absence ; (b) *rejouer les interviews OASIS* — hors du périmètre par construction
(`replay_frozen` neutralise les appels live, c'est le sujet même de l'épic) ;
(c) *un second modèle de secours* — la décision d'ingénierie n° 10 est explicite :
le banc n'escalade jamais de modèle tout seul, et la condition
« `medium` vs `high` ambigu » n'est pas remplie par une campagne à une
répétition.

**État de la revue** : la story est passée en `review` avec les correctifs
appliqués et vérifiés par mutation (trois mutations ciblées ont été confirmées
comme détectées par les tests correspondants).

### Revue de clôture — confrontation des 12 critères d'acceptation

| AC | Preuve | Verdict |
|---|---|---|
| AC1 | `test_campagne_refusee_si_preuves_insuffisantes` ; à la campagne, l'empreinte de référence a été retrouvée (737 événements, 41 acteurs) | conforme |
| AC2 | `test_dry_run_ne_genere_aucun_rapport`, `test_banc_refuse_un_backend_de_graphe_inattendu` ; la rehearsal sur la stack affiche empreinte, graphe, profils et plafonds sans créer de rapport | conforme |
| AC3 | `test_variante_exclue_si_empreinte_divergente`, `test_variante_exclue_si_le_graphe_a_change` ; les deux rapports portent la même empreinte `26cf493e…`, et l'empreinte de contenu du graphe est identique avant et après | conforme |
| AC4 | `test_campagne_produit_deux_dossiers_complets_sans_ecrasement` ; les deux dossiers portent les 7 artefacts, le premier est intact après le second | conforme |
| AC5 | `test_grille_expose_les_metriques_attendues`, `test_version_de_grille_stable` ; le rapport affiche la version `1.1.0` et ses 34 métriques | conforme |
| AC6 | `test_denominateur_nul_vient_echec_de_couverture` ; la variante A affiche un taux « indisponible » et « échec de couverture » (0 assertion d'action) | conforme |
| AC7 | `test_verdict_de_comparabilite_et_son_motif` ; le rapport énonce la règle (empreinte SHA-256 prioritaire, instantané en repli) et le motif du verdict | conforme |
| AC8 | `test_metrique_absente_vaut_null_et_non_zero` ; le rapport affiche « indisponible », libèle le coût comme estimation et publie le coût théorique | conforme |
| AC9 | `test_rapport_ne_designe_aucun_gagnant` ; le banc refuse lui-même d'écrire un rapport porteur d'un marqueur de désignation | conforme |
| AC10 | `test_materiel_aveugle_ecrit_avec_correspondance_separee` ; la paire anonymisée, la grille, la correspondance et la consigne sont dans le dossier de campagne | conforme |
| AC11 | `test_campagne_arretee_sur_plafond_sans_escalade` ; plafonds du profil appliqués, aucune escalade, coût et durée déclarés | conforme |
| AC12 | 2 067 tests backend et 43 tests Node au vert, aucune dépendance ajoutée, scan de secrets sur les 7 artefacts produits : propre | conforme |

### Revue aveugle — issue et conséquence

La grille a été remplie (voir `benchmark-013-20261020-203040/grille-aveugle.md`),
avec la réserve explicite que l'évaluateur — un agent de la session de
développement — avait déjà lu la correspondance : l'évaluation **informe**,
elle n'**autorise** pas.

**Résultat** : A (`medium`) = 2/5, B (`high`) = 2/5. Les erreurs matérielles
majeures sont **communes** aux deux variantes (arc « Émilie » fabriqué alors
qu'elle n'a aucune action observée, citations présentées comme verbatim et
qui ne le sont pas, souscriptions contredites par le tableau de cohorte du
rapport lui-même, section « Sources & Provenance » qui certifie une
traçabilité que le registre du même rapport nie, persona active omise de la
prose). `high` ajoute des erreurs qui lui sont propres (citations
d'entretiens menés pendant la rédaction présentées comme des événements
observés, question d'entretien présupposant la conversion).

**Confirmation indépendante** : une seconde revue a été conduite le
21 octobre 2026 par un évaluateur externe (ChatGPT, session neuve, sans
accès à la correspondance) — voir
`benchmark-013-20261020-203040/revue-aveugle-independante.md`. Ses notes :
A = 1/2/3/4/1, B = 0/2/2/4/1 (2,2/5 et 1,8/5). Les deux revues
**convergent** : même note globale, mêmes erreurs matérielles décisives, et
`high` **jamais supérieure** à `medium` — inférieure sur l'exactitude et sur
les limites. *Réserve* : les pièces de preuve jointes à cette seconde revue
portaient `sim_ea4f3cfe1028` (l'exécution R6) au lieu de `sim_80a54d7bbd7b`,
ce qui rend **provisoires** ses notes des critères 1 et 5 ; le verdict global
et la comparaison A/B, eux, reposent sur les textes mêmes des rapports. La
procédure a été durcie : la consigne exige désormais un contrôle du
`simulation_id` des pièces jointes avant l'envoi.

**Décision (PRD source §8)** : le critère « *choisir `high` si la revue
aveugle montre une réduction claire des erreurs matérielles et des citations
non fondées* » **n'est pas rempli** → **la configuration par défaut reste
`medium`** ; le banc n'a justifié aucun basculement de modèle. La
campagne démontre en revanche un **défaut de pipeline**, pas de modèle :
il est consigné dans `docs/deferred-work.md` et devient le prochain
chantier de l'Epic 013.

---

## Notes de complétion

- **Statut final** : `done`. La story a été implémentée, testée, revue à
  quatre couches, exécutée en conditions réelles, et la revue aveugle a été
  remplie. Les 12 critères d'acceptation sont satisfaits (table de clôture
  dans la section « Revue »).
- **Tests exécutés** (chiffres lus dans la sortie des commandes) :
  - `cd backend && uv run pytest tests/ -q` → **2 067 passed** (référence
    avant story : 1 971 ; **+ 96 tests** hermétiques nouveaux) ;
  - `pnpm --dir frontend test` → **43 pass** (inchangés : la story ne touche
    pas le frontend) ;
  - `pnpm --dir frontend build` → *built in 1.02 s* ;
  - `cd backend && uv run ruff check .` → *All checks passed!* ;
  - `cd backend && uv run python scripts/validate_plans.py` → *structure de
    planification valide — 13 epics, 66 fichier(s) de story*.
- **Campagne réelle** — stack Docker de référence (ADR 0006), simulation R7
  `sim_80a54d7bbd7b`, deux variantes `flash-medium` puis `flash-high`, une
  répétition chacune, un `report_id` par variante, une tentative par variante
  (aucune relance). **Verdict : comparaison contrôlée.**
  - **Preuves figées** : empreinte SHA-256
    `26cf493ea7bbd579be7162c0eec3ee7074f905f0e5532a3c004cb9c017989f56`,
    737 événements, 41 acteurs — retrouvée au pré-contrôle **et** recontrôlée
    après chaque variante, identique dans les deux cas.
  - **Graphe** : `mirofish_c34a65988c24496b`, 42 nœuds, 163 arêtes, empreinte
    de contenu `1ac6e9a3…` — **inchangée** pendant toute la campagne.
  - **Durée murale de campagne** : 4 434,96 s (2 214 s et 2 220 s par
    variante).
  - **Coût facturable** : 0,0 $ (passerelle locale) ; **coût théorique**
    0,9119 $ et 1,0251 $ — c'est le montant qu'une campagne comparable
    coûterait sur une passerelle facturée.
  - **Résultats bruts** (aucun classement n'est produit) :

    | Mesure | A (`medium`) | B (`high`) | Écart brut (B − A) |
    |---|---|---|---|
    | Affirmations extraites | 159 | 178 | +19 |
    | Affirmations vérifiées | 0 | 1 | +1 |
    | Affirmations contradictoires | 7 | 8 | +1 |
    | Assertions d'action observée | 0 | 1 | +1 |
    | Taux de vérification des actions | **indisponible** (échec de couverture) | 1,0 | — |
    | Contrôles de publication en échec | 0 | 0 | 0 |
    | Statut de certification | `needs_review` | `needs_review` | — |
    | Appels LLM | 58 | 50 | −8 |
    | Tokens totaux | 517 143 | 582 629 | +65 486 |
    | Durée d'inférence | 2 195,4 s | 1 885,2 s | −310,2 s |
    | Caractères du rapport | 47 202 | 49 468 | +2 266 |

  Ce que la mesure dit, et que le banc **ne tranche pas** : à effort `high`,
  l'extraction est plus prolixe (+19 affirmations) et capte une assertion
  d'action que l'effort `medium` n'a pas produite — d'où un taux de
  vérification des actions *indéfinible* côté `medium` (dénominateur nul) et
  *mesurable* côté `high`. Le rapport `high` est aussi plus long (+4,8 %) et
  coûte ~13 % de tokens de plus. La qualité rédactionnelle et l'exactitude
  réelle de ces affirmations relèvent de la **revue aveugle**, dont le
  matériel est écrit et **non exécuté**.
- **Vérification visuelle** : le rapport de qualification, la charge utile
  JSON et les quatre fichiers du matériel de revue aveugle ont été relus à
  l'œil après la campagne ; la paire anonymisée a été contrôlée par recherche
  de marqueurs (`gemini`, `flash-medium`, `flash-high`, `effort de
  raisonnement`) — **aucune fuite** dans les deux corps. La story ne touche
  pas l'IHM : la vérification visuelle porte sur les artefacts produits, pas
  sur un écran.
- **Écarts avec le plan, et pourquoi** :
  1. **Le pré-contrôle n'est plus rejoué par la campagne** (décision de codage
     n° 3) : deux captures de référence auraient pu différer, et le rapport
     aurait affiché une empreinte différente de celle de la charge utile.
  2. **Le mode de rejeu est une constante** et non un paramètre (décision n° 10) :
     un paramètre aurait permis un rapport auto-contradictoire.
  3. **La version de la grille de score est `1.1.0`** et non `1.0.0` : la revue a
     ajouté `usage_theoretical_cost_usd` et `cohort_adoption_denominator`, et a
     fait respecter le drapeau `usage_available`. La grille étant versionnée,
     le changement est explicite et daté.
  4. **Le dénominateur d'adoption est publié par le modèle**
     (`CohortCoverageTable.to_dict()`), et non injecté par le banc : c'était une
     convention privée, invisible pour l'API et l'IHM.
  5. **La règle de comparabilité a été alignée sur l'IHM** au lieu d'être
     simplement « non réimplémentée » : la story demandait de ne pas
     réimplémenter la règle, mais le rapport doit **énoncer** la règle appliquée
     et rendre un verdict par paire — il fallait donc une implémentation
     serveur, alignée cas par cas avec la version navigateur.
  6. **Un accesseur public `ReportManager.get_report_folder()`** a été ajouté :
     le banc ne doit pas dépendre d'un membre privé pour connaître l'emplacement
     d'un rapport.
  7. **Le format du dossier de campagne** est `benchmark-013-<AAAAMMJJ-HHMMSS>`
     (date **et** heure) : une date seule aurait écrasé la mesure d'une
     relance le même jour, et la définition de fini exige qu'une relance
     n'écrase pas la mesure précédente.
  8. **Le plafond mural du catalogue a été relevé** (900 s → 5 400 s), sur
     arbitrage explicite de l'utilisateur, après mesure : la variante
     `flash-high` sur R7 demande ~4 500 s, soit ~3,5 fois la variante
     `medium`. C'est une modification du **produit**, hors du périmètre
     strict de la story ; elle est consignée ici parce qu'elle est la
     condition de l'AC11 (le banc respecte les plafonds du profil) **et** de
     la définition de fini (deux variantes complètes).
  9. **Une variante peut être relancée une fois** après une erreur
     d'infrastructure (décision n° 17) : le banc n'est pas rejouable s'il
     meurt sur un `502` amont. La relance est bornée, avec le même profil et
     le même jeu de preuves, et elle est consignée. *La campagne de référence
     n'a nécessité aucune relance.*
  10. **Le rapport est une fonction déterministe de la charge utile** : son
      horodatage est celui de la campagne, pas celui du rendu. Le rapport
      versionné peut donc être rejoué à partir du seul JSON, à l'octet près.
- **Ce que la story ne fait pas** : elle ne qualifie pas la **qualité
  rédactionnelle** — la grille mesure des décomptes et des taux, et l'arbitrage
  qualitatif revient à la revue aveugle, dont le matériel est écrit mais **pas
  exécuté** (un agent ne peut pas être son propre juge aveugle) ; elle ne
  compare pas deux simulations ; elle n'escalade jamais de modèle ; elle ne
  corrige jamais le code vérificateur entre deux variantes ; elle ne fige pas le
  graphe ; elle ne mesure pas la variabilité stochastique (une répétition par
  variante).
- **Effets de bord observés** : deux rapports supplémentaires ont été produits
  sous `backend/uploads/reports/` (`report_108186c7524b` et
  `report_ccf28321dcb8`, zéro écrasement) ; l'entrée d'historique
  `sim_80a54d7bbd7b/report_history.json` a été complétée par les deux
  générations ; l'image `mirofish-backend:local` a été reconstruite (le code
  est **cuit** dans l'image, pas monté en volume : un banc lancé sans
  reconstruction exécuterait l'ancienne version du banc) ; le plafond mural
  des profils de rapport est passé de 900 à 5 400 s.
- **Un test préexistant a échoué par intermittence** :
  `tests/test_report_llm_profile.py::test_antigravity_proxy_build_gemini_request_translates_effort`
  a échoué **2 fois sur ~10 exécutions complètes** de la suite, et **jamais**
  en exécution isolée (7 tentatives ciblées sans échec) ni lors des trois
  dernières suites complètes (2 067 passantes chacune). Les deux échecs sont
  survenus sur des exécutions lancées immédiatement après une forte activité
  Docker sur le même hôte. Le test est **antérieur à la story** et n'a pas été
  touché par ce diff ; il importe un module local
  (`backend/scripts/antigravity_proxy.py`) par un `sys.path.insert`, ce qui le
  rend dépendant de l'état de la machine. *Consigné dans
  `docs/deferred-work.md`.*
- **Ce qui n'a pas pu être vérifié** : le passage en revue de la campagne
  elle-même (la revue aveugle est outillée, pas exécutée) ; la robustesse du
  banc face à une dérive du graphe en cours de campagne, faute d'un scénario
  d'injection temps réel — le garde-fou est testé par injection, pas par
  accident naturel ; la variabilité stochastique du modèle, faute de
  répétitions multiples ; le comportement du banc sur une simulation dont le
  projet n'est pas `GRAPH_COMPLETED` est testé par injection de préconditions,
  pas contre une vraie simulation dans cet état.
