# AGENTS.md — MiroFish local-first

Constitution du dépôt. Elle vaut pour toute contribution, humaine ou agent.
En cas de conflit entre ce fichier et une demande ponctuelle : **ce fichier
gagne**, et on le corrige explicitement dans un commit dédié.

> Révision : 13 octobre 2026 · branche `local-first` · fork `zohac/MiroFish`

---

## 1. Le projet en une minute

MiroFish est un **moteur de simulation sociale**. À partir de documents, il
construit un graphe de connaissances, en déduit une configuration de
simulation, génère des personas, fait vivre des agents (Twitter, Reddit,
parallèle) via `camel-oasis`, puis rédige un rapport.

**Notre travail : faire tourner tout ça sans cloud, dans un environnement
reproductible.**

| Axe | État |
|---|---|
| LLM branché sur l'endpoint gratuit (OpenCode Go) | ✅ fait, testé |
| Cadre de travail : constitution, ADR, CI, suivi | ✅ fait |
| Planification migrée vers `epic-XXX.md` + `story-XXX.md` (ADR 0009) | ✅ fait |
| Graphe de connaissances local (Graphiti + Neo4j) à la place de Zep Cloud | ✅ fait — Epics 001, 002, 003 et 004 clos (632 tests verts) |
| Environnement Docker de référence (Docker-first) | ✅ fait — Epic 005 clos (711 tests verts, Verdict GO) |
| Migration des graphes Zep existants (ou purge sécurisée) | ✅ fait — Epic 006 clos (800 tests verts) |
| Éligibilité des acteurs et fiabilisation des sources | ✅ fait — Epic 009 clos (1157 tests verts, Verdict GO) |
| Ontologie dynamique (v2) | ✅ fait — Epic 007 clos (1550 tests verts, Verdict GO, NO-GO empirique C3 consigné) |
| Support complet de la langue française (Localisation FR) | ✅ fait — Epic 008 clos (1649 tests verts hôte + 9 frontend, Verdict GO) |
| Preuve par les faits simulés, traçabilité et intégrité (OASIS post-simulation, ToolShield, ReportClaim) | ✅ fait — Epic 011 clos (1751 tests verts hôte + 9 frontend, Verdict GO) |
| Fiabilité des acteurs, intégrité des preuves et publication stricte (Fail-Closed, Résolution sans collision) | ✅ fait — Epic 012 clos (1842 tests verts hôte + 9 frontend, Verdict GO) |
| Benchmark LLM du ReportAgent et régénération non destructive (Replay frozen, profils LLM) | ✅ fait — Epic 013 clos (7/7 stories, 2 067 tests verts) |
| Intégrité des preuves de rédaction (régime de provenance, provenance honnête, règle de silence) | 🏗️ en cours — Epic 014 (dossier de plan rédigé, 4 stories prévues) |

- Amont : `666ghj/MiroFish` — AGPL-3.0, ~75 000 ★, très actif
- Fork de travail : `zohac/MiroFish`, branche `local-first`
- État du projet : [`docs/STATUS.md`](docs/STATUS.md)
- Contexte technique détaillé : [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md)

### La tâche du moment

> **L'epic 012 (« Fiabilité des acteurs, intégrité des preuves et publication stricte ») est intégralement clos avec succès (6/6 stories validées — 1 842 tests verts sur l'hôte + 9 tests Node frontend, VERDICT GO).**
>
> **L'epic 013 (« Benchmark LLM du ReportAgent et régénération non destructive sur simulation existante ») est en cours de développement.**
> Dossier de plan : [`docs/plans/013-benchmark-llm-report-replay/`](docs/plans/013-benchmark-llm-report-replay/prd.md) (`prd.md`, `architecture.md`, `epic-013.md`, `story-013-1.md` à `story-013-5.md`).
> Objectif : permettre la régénération de rapports en mode replay à preuves figées (`replay_frozen`), injecter une configuration LLM dédiée par job (`ReportLLMProfile`), isoler chaque génération sous `reports/<report_id>/` sans écrasement destructif, et mener un benchmark A/B rigoureux (notamment `gemini-3.8-flash` en `medium` vs `high` sur le serveur local Antigravity, puis sur OpenCode GO).
> La story **013-1** (« Configuration LLM dédiée au ReportAgent et support effectif de l'effort ») est validée (`done`, revue BMAD 4 couches, 1 852 tests verts). La story **013-2** (« Mode replay à preuves figées et capture de l'empreinte SHA-256 ») est validée (`done`, revue BMAD 4 couches, 1 869 tests verts sur l'hôte + 9 tests frontend Node). La story **013-3** (« Isolation multi-rapports sous reports/<report_id>/ et API d'historique ») est validée (`done`, revue BMAD 4 couches, 1 881 tests verts sur l'hôte + 9 tests frontend Node). La story **013-4** (« Télémétrie d'usage, mesure des temps et plafonds budgétaires ») est validée (`done`, deux passes de revue BMAD 4 couches, 14 patches appliqués, 1 939 tests verts sur l'hôte + 9 tests frontend Node). La story **013-5** (« Interface Vue 3 Step 4 : sélecteur de rapport, régénération et comparaison ») est validée (`done`) : sélecteur d'historique synchronisé à la route `/report/<report_id>`, dialogue de régénération par `profile_id` via un nouveau `GET /api/report/profiles`, panneau de comparaison avec verdict de comparabilité fondé sur l'empreinte SHA-256 des preuves, diff par section, audit téléchargeable par version, bandeau de télémétrie, affichage Fail-Safe des `stop_reason` et des métriques indisponibles. Revue BMAD 4 couches : 9 findings corrigés, dont 2 que **seule la vérification visuelle sur la stack Docker a révélés** (le verdict de comparabilité ne lisait pas la forme de donnée réellement consommée par l'IHM ; le sélecteur de version était emporté par le défilement automatique des journaux). **2e revue BMAD 4 couches (20 octobre 2026)** : 23 correctifs appliqués, 2 décisions arbitrées par l'utilisateur, 3 différés, 8 rejets (dont 4 `false` réfutés par lecture du code). Deux défauts lourds, invisibles aux tests : le dialogue de régénération interdisait le rejeu figé dès la 2e génération (`currentHasSnapshot` ne regardait que l'entrée provisoire, sans champ d'instantané — donc `live` présélectionné, et des rapports non comparables) ; et un rapport corrompu inscrit dans `report_history.json` restait listé avec son empreinte périmée (donc une version que l'IHM ne pouvait pas ouvrir, et un verdict de comparabilité fondé sur un rapport sans contenu). Décisions : le chemin `llm_profile` en ligne est **aligné sur le catalogue** (`base_url`/`api_key` refusés, facturation non déclassable, plafonds non relevables, `profile_id` dérivé du couple modèle/effort) et `provider_id` désigne **la passerelle qui a servi**. **Correction refusée après vérification** : le verdict « comparable » sur la seule égalité du `snapshot_id` est correct (uuid par capture ⇒ identité de la capture). **Divergence assumée et mesurée** : l'empreinte SHA-256 prime sur l'identifiant d'instantané — ce dernier étant un uuid de capture et non une adresse de contenu, la règle littérale de la story aurait déclaré non comparables tous les couples A/B de l'Epic 013 ; la story 013-6 doit s'appuyer sur cette sémantique. Prochaine étape : benchmark **013-6**.
>
> La story **013-6** (« Banc de benchmark contrôlé A/B et qualification globale de l'Epic 013 ») est validée (`done`) : moteur de score pur et fermé (`backend/app/utils/report_benchmark_score.py`, grille versionnée `1.1.0`, 34 métriques, aucun champ interprétatif), orchestrateur de campagne (`backend/scripts/verifier_benchmark_epic_013.py`, `--dry-run` sans génération, garde-fou de cohérence du graphe par empreinte de contenu), extension de la télémétrie (`cached_tokens`, `finish_reason`), 96 tests hermétiques nouveaux. La campagne réelle a été exécutée sur R7 (`sim_80a54d7bbd7b`) dans la stack Docker de référence : deux variantes `flash-medium` / `flash-high`, un `report_id` chacune, empreinte de référence retrouvée au pré-contrôle, graphe inchangé pendant la campagne — **verdict : comparaison contrôlée**. Revue BMAD 4 couches : 24 correctifs appliqués, 4 points différés, 3 rejets motivés. **La revue aveugle est ensuite remplie** : les deux variantes sont notées **2/5** et les erreurs matérielles majeures sont **communes** aux deux (arc « Émilie » fabriqué alors qu'elle n'a aucune action observée, citations présentées comme verbatim et qui ne le sont pas, souscriptions contredites par le tableau de cohorte du rapport lui-même, « Sources & Provenance » sur-certifiée). `high` consomme ~13 % de tokens de plus sans réduction claire des erreurs : **le critère de décision du PRD source §8 n'est pas rempli, la configuration par défaut reste `medium`**. La grille a été remplie par un agent qui avait déjà lu la correspondance, puis **confirmée par un évaluateur externe indépendant** (ChatGPT, session neuve, sans la correspondance) : notes A = 1/2/3/4/1, B = 0/2/2/4/1 — les deux revues convergent, `high` n'est jamais supérieure à `medium`, **la configuration par défaut reste `medium`**. *Réserve* : les pièces jointes à cette seconde revue portaient l'ancienne simulation `sim_ea4f3cfe1028` au lieu de `sim_80a54d7bbd7b`, donc ses notes des critères 1 et 5 restent provisoires (la consigne exige désormais un contrôle du `simulation_id` des pièces avant l'envoi). **L'Epic 013 est clos** (7/7 stories).
>
> **L'epic 001 (« Épreuve Graphiti local ») est intégralement clos avec un VERDICT GO validé.**
> Les 6 stories ont été menées à bien, testées et revues.
>
> **L'epic 002 (« Interface GraphStore ») est intégralement clos avec succès (6/6 stories done).**
> Les stories 002-1 à 002-6 sont validées (470 tests verts). L'isolation totale est prouvée par AST
> (0 import direct de Zep dans services/ et api/, 0 bifurcation conditionnelle) et les critères C1 à C6 sont satisfaits.
>
> **L'epic 003 (« GraphitiGraphStore : écriture et chemin de lecture ») est intégralement clos avec succès (5/5 stories done).**
> Dossier de plan : [`docs/plans/003-chemin-de-lecture-graphiti/`](docs/plans/003-chemin-de-lecture-graphiti/prd.md) (`prd.md`, `architecture.md`, `epic-003.md`, `rapport-validation-integration.md`).
> Les stories 003-1 à 003-5 sont validées (squelette `GraphitiGraphStore`, write pipeline, cycle de vie, lecture Cypher, voisinage, recherche hybride, adaptation `zep_entity_reader.py`, banc d'intégration réelle contre Neo4j et revues BMad — 562 tests verts).
>
> **L'epic 004 (« Construire un graphe en local sans clé Zep ») est intégralement clos avec succès (5/5 stories done).**
> Dossier de plan : [`docs/plans/004-bascule-sans-zep/`](docs/plans/004-bascule-sans-zep/prd.md) (`prd.md`, `architecture.md`, `epic-004.md`, `rapport-qualification-epic-004.md`).
> Les stories 004-1 à 004-5 sont validées (paramétrabilité universelle LLM, levée des gardes ZEP_API_KEY, ingestion/graphe e2e, personas et simulation e2e, banc de qualification globale local-first et revues BMad — 632 tests verts).
>
> **L'epic 005 (« Environnement Docker de référence — Docker-first ») est intégralement clos avec succès (5/5 stories done).**
> Dossier de plan : [`docs/plans/005-docker-local/`](docs/plans/005-docker-local/prd.md) (`prd.md`, `architecture.md`, `epic-005.md`, `rapport-qualification-epic-005.md`).
> Les stories 005-1 à 005-5 sont validées (Dockerfiles spécialisés locaux, `docker-compose.yml` unifié avec healthchecks, outillage et parité CI sous Docker, persistance Neo4j sur volume nommé, banc de qualification finale Docker avec VERDICT GO et 0 secret — 711 tests verts).
>
> **L'epic 006 (« Migrer un graphe Zep existant — ou acter qu'on jette ») est intégralement clos avec succès (3/3 stories done).**
> Dossier de plan : [`docs/plans/006-migration-donnees-zep/`](docs/plans/006-migration-donnees-zep/prd.md) (`prd.md`, `architecture.md`, `epic-006.md`).
> Objectif : auditer les graphes distants (`auditer_graphes_zep.py`), formaliser l'arbitrage (« Migrer vs Jeter »), outiller le rapatriement direct vers Neo4j (`migrer_zep_vers_graphiti.py`) à coût marginal nul (0 €), valider la relecture applicative (GraphStore, ZepEntityReader, OASIS — C4) avec purge optionnelle sécurisée (`purger_graphes_zep.py`, FR-6).
> Les stories 006-1, 006-2 et 006-3 sont validées (800 tests verts).
>
> **L'epic 009 (« Éligibilité des acteurs et fiabilisation des sources ») est intégralement clos avec succès (4/4 stories done).**
> Dossier : [`docs/plans/009-eligibilite-acteurs-et-sources/`](docs/plans/009-eligibilite-acteurs-et-sources/epic-009.md).
> La story 009-1 est close (`done`) : modèle `ActorEligibility`, classifieur
> agnostique à deux passes (`app/services/actor_classifier.py`), barrière du
> générateur de profils, intégration gestionnaire/routes, preuve de qualification.
> [Mesure réelle C2](docs/plans/009-eligibilite-acteurs-et-sources/mesure-009-1.md) :
> space-bunny, 8/8 acteurs retenus et 0 faux acteur par domaine.
> La story 009-2 est close (`done`) : [ADR 0012](docs/decisions/0012-contrat-de-provenance-graphstore.md)
> (contrat de provenance `GraphStore`) et [ADR 0013](docs/decisions/0013-semantique-des-sources.md)
> (statut de validation, conflits, budget de contexte) acceptés ; modèles
> `source_document.py` et `simulation_brief.py`, extension des deux stores,
> découpage par document à positions exactes, transmission du brief et
> diagnostics de contexte. [Mesure réelle C3](docs/plans/009-eligibilite-acteurs-et-sources/mesure-009-2.md) :
> 2 documents × 2 fragments, 8/8 références documentaires résolues, 8/8 positions
> exactes. Revue BMAD validée avec 3 patches appliqués (1112 tests verts).
> La story 009-3 est close (`done`) : modèle `ActorSelection` et persistance
> atomique `actors.json` rattachée à la simulation avec empreinte SHA-256 déterministe
> et journal d'audit ; endpoints Flask `POST /api/simulation/actors/preview`
> (cache serveur, recalcul forcé, conflits ouverts) et `POST /api/simulation/actors/review`
> (409 sur désynchronisation optimiste, rejet strict des non-acteurs éligibles, justification
> obligatoire) ; intégration fluide dans `prepare_simulation` (parcours simple sans friction,
> transmission des rôles qualifiés aux personas, invalidation d'obsolescence et blocage
> volontaire `block_on_review`/`block_on_conflict`) ; IHM Vue 3 (`Step2EnvSetup.vue`) avec
> panneau de prévalidation, badges d'éligibilité, dialogue modal d'arbitrage motivé,
> alertes de conflits et cases de blocage (1130 tests verts).
> La story 009-4 est close (`done`, revue BMAD code-review du 12 octobre 2026, 10 patches de moyen/haut impact appliqués et **1157 tests verts** — voir `### Review Findings` dans la story) : outils de provenance `ZepToolsService` (classification
> étanche en 5 origines, `ProvenanceRecord`, `episodes`, fragments `char_start`/`char_end`),
> vérificateur d'actions simulées `SimulationActionVerifier` (règle anti-affabulation C7,
> `event_id` déterministe, contrôle verbatim exact des citations, formatage des contradictions),
> génération de la section « Sources & Provenance » dans `ReportAgent` avec étanchéité NFR-5,
> banc d'orchestration globale `backend/scripts/verifier_qualification_epic_009.py` validant
> les critères C1 à C7 de bout en bout avec [rapport de qualification formel](docs/plans/009-eligibilite-acteurs-et-sources/rapport-qualification-epic-009.md)
> et **VERDICT GO** validé (1157 tests verts sur l'hôte, 0 échec, revue BMAD 4 couches conforme).

La **story 007-2 est close** après revue BMAD, 14 correctifs appliqués et
qualification réelle C2 Graphiti : [12 cas conformes](docs/plans/007-ontologie-dynamique/mesure-007-2.json).
L’ADR 0016 limite la garantie à Graphiti ; l’ADR 0017 formalise la politique
durable et la rétrogradation transactionnelle. Le refus strict Zep reste
explicite. **007-3 est close (`done`)** : entrées figées (corpus 10K/50K), température zéro,
projection canonique, sonde autonome `verifier_ontology_regeneration.py`.
L'épreuve réelle contre Neo4j et `gpt-6.1-sol` valide la pose (< 10 ms), mais
le non-déterminisme nominal et le délai d'inférence (91–193 s) inhérents au LLM
sont actés en NO-GO empirique C3 dans [`mesure-007-3-hote.json`](docs/plans/007-ontologie-dynamique/mesure-007-3-hote.json).
Revue contradictoire BMAD 4 couches validée (7 patches appliqués, 1 différé, 5 rejets).
**007-4 est close (`done`)** : modèle `OntologyVersion` immuable (`ont_<uuid12>`), magasin atomique `OntologyVersionStore`,
extension monotone du `Project` (`applied_ontology_id`, `applied_ontology_version`, `ontology_history`),
et câblage réactif des événements : E1 (ajout de document, préservation des labels existants C4),
E2 (diff brief substantiel `difflib.SequenceMatcher.ratio() < 0.95`), E3 (demande explicite API `POST /api/project/<id>/ontology/regenerate`),
et E4 (initialisation atomique v1 lors de la création de projet). Endpoints d'API dans `backend/app/api/project.py`
et rattachement de la version aux avertissements `GraphValidationWarning` (AC6). Revue contradictoire BMAD 4 couches validée.
**007-5 est close (`done`)** : composition `ActorClassifier` / ontologie dynamique (AC1-AC5), propagation
dans `SimulationConfigGenerator` et cohérence de projet E5 (AC6), isolation hermétique des tests.
Revue contradictoire BMAD 4 couches validée (5 patches appliqués, 1 différé, 2 rejets).
**007-6 est close (`done`)** : audit d'ontologie appliquée dans `ReportAgent` et exposition outillée LLM / API.
Sous-section « ### 6. Ontologie appliquée (Epic 007, FR-6) » intégrée dans `build_sources_provenance_section()`
(types d'entités avec `InformationOrigin`, relations, métadonnées de version `ont_<uuid12>`, politique et avertissements).
Omission conditionnelle stricte sur projet sans ontologie appliquée (AC2, C7). Outil LLM `get_applied_ontology`
déclaré dans `_define_tools` et exécutable dans `_execute_tool` avec formatage JSON structuré. Décompte tolérant
aux pannes `_get_ontology_instance_counts` (AC5, NFR-4). Endpoint `GET /api/project/<id>/ontology` consolidé
(AC7, PRD Q4) avec politique, avertissements et statistiques sous `include_counts=true` et restitution sécurisée des connexions via `release_graph_store`.
Revue contradictoire BMAD 4 couches validée.
**007-7 est close (`done`)** : banc d'orchestration global autonome `backend/scripts/verifier_qualification_epic_007.py` évaluant de bout en bout l'ensemble des critères C1 à C8. Consignation du constat empirique C3 sur modèle externe amont (`gpt-6.1-sol`, 91–193 s, variations nominales) en NO-GO empirique C3 sans impacter le moteur local. Rapport formel `docs/plans/007-ontologie-dynamique/rapport-qualification-epic-007.md` versionné avec **VERDICT GO**. 12 tests hermétiques dédiés (`test_verifier_qualification_epic_007.py`). Revue contradictoire BMAD 4 couches validée avec 8 patches appliqués. **Epic 007 intégralement clos avec succès (7/7 stories done, 1550 tests verts sur l'hôte)**.
**010-1 est close (`done`)** : arrêt déterministe (`--no-wait`) injecté par défaut dans `SimulationRunner._start_simulation` pour `run_parallel_simulation.py`, Twitter et Reddit, avec support du repli interactif `keep_alive_on_completion: bool | None = None` (API `/start` et config) et persistance `SimulationRunState`. Supervision active de fin de cycle dans `_monitor_simulation` via `_check_all_platforms_completed`, préservation stricte du mode persistant (Patch 1 BMAD), repli IPC `send_close_env()` à 5 s et terminaison forcée de sécurité à 10 s (NFR-3). Transition déterministe vers `RunnerStatus.COMPLETED` avec horodatage ISO 8601 (`completed_at`) et intégrité de la barrière mémoire Neo4j sous verrou (AC5). 11 tests unitaires hermétiques dédiés (`test_simulation_runner_completion.py`, dont 3 issus de la revue BMAD). Revue contradictoire BMAD 4 couches validée (4 patches appliqués). **1562 tests verts sur l'hôte**.
**010-2 est close (`done`)** : réconciliation d'état OS/cache et résilience IHM (`Step3Simulation.vue`). Réconciliation de vivacité dans `SimulationRunner.get_run_state` vérifiant `process.poll()` pour les processus gérés et `os.kill(pid, 0)` / `OpenProcess` (`STILL_ACTIVE`) pour les PID système, avec bascule sous verrou de finalisation vers les statuts terminaux réels (`COMPLETED`, `STOPPED` ou `FAILED`), élimination des statuts orphelins sans PID et fermeture des descripteurs de logs. Invalidation de cache temps réel par comparaison du `mtime` de `run_state.json`. Détection de complétion par les faits côté IHM Vue 3 dans `Step3Simulation.vue` (`factsCompleted` via `progress_percent >= 100` et achèvement des plateformes actives) permettant le déblocage immédiat de la phase 2 et du bouton de génération de rapport, maintien du polling jusqu'à la fin de la barrière mémoire et tolérance aux erreurs 409 transitoires. 9 tests unitaires hermétiques dédiés créés dans `backend/tests/test_simulation_runner_reconciliation.py`. Revue contradictoire BMAD 4 couches validée (4 patches appliqués). **1571 tests verts sur l'hôte**.
**010-3 est close (`done`)** : sécurisation thread-safe de `SentenceTransformerEmbedder._encode_sync` (sérialisation de l'inférence PyTorch via `self._lock` éliminant les collisions de meta tensors) et drain mémoire résilient dans `ZepGraphMemoryUpdater.stop(strict=False)` et `ZepGraphMemoryManager.stop_updater` assurant la complétion nominale vers `RunnerStatus.COMPLETED` même en présence de défaillances mineures de lots secondaires. Purge de `_pending_episode_uuids` sécurisée sous bloc `finally:`. 9 tests unitaires hermétiques dédiés (`test_sentence_transformer_thread_safety.py`). Revue contradictoire BMAD 4 couches validée (2 patches appliqués). **Epic 010 intégralement clos avec succès (3/3 stories done, 1580 tests verts sur l'hôte)**.
**008-1 est close (`done`)** : dictionnaire complet de traduction française `locales/fr.json` (679 clés sur 17 sections, parité 100 % stricte avec `en.json`, 0 orpheline, 0 manquante, variables `{var}` conformes), intégration backend `normalize_locale()` RFC 7231 (`backend/app/utils/locale.py`), 7 tests hermétiques dédiés (`test_i18n_parity.py`). Revue contradictoire BMAD 4 couches validée.
**008-2 est close (`done`)** : intégration et bascule IHM frontend Vue 3 (`LanguageSwitcher.vue`, formats régionaux `fr-FR` via `regionalFormat.js`, synchronisation de l'en-tête Axios `Accept-Language`, persistance `localStorage`). 9 tests Node passés (`pnpm --dir frontend test`), build Vite réussi. Revue contradictoire BMAD 4 couches validée avec 5 patches appliqués (fuite `'FINALIZING'` résolue, gardes défensives sur types coercitifs, synchronisation CI) et 5 travaux différés consignés dans `docs/deferred-work.md`. Validation visuelle Docker réelle réussie à 100 % sur navigateurs bureau (rendu mobile amont documenté et différé pour story ergonomique dédiée). DoD 100 % satisfait. Filet global : **1618 tests verts sur l'hôte**, 9 tests frontend Node.
**008-3 est close (`done`)** : locale canonique persistée par simulation (`SimulationState.locale`), propagation thread-safe Flask/threads/processus OASIS (`use_locale`), prompts LLM et fallbacks localisés (plan_outline, ReACT, simulation_config_generator, chat), neutralisation des consignes antérieures lors des régénérations et respect strict des invariants techniques (clés JSON anglaises, types PascalCase, relations UPPER_SNAKE_CASE, enums et citations verbatim fidèles). 59 tests hermétiques passants (52 dans `test_simulation_locale.py`, 7 dans `test_verifier_qualification_epic_008_3.py`). Banc d'évaluation autonome sous conteneur Docker avec modèle réel validant AC1–AC8 avec **VERDICT GO** formalisé dans [`rapport-qualification-008-3.md`](docs/plans/008-support-langue-francaise/rapport-qualification-008-3.md). **Epic 008 intégralement clos avec succès (3/3 stories done, 1649 tests verts sur l'hôte + 9 tests frontend Node)**.
**011-1 est close (`done`)** : maintien en vie interactif du processus OASIS post-rounds avec découplage de la complétion logique (`RunnerStatus.COMPLETED` et drain mémoire Neo4j sous verrou dès la fin des plateformes), rétablissement opérationnel d'`interview_agents_batch` / `interview_agents` en état `COMPLETED`, repli hors-ligne robuste par synthèse d'archives (`_synthesize_offline_interviews` avec balises explicites sans rupture ReACT), clôture différée ordonnée `close_simulation_environment(simulation_id)` déclenchée en fin de génération de rapport (`finally:` de `ReportAgent` et endpoint API), et protection anti-zombie via watchdog d'inactivité de 15 minutes. 13 tests unitaires hermétiques dédiés (`test_simulation_interactive_lifecycle.py`). Revue contradictoire BMAD 4 couches validée avec 4 patches appliqués (résilience COMPLETED face aux signaux de fin de vie, propagation du mode interactif, préservation completed_at, ponctuation). **1663 tests verts sur l'hôte**.
**011-2 est close (`done`)** : registre unifié d'événements observés (`OasisLogReaderService`, modèle `EvidencePack`, record `ObservedEvent`) avec ingestion multi-sources JSONL (`twitter`, `reddit`, racine) et SQLite (`post`, `comment`), calcul déterministe d'`event_id` (`SimulationActionVerifier.compute_event_id`), cache dynamique indexé invalidé par `mtime` et outil ReACT direct `query_simulation_events`. Bouclier défensif `ToolShield` interceptant les requêtes vides ou sérialisées incomplètes (`quick_search`, `panorama_search`, `insight_forge`), injectant le titre de section ou l'exigence de simulation en repli et protégeant le quota de 5 itérations ReACT contre `GraphValidationError`. Déterminisme nominatif strict au Round 0 dans `SimulationConfigGenerator` éliminant 100 % des inversions de personas. Revue contradictoire BMAD 4 couches validée avec 8 patches appliqués (sécurisation numérique typée des logs JSONL/SQLite, fermeture résiliente SQLite sous `finally:`, assainissement étendu ToolShield, conversions typées dans `_execute_tool`, correspondances partielles nominatives durcies, 4 nouveaux tests unitaires hermétiques). 17 tests hermétiques dédiés (`test_oasis_log_reader_toolshield.py`). **1679 tests verts sur l'hôte**.
**011-3 est close (`done`)** : contrat structuré `ReportClaim` (`ClaimKind`, `VerificationStatus`, conteneur `ReportClaimRegistry` avec calcul des statistiques et sérialisation atomique `report_claims.json`), typage épistémique strict des sources `EpistemicSourceKind` (`CANONICAL_DOCUMENT`, `HISTORICAL_CASE`, `PERSONA_SPECIFICATION`, `SCENARIO_BRIEF`) dans `source_document.py`, et barrière hermétique C5 interdisant catégoriquement la qualification en `DOCUMENTARY` des faits issus de personas fictifs (forçage `InformationOrigin.HYPOTHESIS`). Règle anti-affabulation C4 dans `SimulationActionVerifier.verify_report_claim` déclassant systématiquement les intentions non exécutées vers `ClaimKind.REPORTED_INTENTION` et `VerificationStatus.UNSUPPORTED`. Contrôle verbatim exact et normalisé des citations simulées (`verify_simulated_citation`). Extraction, vérification et persistance de `simulations/<sim_id>/report_claims.json` dans `ReportAgent`. Revue contradictoire BMAD 4 couches validée avec 8 patches appliqués (conformité roundtrip `SourceReference.from_dict`, durcissement de matching normalisé, gestion d'erreurs défensive dans `ReportAgent`, écriture atomique du registre, sécurisation `NoneType`, asymétrie de citation et barrière C5 anonyme). 17 tests hermétiques dédiés (`test_report_claim_epistemic.py`). **1696 tests verts sur l'hôte**.
**011-4 est close (`done`)** : modèle de couverture de cohorte (`CohortCoverageTable`, `CohortMemberStatus`), marquage déterministe des personas silencieux (`present_no_action`), barrière de synthèse anti-biais de confirmation (`check_executive_summary_bias`), garde-fou d'horizon temporel simulé (`TimeHorizonGuard`, FR-08, C8), neutralisation des métriques quantitatives fantômes (`_GHOST_METRIC_PATTERNS`), extraction et injection obligatoire de la section d'objections non levées et limites dans `ReportAgent` (FR-07, C7), priorité stricte de contradiction anti-affabulation C7 dans `verify_report_claim`, appariement nominatif exact et extraction textuelle récursive d'arguments d'actions, et internationalisation bilingue FR/EN des diagnostics et tableaux Markdown. Revue contradictoire BMAD 4 couches validée avec 5 patches appliqués. 23 tests hermétiques dédiés (`test_cohort_coverage_time.py`). **1719 tests verts sur l'hôte**.
**011-5 est close (`done`)** : modèle `QualityGateResult` (`backend/app/models/report_quality.py`), extension de `ReportStatus.FAILED_VALIDATION`, composant anti-troncature `SectionCompletionGuard` avec détection fine et reprise ciblée (max 2 passes sans doublon ni répétition), 5 contrôles préalables de publication (intégrité structurelle, anti-troncature, locale FR, limites obligatoires, intégrité des claims sans affabulation, C9), service d'audit exportable `SimulationAuditService` réunissant l'archive ZIP autonome des 8 artefacts de preuve canoniques scellée par SHA-256 (C10), endpoints API REST (`/api/report/<report_id>/quality`, `/api/report/<report_id>/audit/download`, `/api/report/simulation/<sim_id>/audit/download`) et interface utilisateur `Step4Report.vue` (badges d'état qualité, carte dépliable des vérifications, bouton de téléchargement de l'archive ZIP). 20 tests unitaires hermétiques dédiés (`test_report_quality_gate_audit.py`). Revue contradictoire BMAD 4 couches validée avec 8 patches appliqués. **1739 tests verts sur l'hôte (+ 9 tests frontend Node)**.
**011-6 est close (`done`)** : banc de qualification de bout en bout multi-domaines (`backend/scripts/verifier_qualification_epic_011.py`) évaluant de bout en bout l'ensemble des critères C1 à C11 sur 3 corpus distincts (SaaS Keova, concertation publique territoriale, régulation/infrastructure télécom). Rapport formel [`rapport-qualification-epic-011.md`](docs/plans/011-preuve-simulation-et-fiabilite-rapport/rapport-qualification-epic-011.md) versionné avec **VERDICT GO**. 15 tests hermétiques dédiés (`test_verifier_qualification_epic_011.py`). Revue contradictoire BMAD 4 couches validée avec 8 patches appliqués. **Epic 011 intégralement clos avec succès (6/6 stories done, 1755 tests verts sur l'hôte + 9 tests frontend Node)**.
**012-1 est close (`done`)** : résolution stricte des identités d'acteurs et couverture de cohorte sans collision (`AgentIdentityResolver`, normalisation canonique Unicode NFKD stricte `==` sans inclusion heuristique par sous-chaîne, 23 événements d'`Agent_1` et 18 d'`Agent_16` strictement disjoints éliminant l'anomalie R6 `COVERAGE_ALIAS_COLLISION`, filtrage strict des entités inéligibles Stripe/CPAM, dédoublonnage des alias techniques `Agent_X` en faveur des personas nommés et attribution univoque d'`event_id`). 11 tests unitaires hermétiques dédiés (`test_cohort_identity_resolution.py`). Revue contradictoire BMAD 4 couches validée avec 4 patches appliqués (sécurisation falsy 0, conversion int défensive, garde simulation_id vide, initialisation complète alias/noms). **1771 tests verts sur l'hôte (+ 9 tests frontend Node)**.
**012-2 est close (`done`)** : rôles de scénario et statuts de décision d'adoption déterministes. Suppression définitive du forçage aveugle `ActorRole.PERSON -> ScenarioRole.PROSPECT` au profit d'une hiérarchie explicite (`simulation_brief` > `simulation_config.json` > `actor_selection` > `ScenarioRole.UNKNOWN`). Enrichissement complet de `ScenarioRole` (`FOUNDER`, `TEAM_MEMBER`, `EXISTING_USER`, `PROSPECT`, `PARTNER`, `INSTITUTION`, `UNKNOWN`) et `DecisionStatus` (`NOT_APPLICABLE`, `NO_DECISION`, `INTERESTED`, `DEMO_REQUESTED`, `HESITANT`, `REJECTED_EXPRESSED`, `ADOPTED_VERIFIED`, `PRESENT_NO_ACTION`) avec rétrocompatibilité transparente ascendante (`ADOPTED`, `REJECTED`, `UNDECIDED`). Règle anti-affabulation C3 : interdiction absolue d'attribuer `ADOPTED` par simple absence d'objections ou posts anodins (qualifiés `NO_DECISION` ou `INTERESTED`), statut `ADOPTED_VERIFIED` strictement conditionné à des preuves d'engagement probantes. Attribution systématique de `NOT_APPLICABLE` pour les fondateurs, collaborateurs internes et institutions non clientes, et assainissement du calcul d'`adoption_rate` excluant strictement `NOT_APPLICABLE` du dénominateur. 14 tests hermétiques dédiés (`test_cohort_roles_and_decisions.py`). Revue contradictoire BMAD 4 couches validée avec 5 patches appliqués. **1785 tests verts sur l'hôte (+ 9 tests frontend Node)**.
**012-3 est close (`done`)** : extraction d'assertions assainie et réconciliation déterministe avec l'`EvidencePack`. Élimination catégorique des faux agents (« Si », « Dès », conjonctions et débuts de phrase), exclusion formelle des titres Markdown (`#`, `##`, `###`), et validation nominative stricte par `AgentIdentityResolver` (`get_known_names`, `resolve_name`). Extraction des affirmations d'actions observées sans exiger d'identifiants techniques `evt_*` littéraux dans le texte Markdown rédigé. Réconciliation déterministe sémantique et temporelle dans `SimulationActionVerifier.verify_report_claim` (résolution univoque des acteurs sans matching par sous-chaîne `in`, corrélation de contenu et verbatims). Règle anti-affabulation C4 durcie : déclassement systématique en `REPORTED_INTENTION` / `UNSUPPORTED` avec justification dans `limitations` en l'absence de trace concrète, et interdiction formelle d'inférer des transactions commerciales (achats/abonnements) depuis de simples posts de réseaux sociaux. 15 tests hermétiques dédiés (`test_report_claims_reconciliation.py`). Revue contradictoire BMAD 4 couches validée avec 10 patches appliqués. **1800 tests verts sur l'hôte (+ 9 tests frontend Node)**.
**012-4 est close (`done`)** : barrière de publication « Fail-Closed » et états de certification du rapport. Modélisation formelle de `PublicationStatus` (`draft`, `needs_review`, `verified_publishable`, `failed_validation`). Conditionnement strict de `is_publishable = True` à l'état `verified_publishable` (avec option de consultation sous réserve pour `needs_review`, et interdiction formelle de publication certifiée pour `failed_validation`). Détection et rejet immédiat en `failed_validation` de l'anomalie R6 où des actions simulées sont affirmées mais avec 0 claim vérifié (`verification_ratio == 0.0` / QA-08). Gestion stricte de l'absence de registre `report_claims.json` basculant en échec si des actions sont relatées ou en statut informatif pour un rapport théorique (QA-09). Seuils stricts de preuve factuelle ($\ge 80\ %$ pour `verified_publishable`, $50\text{--}79\ %$ pour `needs_review`, $< 50\ %$ pour `failed_validation`). Interdiction d'affabulation commerciale bloquant en échec toute cohorte comportant des personas au statut `ADOPTED_VERIFIED` sans claim d'adoption prouvé (vocabulaire d'action bilingue FR/EN). Désérialisation rétrocompatible transparente dans `QualityGateResult.from_dict` avec lookup Enum standard. Interface utilisateur Vue 3 (`Step4Report.vue`) adaptée avec badges dynamiques, affichage réactif de la carte diagnostic pour `needs_review`, internationalisation trilingue `fr.json`, `en.json`, `zh.json`. Alignement du cycle de vie `ReportStatus` dans `ReportAgent` préservant l'accessibilité en `needs_review`. 31 tests hermétiques au vert dans `test_report_quality_gate_audit.py`. Revue contradictoire BMAD 4 couches validée avec 7 patches appliqués. **1812 tests verts sur l'hôte (+ 9 tests frontend Node)**.
**012-5 est close (`done`)** : séparation épistémique des sources, intégrité du brief et détection de contradictions. Prévalence épistémique absolue de `epistemic_kind` sur `DocumentRole` dans `source_document.py` (`derive_epistemic_kind`, `classify_record_origin`), interdisant formellement qu'un fragment issu de `PERSONA_SPECIFICATION` ou `SCENARIO_BRIEF` soit qualifié de contexte historique documentaire au profit de `InformationOrigin.HYPOTHESIS` garanti (QA-10). Audit structuré du manifeste de sources (`audit_source_manifest`, `SourceManifestAuditResult`) identifiant les discordances déclaratives (`METADATA_ROLE_EPISTEMIC_MISMATCH`) et les sources non découpées (`EMPTY_OR_UNCHUNKED_SOURCE`) sans écrasement silencieux avec typage défensif sur `total_chunks`. Inférence traçable d'horizon temporel dans `simulation_brief.py` (`extract_inferred_horizon`) avec motif regex universel déterministe, accord grammatical et diagnostic des lacunes de brief (`audit_brief`) avec repli explicite `"unknown"` (QA-11). Restitution exhaustive de la totalité des documents sources dans `ReportAgent.build_sources_provenance_section` incluant les sources `total_chunks == 0` et `unvalidated`. Contrat de faits non négociables de l'entreprise dans `SimulationActionVerifier.check_company_facts_contradiction` déclassant immédiatement en `VerificationStatus.CONTRADICTED` toute allégation de porte-parole interne (`FOUNDER`, `TEAM_MEMBER`) contredisant une source canonique validée, avec chargement direct des textes depuis le disque, découpage propositionnel robuste protégeant les décimaux, et détection d'élisions françaises dans `_content_terms` (QA-12). Généricité absolue garantie sans terme en dur (NFR-1). 15 tests hermétiques dédiés dans `test_epistemic_sources_and_brief.py`. Revue contradictoire BMAD 4 couches validée avec 5 patches appliqués. **1827 tests verts sur l'hôte (+ 9 tests frontend Node)**.
**012-6 est close (`done`)** : banc de qualification sur cas réel R6, complétude du manifeste et non-régression. Script autonome d'orchestration globale `backend/scripts/verifier_qualification_epic_012.py` validant de bout en bout l'ensemble des critères C1 à C8. Fixture synthétique anonymisée de l'audit R6 (`backend/tests/fixtures/qualification_epic_012/r6_bundle/`, 10 artefacts intègres dont `actors.json` avec 44 entités dont Stripe/CPAM, `observed_events.jsonl` avec 786 événements, `cohort_coverage.json` avec 63 membres, `report_claims.json` avec 258 claims, brief, rapport, manifestes) sans aucune fuite de clés ni de tokens (NFR-1). Preuve formelle de bascule Fail-Closed catégorique : invalidation immédiate de l'ancien export erroné (rejet en `PublicationStatus.FAILED_VALIDATION`, `is_publishable=False` / C7 / QA-08 / QA-13) et passage conforme en `PublicationStatus.VERIFIED_PUBLISHABLE` (`is_publishable=True`) du run réconcilié. Complétude et étanchéité de `run_manifest.json` produit par `SimulationAuditService` (résolution dynamique du commit Git `git_commit`, horodatage `completed_at` en ISO 8601, cohérence de `time_horizon` et zéro fuite de secret). Rapport formel de qualification [`rapport-qualification-epic-012.md`](docs/plans/012-fiabilite-preuves-et-publication/rapport-qualification-epic-012.md) consigné avec **VERDICT GO**. Suite hermétique dédiée (`backend/tests/test_verifier_qualification_epic_012.py`, 12 tests unitaires passants). Revue contradictoire BMAD 4 couches validée. Filet global de tests porté à **1 839 tests unitaires et d'intégration au vert sur l'hôte** (0 échec) + **9 tests Node frontend**. **Epic 012 intégralement clos avec succès (6/6 stories done)**.

---

## 2. Règles

### 2.1 Clean architecture, SOLID, KISS, DRY

Les dépendances pointent **vers l'intérieur**, jamais l'inverse :

```
api/  →  services/  →  utils/
(HTTP)   (métier)     (clients, helpers purs)
```

- `api` connaît `services`. `services` connaît `utils`. **Jamais l'inverse.**
- Aucune dépendance circulaire. `utils` ne connaît aucun service métier.
- **Une interface exige ≥ 2 implémentations réelles.** Avant d'en créer une,
  vérifier qu'il y a bien deux cas concurrents (Zep **et** Graphiti).
- **DRY sur le graphe** : la connaissance « comment dialoguer avec le store »
  vit dans l'implémentation, **jamais** dans les appelants. Un `if zep else
  graphiti` dans un service est un bug de conception.
- **KISS** : pas de couche d'abstraction spéculative, pas de configuration
  dynamique si un booléen suffit.

### 2.2 Tout code produit est testé

Une fonctionnalité sans test **n'est pas terminée**. Le filet courant du
20 octobre 2026 compte **2067 tests collectés et réussis sur l'hôte (+ 43 tests frontend Node) ; 1968 réussis + 3 ignorés sous
Docker** — il doit grossir, jamais rétrécir. Référence post-009-1 : 924 hôte /
921 + 3 Docker ; post-009-2 : 1112 hôte / 1109 + 3 Docker ; post-009-3 : 1130
hôte ; post-009-4 : 1157 hôte (1145 initiaux + 12 tests BMAD) ; post-007-1 :
**1367** (1157 + 210 tests hermétiques, relectures comprises) ; post-007-2 :
**1431** (1367 + 64 cas, dont les régressions de revue) ; post-007-3 :
**1459** (1431 + 23 tests de sonde hermétiques + 5 tests BMAD) ; post-007-4 :
**1485** (1459 + 26 tests hermétiques, événements E1-E4 et magasin versionné compris) ; post-007-5 :
**1519** (1485 + 34 tests hermétiques, composition acteurs et cohérence projet) ; post-007-6 :
**1537** (1519 + 18 tests hermétiques, audit rapport, outil LLM et 3 patches BMAD compris) ; post-007-7 :
**1550** (1537 + 13 tests hermétiques, banc de qualification et 8 patches BMAD compris) ; post-010-1 :
**1562** (1550 + 12 tests hermétiques nets, arrêt déterministe, complétion automatique et 4 patches BMAD) ; post-010-2 :
**1571** (1562 + 9 tests hermétiques nets, réconciliation vivacité OS, autorité disque, résilience IHM et 4 patches BMAD) ; post-010-3 :
**1580** (1571 + 9 tests hermétiques nets, thread-safety PyTorch, drain mémoire tolérant et 2 patches BMAD) ; post-008-1 :
**1589** (1580 + 7 tests hermétiques dédiés parité i18n et normalisation locale RFC 7231) ; post-008-2 :
**1618** (1589 + 29 tests, dont 9 tests Node frontend i18n/formats régionaux et suite backend consolidée) ; post-008-3 :
**1649** (1618 + 31 tests hermétiques nets, dont fallbacks config/rapport, boucle ReACT fr et banc de qualification 008-3) ; post-011-1 :
**1663** (1649 + 14 tests hermétiques nets, dont maintien en vie interactif OASIS post-rounds, rétablissement interview_agents, clôture différée et 4 patches BMAD) ; post-011-2 :
**1679** (1663 + 16 tests hermétiques nets, dont registre OasisLogReaderService, EvidencePack, ToolShield, déterminisme nominatif Round 0 et 8 patches BMAD) ; post-011-3 :
**1696** (1679 + 17 tests hermétiques nets, dont contrat ReportClaim, typage épistémique EpistemicSourceKind, barrière hermétique C5, règle anti-affabulation C4, vérification verbatim et 8 patches BMAD) ; post-011-4 :
**1719** (1696 + 23 tests hermétiques nets, dont couverture de cohorte, garde-fou d'horizon temporel, neutralisation de métriques fantômes, section limites/objections, règle C7 prioritaire et 5 patches BMAD) ; post-013-1 :
**1852** (1719 + 133 tests hermétiques nets, dont profil LLM dédié et effort effectif) ; post-013-2 :
**1869** (+ 17 tests, instantané de preuves et empreinte SHA-256) ; post-013-3 :
**1881** (+ 12 tests, isolation multi-rapports et API d'historique) ; post-013-4 :
**1939** (+ 58 tests, télémétrie d'usage et plafonds budgétaires) ; post-013-5 :
**1955** (1939 + 16 tests hermétiques, catalogue de profils, empreinte dans l'historique et robustesse face aux rapports corrompus) ; post-2e revue 013-5 :
**1971** (+ 16 tests, profil client aligné sur le catalogue, alias de passerelle, rapport corrompu indexé, plan dégradé, message d'arrêt), avec **43 tests Node frontend** (10 i18n + 33 comparaison de rapports) ; post-013-6 :
**2067** (+ 96 tests hermétiques nets : moteur de score pur, banc de benchmark, extension de télémétrie `cached_tokens`/`finish_reason`), avec **43 tests Node frontend** (inchangés : la story ne touche pas le frontend).

Les 3 tests ignorés sous Docker cherchent le binaire `docker` — absent de
l'image `backend`, qui n'embarque pas le CLI Docker. Ils sont hermétiques mais
ne sont pas exécutables **dans** le conteneur ; leurs motifs sont consignés dans
la story 007-1.

Règles de qualité des tests :

- **Hermétiques** : jamais de dépendance à `.env` ni à l'ordre d'exécution.
  Si un test casse selon la machine, mocker l'environnement
  (`monkeypatch.delenv(...)`) plutôt que figer une valeur.
- **Pas de réseau réel** : les clients HTTP et LLM sont mockés. Un test qui
  appelle l'API ne teste pas notre code.
- **Un test = une intention.** Si le nom du test contient un « et », il faut
  deux tests.
- **Vérifier qu'un test teste vraiment.** Une fixture dont la mutation ne
  correspond pas au fichier réel fait passer un test sans rien vérifier — pire
  que pas de test. Quand un test échoue, vérifier d'abord qu'il reproduit le
  défaut qu'il prétend couvrir.
- Les tests qui touchent un contrat Zep existant sont notre filet de sécurité
  pendant la migration : ils doivent rester verts **avant et après** chaque
  refactor.

### 2.3 Docs et décisions dans `/docs`

- **Contexte technique** → `docs/LOCAL-FIRST.md`
- **État du projet** → `docs/STATUS.md`
- **Décision d'architecture** → un ADR dans `docs/decisions/NNNN-titre.md`
- **Planification** → `docs/plans/<NNN>-<slug>/`
- **Schéma** → `docs/architecture/`, diagrammes Mermaid
- `AGENTS.md` = constitution + index, mis à jour en fin de session dès que le
  cadre change.

Un ADR est **immuable** une fois accepté. Pour le changer, on écrit un nouvel
ADR qui le précise ou le supersède — on ne réécrit pas l'histoire.

### 2.4 Secrets

`.env` est gitignoré et **ne doit jamais être commité** — ni dans le dépôt, ni
dans une image Docker. La clé OpenCode Go vit dans
`~/.local/share/opencode/auth.json`. Avant chaque commit, vérifier qu'aucun
token n'apparaît dans le diff.

Sous Docker, les secrets passent par `env_file: .env`, jamais par `COPY`.

### 2.5 Dépendances

**Python** — `backend/pyproject.toml` est la source unique (`requirements.txt`
est un artefact amont, ne pas y ajouter de dépendance). Toute nouvelle
dépendance doit être justifiée, déclarée dans le groupe `dev` si c'est un
outillage, et le lock régénéré : l'image utilise `uv sync --frozen` et échoue
si le lock est désynchronisé.

`pydantic` n'est pas une nouvelle dépendance : il entre par `graphiti-core`, il
est donc déjà dans le lock, et `OntologyToPydantic` l'utilise sans l'ajouter.

**Node** — **pnpm uniquement** (ADR 0008). La version est écrite **une seule
fois**, dans le champ `packageManager` de `package.json`. Installations et
builds en `--frozen-lockfile`. Il ne doit plus rester un seul appel à `npm`
dans le dépôt, et un `package-lock.json` qui réapparaît se **supprime** : c'est
une dérive, pas un conflit à réconcilier.

Dépendance prévue côté produit : `graphiti-core` (Apache-2.0). Aucune autre.

### 2.6 Git

- Branche de travail : **`local-first`**. `origin` = `zohac/MiroFish`,
  `upstream` = `666ghj/MiroFish`.
- **Ne jamais pousser sur `upstream`.**
- Message de commit = *ce qui* + *le pourquoi*. Pas de « fix » nu.
- Jalon important → tag de sauvegarde (ex. `local-first-2026-10-03`).
- L'amont avance vite (~100 commits depuis mars). Pour le réintégrer :
  `git fetch upstream && git rebase upstream/main`, **puis** relancer la
  suite complète — ses correctifs d'ontologie et de Zep ne sont pas chez nous.

### 2.7 Licence

AGPL-3.0. Exécuter une version modifiée en mode réseau avec d'autres
utilisateurs impose de publier les sources. Voir l'ADR 0005.

### 2.8 Aucune feature sans plan

On n'attaque pas une fonctionnalité sans ses artefacts. La valeur est dans
les artefacts : une liste de tâches sans PRD ni architecture ne sert qu'à
mesurer un effort, pas à décider quoi construire.

| Artefact | Emplacement | Répond à |
|---|---|---|
| PRD | `docs/plans/<NNN>-<slug>/prd.md` | quoi, pourquoi, **critères de sortie chiffrés** |
| Architecture | `docs/plans/<NNN>-<slug>/architecture.md` | comment, avec schémas Mermaid |
| Epic | `docs/plans/<NNN>-<slug>/epic-<NNN>.md` | le contrat d'ingénierie : FR, NFR, UX, index des stories, **documents à consulter** |
| Story | `docs/plans/<NNN>-<slug>/story-<epic>-<n>[-<suffixe>].md` | une story = un fichier markdown : en-tête minimal, puis les six sections en français (voir §2.10) |
| Suivi | `docs/sprint-status.yaml` | **l'agrégat par epic** |

Règles :

- Un PRD sans critère chiffré est une liste de courses : on ne sait pas quand
  c'est fini.
- **Une story = un fichier markdown** (ADR 0007, forme précisée par l'ADR
  0009). Un petit en-tête `---` machine-readable (`id`, `epic`, `titre`,
  `statut`, `auteur`, `format`), puis de la prose : c'est une note, pas une
  donnée. L'état d'une story vit dans son fichier ; `sprint-status.yaml` ne
  porte que l'agrégat d'epic. Deux endroits pour le même état, et l'état ment.
- L'`id` suit `<epic>-<n>`, avec un **suffixe alphabétique facultatif** pour une
  story dérivée — celle qui naît d'un critère qu'une story précédente n'a pas
  pu tenir (`001-1b` est le geste que la 001-1 n'appliquait pas). Le suffixe se
  valide : `validate_plans.py` refuse un `id` mal formé.
- `format: "2"` dans l'en-tête, et les six sections en français. Le marqueur
  rend la rupture diagnosticable : un fichier au format 1 est refusé avec un
  message qui nomme le format attendu, au lieu de sept « section absente »
  identiques (ADR 0011).
- Une story passe `backlog → in-progress → review → done`, jamais de saut.
  `blocked` quand une dépendance externe nous arrête. **Ne pas passer
  directement à `done`** : un `done` sans passer par `review` n'a pas été
  relu. *Cette règle n'est outillée par rien* : `validate_plans.py` lit des
  fichiers, pas un historique, et ne contrôle que l'appartenance de l'état à la
  liste des cinq autorisés.
- **Un fichier par story réellement démarrée**, pas imaginée — sinon la
  formalisation devient du bruit. Une story en `backlog` peut n'exister que
  dans l'index de `epic-<NNN>.md`, avec ses critères résumés.
- **Définition de prêt** satisfaite avant de commencer : critères
  mesurables, dépendances résolues, stratégie de test identifiée, documents
  lus.
- **Définition de fini** cochée avant de finir, et **notes de complétion**
  écrites : ce qui a divergé du plan, et pourquoi. Un critère **non satisfiable**
  se barre et se date, il ne se supprime pas : le voir échouer est l'intérêt.
- La structure est **validée par un script**
  (`backend/scripts/validate_plans.py`, PyYAML dans le groupe `dev`) lancé en
  CI. Voici ce qu'il impose, et rien de plus :
  1. un epic `in-progress` ou au-delà a un dossier de plan complet
     (`prd.md`, `architecture.md`, `epic-<NNN>.md`) ;
  2. une story `in-progress` ou au-delà a un fichier **et** est citée dans le
     hub — citation cherchée par frontières de mot, pas par sous-chaîne, sinon
     `001-1b` tiendrait lieu de `001-1` ; et une ligne de hub passée
     `in-progress` a un fichier derrière ;
  3. états et `id` sont valides, `format` est bon, les six sections obligatoires
     sont présentes, et une story en `review` ou `done` n'a plus aucune case
     ouverte — ni dans `Tâches`, ni dans les deux définitions ;
  4. une story `done` dont les notes de complétion sont encore au gabarit est
     refusée.
- `docs/STATUS.md` est la vue humaine, alimentée du YAML. Pas de second
  saisie.

### 2.9 Docker d'abord — environnement de référence opérationnel

**Docker est l'environnement de référence actif** (ADR 0006, Epic 005 clos). Un seul
environnement reproductible, pas deux qui divergent.

> ✅ **L'epic 005 est intégralement réalisé.** Le fichier `docker-compose.yml`
> unifie désormais les 3 services construits localement :
> - `neo4j` : instance Neo4j 5.26.31 Community avec APOC débridé, volume nommé persistant `neo4j_data` et healthcheck Bolt.
> - `backend` : service Flask API, Graphiti, SentenceTransformerEmbedder et moteurs de simulation OASIS (Python 3.11-slim, `uv sync --locked`).
> - `frontend` : service Vue 3 + Vite avec target proxy dynamique vers `http://backend:5001`.
>
> ```bash
> # Cycle standard de l'application
> docker compose up -d                      # démarre les 3 services avec healthchecks
> docker compose ps                         # état + healthchecks
> docker compose logs -f backend            # logs backend
> docker compose down                       # arrête les conteneurs en conservant les volumes
> ```
>
> Le mot de passe vient de `.env` (`NEO4J_PASSWORD`), **jamais** du compose ni des images.
> `down -v` détruit le volume du graphe — ne le lancer que sciemment.

Règles d'or de l'environnement de référence :

- Toute commande d'exécution et de validation passe préférentiellement par `docker compose`.
- Le mode sans Docker reste un **secours de développement local explicite**. On ne mélange pas les
  deux dans une même session.
- Le code est **monté en volume** en développement ; l'image reste la
  référence des dépendances.
- Les données persistantes vivent dans des **volumes nommés** (Neo4j), jamais
  dans le cycle de vie d'un conteneur.
- `docker compose down` **sans** `-v` conserve les données. `down -v` détruit
  le graphe : ne le lancer que sciemment.
- Aucune modification manuelle d'un conteneur ou d'une image. Tout passe par
  les fichiers du dépôt.
- Les ports sont exposés **explicitement** dans le compose. Sur cette machine,
  3000 et 3001 sont déjà pris par les conteneurs d'un autre projet.

### 2.9.1 Lancer MiroFish avec la passerelle Codex locale (modèles avancés)

Pour utiliser un modèle de frontière via Codex (ex. `gpt-6.1-sol`) dans MiroFish :

1. **Configuration `.env`** (à la racine) :
   ```env
   LLM_API_KEY=codex-local
   # Pour exécution dans la stack Docker de référence (recommandé) :
   LLM_BASE_URL=http://host.docker.internal:18080/v1
   # Pour exécution locale directe sur l'hôte (scripts CLI / tests réels) :
   # LLM_BASE_URL=http://127.0.0.1:18080/v1
   LLM_MODEL_NAME=gpt-6.1-sol
   LLM_REASONING_EFFORT=low
   ```
2. **Démarrage de la passerelle Codex locale** (sur la machine hôte) :
   ```bash
   uvx openai-api-server-via-codex \
     -drop-params "temperature,top_p,presence_penalty,frequency_penalty,response_format" \
     -port 18080 \
     -verbose
   ```
   *Note : Le flag `-drop-params` est requis pour filtrer les paramètres non supportés par l'API backend Codex amont (rejet HTTP 400).*

3. **Vérification de santé** :
   ```bash
   # Lister les modèles disponibles
   curl -s http://127.0.0.1:18080/v1/models
   # Test d'inférence direct
   curl -s http://127.0.0.1:18080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "gpt-6.1-sol", "messages": [{"role": "user", "content": "PONG"}]}'
   ```

4. **Exécution de MiroFish** :
   - **Mode Docker de référence** (recommandé) :
     ```bash
     docker compose up -d
     ```
     Interface Web accessible sur `http://localhost:3000`.
   - **Mode Hôte** (scripts locaux, bancs réels) :
     Veiller à ce que `LLM_BASE_URL` pointe sur `http://127.0.0.1:18080/v1`.

### 2.9.2 Lancer MiroFish avec la passerelle Antigravity locale (Gemini & Claude)

Une passerelle autonome Python (`backend/scripts/antigravity_proxy.py`) permet
d'utiliser les modèles de l'IDE Antigravity (`gemini-3.8-flash`, `claude-opus-5.5`,
`claude-sonnet-5.5`, `gpt-oss-120b`, etc.) au format compatible OpenAI via les
quotas de l'IDE sans clé payante :

1. **Démarrage de la passerelle Antigravity locale** (sur la machine hôte) :
   ```bash
   python backend/scripts/antigravity_proxy.py --host 0.0.0.0 --port 18081
   ```
   *Note : Le script extrait automatiquement la session OAuth active depuis la base SQLite locale de l'IDE Antigravity (`~/Library/Application Support/Antigravity IDE/User/globalStorage/state.vscdb`) et assure le renouvellement transparent du jeton d'accès sans aucune intervention manuelle.*

2. **Configuration `.env`** (à la racine) :
   ```env
   LLM_API_KEY=antigravity-local
   # Dans la stack Docker :
   LLM_BASE_URL=http://host.docker.internal:18081/v1
   # Hors Docker (scripts hôte) :
   # LLM_BASE_URL=http://127.0.0.1:18081/v1
   LLM_MODEL_NAME=gemini-3.8-flash
   LLM_REASONING_EFFORT=high
   ```

   *Modèles de l'IDE disponibles* :
   - `gemini-3.8-flash` (défaut, reasoning High)
   - `claude-opus-5.5` (reasoning Medium)
   - `claude-sonnet-5.5` (reasoning Medium)
   - `gpt-oss-120b` (reasoning Medium)
   - *(rétrocompatibilité : `gemini-3-pro`, `gemini-2.5-pro`, `claude-sonnet-4.6`, etc.)*

3. **Vérification de santé** :
   ```bash
   curl -s http://127.0.0.1:18081/health
   curl -s http://127.0.0.1:18081/v1/models
   curl -s http://127.0.0.1:18081/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "gemini-3.8-flash", "messages": [{"role": "user", "content": "PONG"}]}'
   ```

### 2.10 Langue

**Français, partout, sans exception.** Cette constitution, les ADR, les PRD,
les epics, les stories, le `STATUS.md`, les messages de commit, les
commentaires de pull request, et les échanges avec l'utilisateur comme entre
agents.

Restent en anglais, et uniquement là :

- le code et les identifiants — `chunk_size`, `GraphStore`, `zep_entity_reader` ;
- les valeurs de statut et les clés d'en-tête des stories — `backlog`,
  `in-progress`, `review`, `done`, `blocked`, `definition_of_ready` : ce sont
  des identifiants lus par `validate_plans.py` ;
- un terme technique établi où la traduction serait moins claire — `pipeline`,
  `commit`, `endpoint`, `healthcheck`.

Les six sections d'une story sont donc en français : **Définition de prêt**,
**Définition de fini**, **Tâches**, **Notes de développement**, **Revue**,
**Notes de complétion**. L'illustration donnée dans l'ADR 0009 montre les
noms anglais d'origine : cet ADR est immuable, on ne l'a pas retouché, et son
illustration est **caduque** sur ce point. L'ADR 0011 explique pourquoi le
validateur exige désormais les titres français. **Ne pas la recopier.**

> Cette règle est outillée par `validate_plans.py`, qui refuse un fichier sans
> `format: "2"` ou dont les sections portent les titres anglais (ADR 0011). Elle
> reste une règle de constitution sur *le reste* des documents : un PRD, une
> architecture ou un ADR écrits en anglais ne sont détectés par rien. Un
> document en anglais n'est pas détecté, il est en faute.

---

## 3. Commandes

### Environnement de référence — Docker (ADR 0006, Epic 005)

```bash
docker compose up -d                                         # backend :5001, frontend :3000, Neo4j :7687/:7474
docker compose ps                                            # état + healthchecks
docker compose logs -f backend                               # logs en direct
docker compose run --rm backend uv run pytest tests/ -q      # suite complète dans le conteneur
docker compose run --rm backend uv run ruff check .          # linting dans le conteneur
docker compose run --rm backend uv run python scripts/verifier_qualification_docker.py # qualification complète
docker compose down                                          # arrêt en conservant les volumes
```

### Mode secours local (sans Docker)

```bash
# Bootstrap local hôte
cd backend && uv sync && cd ..
pnpm install --frozen-lockfile && pnpm --dir frontend install --frozen-lockfile

# Avant chaque commit
cd backend && uv run pytest tests/ -q                  # suite complète
cd backend && uv run ruff check .                     # lint
cd backend && uv run python scripts/validate_plans.py # structure de plan

# Application
pnpm dev                                              # backend :5001, frontend :3000
pnpm build                                            # build frontend
```

Ports : backend `5001` · frontend `3000` (3001, 3002 si occupés) · Neo4j
`7474` (browser) et `7687` (Bolt) — ce dernier **est déjà exposé** par
`docker-compose.neo4j.yml`, donc utilisable avant l'epic 005.

Variables d'environnement utiles :

| Variable | Rôle |
|---|---|
| `FLASK_PORT` | port backend (défaut 5001) |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_NAME` | endpoint LLM |
| `LLM_REASONING_EFFORT` | effort de raisonnement (OpenCode Go) |
| `ZEP_API_KEY` | requis uniquement si le backend graphe = Zep |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | cible Graphiti |

---

## 4. Carte du dépôt

| Zone | Chemin | Rôle |
|---|---|---|
| Routes HTTP | `backend/app/api/` | `graph.py`, `simulation.py`, `report.py` |
| Métier | `backend/app/services/` | construction graphe, personas, simulation, rapport |
| Clients & helpers | `backend/app/utils/` | `zep.py`, `zep_paging.py`, `llm_client.py`, `llm_compat.py`, `graphiti_llm_client.py`, `graphiti_embedder.py`, `ontology.py`, `locale.py` |
| Store de graphe | `backend/app/utils/graph_store/` | interface `GraphStore`, `GraphitiGraphStore`, `ZepGraphStore`, factory `get_graph_store` |
| Modèles | `backend/app/models/` | `project.py`, `task.py` |
| Config | `backend/app/config.py` + `.env` | variables d'env |
| Tests | `backend/tests/` | pytest — 2067 tests collectés au 21 octobre 2026 (Epic 013 clos, 7/7 stories `done`) |
| Simulations | `backend/scripts/` | `run_{parallel,twitter,reddit}_simulation.py` |
| Outillage | `backend/scripts/validate_plans.py` | validation de la structure de planification |
| Banc de benchmark A/B (Epic 013) | `backend/scripts/verifier_benchmark_epic_013.py` | orchestrateur de campagne : pré-contrôle de l'empreinte figée, garde-fou de cohérence du graphe, variantes, écriture du JSON, du rapport formel et du matériel de revue aveugle |
| Grille de score du banc | `backend/app/utils/report_benchmark_score.py` | grille fermée et purement mécanique (versionnée) — aucun champ interprétatif, aucun classement |
| Frontend | `frontend/` | Vue + Vite, proxy `/api` vers 5001 |
| IHM de rapport (Epic 013) | `frontend/src/components/ReportHistorySelector.vue`, `ReportRegenerateDialog.vue`, `ReportComparisonPanel.vue` | sélecteur de versions, régénération par profil, comparaison factuelle (Step 4) |
| Fonctions pures de comparaison | `frontend/src/utils/reportComparison.js` | comparabilité, diff par section, honnêteté de l'usage — testable hors navigateur |
| Locks | `pnpm-lock.yaml`, `frontend/pnpm-lock.yaml`, `backend/uv.lock` | versions figées — ne jamais en réécrire un à la main |
| Planification | `docs/plans/`, `docs/sprint-status.yaml` | PRD, architecture, epic, stories, suivi |
| Données d'entrée | `backend/uploads/documents/` | rapport AN n° 2506 — **gitignoré** |
| Épreuve du graphe | `docker-compose.neo4j.yml` | Neo4j seul, séparé — `5.26.31-community`, volumes nommés |
| Vérification du driver | `backend/scripts/verifier_driver_neo4j.py` | test comportemental de l'override (001-2), 17 contrôles |
| Vérification du LLM | `backend/scripts/verifier_llm_graphiti.py` | test de session & structured output Graphiti (001-3) |
| Vérification de l'embedder | `backend/scripts/verifier_embedder_graphiti.py` | test d'encodage local & intégration Graphiti (001-4) |
| Validation intégration | `backend/scripts/verifier_integration_graphiti.py` | test d'intégration réelle Graphiti + Neo4j local (003-5), critères C1-C6 |
| Vérification ingestion | `backend/scripts/verifier_ingestion_graphiti.py` | test d'ingestion et construction de graphe local (004-3), critère C3 |
| Vérification ontologie | `backend/scripts/verifier_ontology_persistence.py` | test de persistance effective des labels d'ontologie (007-1), critère C1 — sortie [`mesure-007-1.txt`](docs/plans/007-ontologie-dynamique/mesure-007-1.txt) |
| Qualification Epic 007 | *(à créer en 007-7)* | banc de qualification C1–C8 de l'ontologie dynamique |
| Vérification personas | `backend/scripts/verifier_personas_simulation_graphiti.py` | test d'extraction d'entités, personas et simulation (004-4), critère C4 |
| Qualification globale | `backend/scripts/verifier_qualification_local_first.py` | test de qualification globale local-first et clôture Epic 004 (004-5), critères C1-C5 |
| Persistance Neo4j Docker | `backend/scripts/verifier_persistance_neo4j_docker.py` | test de persistance et cycle de vie des volumes (005-4), critère C3 |
| Qualification Docker | `backend/scripts/verifier_qualification_docker.py` | banc d'orchestration de qualification Docker et clôture Epic 005 (005-5), critères C1-C5 |
| Audit Zep Cloud | `backend/scripts/auditer_graphes_zep.py` | sonde d'inventaire et d'arbitrage de compte Zep (006-1), critère C1 |
| Migration Zep -> Graphiti | `backend/scripts/migrer_zep_vers_graphiti.py` | pipeline ETL direct Zep vers Neo4j (006-2), critères C2, C3, C4 |
| Purge Zep Cloud | `backend/scripts/purger_graphes_zep.py` | outil autonome de purge distante sécurisée (006-3), critère FR-6 |
| Qualification Epic 009 | `backend/scripts/verifier_qualification_epic_009.py` | banc de qualification globale éligibilité acteurs et provenance (009-4), critères C1-C7, VERDICT GO |
| Protocole de la 001-2 | `docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh` | les deux modes (compose / sans-apoc) — **la seule chose rejouable** |
| Sorties de mesure | `…/mesure-001-2-compose.txt`, `…/mesure-001-2-sans-apoc.txt` | la preuve versionnée, avec les deux versions |
| Garde-fous de la 001-2 | `backend/tests/test_neo4j_serveur_epreuve.py`, `…/test_verifier_protocol.py` | 43 tests — serveur déclaré, protocole, sorties |
| Docker | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | stack unifiée 3 services (neo4j, backend, frontend), images spécialisées locales |

---

## 5. Le graphe : rayon d'impact

Le graphe de connaissances est le point le plus couplé du code. **Dix
fichiers utilisent réellement le client Zep** — le noyau :

```
backend/app/api/graph.py
backend/app/services/graph_builder.py            # extraction depuis les documents
backend/app/services/ontology_generator.py       # ontologie générée à l'exécution
backend/app/services/oasis_profile_generator.py  # enrichment des personas
backend/app/services/zep_entity_reader.py        # lecture → config de simulation
backend/app/services/zep_graph_memory_updater.py # écriture pendant les tours
backend/app/services/zep_tools.py                # outils du ReportAgent
backend/app/utils/zep.py                         # client + retry
backend/app/utils/zep_paging.py                  # pagination
backend/scripts/validate_zep_cloud_integration.py
```

**Tout nouveau code qui touche au graphe passe par l'interface du store
(ADR 0001), jamais par le client Zep directement.** C'est cette discipline qui
permettra de basculer `ZEP_BACKEND` sans réécrire les services.

---

## 6. Pièges connus

| Piège | Symptôme | Réflexe |
|---|---|---|
| **Commandes Docker lancées trop tôt** | le conteneur tourne le code amont, ou `no such service: backend` | epic 005 (§2.9) : travailler en local d'ici là |
| Python système hors plage (`>=3.11,<3.13`) | `uv` refuse de synchroniser | utiliser `backend/.venv`, ou Docker (3.11) |
| `uv sync --frozen` échoue au build | lock désynchronisé | `uv lock` puis `uv sync`, **avant** de construire l'image |
| **Dérive Docker / local** | les tests passent en local, pas dans le conteneur | un seul environnement de référence |
| **npm et pnpm mélangés** | un `package-lock.json` réapparaît, `node_modules` divergent | pnpm uniquement ; le lock npm se supprime (ADR 0008) |
| `pnpm install` sans `--frozen-lockfile` | le lock est réécrit sans bruit | `--frozen-lockfile` par défaut, partout |
| `docker compose down -v` | le graphe Neo4j disparaît | ne l'utiliser que pour repartir de zéro, sciemment |
| Ports 3000/3001 occupés | le frontend démarre sur 3002 | exposer des ports explicites dans le compose |
| `CMD pnpm run dev` | image en mode dev, pas de build front | à corriger pour une image de production |
| `.env` copié dans l'image | secret dans l'historique Docker | `env_file`, jamais `COPY` |
| OpenCode Go exige un identifiant de session | HTTP 400 `MissingSessionID` | en-têtes via `utils/llm_compat.py` — **Graphiti n'est pas couvert** |
| Structured output non honoré | échec d'extraction | `response_format={"type": "json_object"}` côté MiroFish (`llm_client.py:183`), mode `json_object` explicite côté Graphiti |
| `camel-oasis` vs `graphiti-core` | `neo4j==5.23.0` (pin exact) vs `neo4j>=5.26.0` (plancher) — **conflit structurel, vérifié** | story 001-1 : aucune combinaison publiée ne résout. Parade mesurée et rejouable : `override-dependencies`. **Un second conflit identique** (`sentence-transformers==3.0.0` vs `>=3.2.1`) bloque la story 001-4 |
| **Une ontologie vide n'est plus un no-op** | `set_ontology(gid, {"entity_types": [], "edge_types": []})` lève `OntologyValidationError` depuis l'ADR 0014 ; avant, c'était un appel silencieux | poser une ontologie **réellement** typée ; `verifier_provenance_documents.py` a été corrigé pour ça |
| **Un nom de type d'ontologie devient un label Cypher** | `Media Organization` ou un nom commençant par un chiffre produirait une erreur de syntaxe **en aval**, loin de sa cause | `OntologyToPydantic` refuse ; le même validateur sert les deux stores |

---

## 7. Définition de « fini »

- [ ] Tests verts sous Docker, environnement de référence depuis l'epic 005
- [ ] `ruff check` → rien
- [ ] `validate_plans.py` → rien à signaler
- [ ] Aucun secret dans le diff ni dans l'image
- [ ] Artefacts de plan à jour (PRD, architecture, epic, story, `sprint-status.yaml`)
- [ ] Doc mise à jour si le comportement a changé
- [ ] ADR écrit si une décision d'architecture a été prise
- [ ] Message de commit qui explique le **pourquoi**
- [ ] `AGENTS.md` touché si le cadre lui-même a changé

---

## 8. Hors périmètre (pour l'instant)

- Ré-auditer les forks communautaires → fait, ADR 0002
- Ontology dynamique → **en cours**, epic 007 ; stories 007-1, 007-2 et 007-3 `done` (ADR 0016/0017), 1459 tests verts
- Moderniser le frontend ou l'i18n
- Exposer l'application en réseau sans lire l'ADR 0005
- GitHub Projects : uniquement comme vue générée, et seulement quand
  plusieurs epics seront en cours

---

## 9. Index des documents

| Doc | Contenu |
|---|---|
| [`docs/STATUS.md`](docs/STATUS.md) | fait / en cours / à faire / prochain pas |
| [`sprint-status.yaml`](docs/sprint-status.yaml) | agrégat machine-readable par epic |
| [`docs/plans/001-epreuve-graphiti-local/`](docs/plans/001-epreuve-graphiti-local/epic-001.md) | épreuve close : PRD, architecture, epic, stories |
| [`docs/plans/006-migration-donnees-zep/`](docs/plans/006-migration-donnees-zep/epic-006.md) | migration en cours : 006-1 et 006-2 terminées, 006-3 démarrée |
| [`docs/plans/009-eligibilite-acteurs-et-sources/`](docs/plans/009-eligibilite-acteurs-et-sources/epic-009.md) | verrou d'acteurs en cours : story 009-1 en `review`, mesure C2 réelle consignée |
| [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md) | installation, rôle de Zep, couplage, obstacles, plan, audit des forks |
| [`docs/README.md`](docs/README.md) | conventions et index de la documentation |
| [`deferred-work.md`](docs/deferred-work.md) | travail réel différé, avec ce qui le déclencherait |
| [`docs/architecture/cible-graphstore.md`](docs/architecture/cible-graphstore.md) | schémas de l'architecture cible |
| [`docs/decisions/`](docs/decisions/) | ADR — décisions d'architecture, figées |

### Décisions figées

| ADR | Décision |
|---|---|
| 0001 | Remplacer Zep par Graphiti + Neo4j, derrière une interface à deux implémentations |
| 0002 | Ne pas adopter de fork communautaire : prendre la forme, pas le code |
| 0003 | L'ontologie dynamique est une **v2** ; le chemin de lecture d'abord |
| 0004 | LLM : endpoint gratuit OpenCode Go, avec compat session |
| 0005 | Licence : rester local ; si exposition réseau, publier les sources |
| 0006 | **Docker d'abord** : un seul environnement de référence |
| 0007 | **Une story = un fichier**, l'état vit avec la story |
| 0008 | **pnpm** pour Node : version figée dans `packageManager`, lock strict |
| 0009 | **Fichiers de story en markdown**, pas en YAML |
| 0010 | Forcer `neo4j` par `override-dependencies` : un seul environnement, on contourne le pin de l'amont |
| 0011 | Relevé réel de la surface `neo4j` (pas de `neo4j.Version`), version résolue consignée, marqueur de format de story |
| 0012 | Contrat de provenance commun aux deux stores : métadonnées alignées, annotation `:Episodic` vérifiée, lecture neutre `get_edge_provenance` |
| 0013 | Sémantique des sources : statut de validation, conflits conservés avec règle déclarée, budget de contexte explicite |
| 0014 | Pose effective de l'ontologie : `set_ontology` cesse d'être un no-op, `strict` et `ontology` sont keyword-only, le contrat `GraphStore` est versionné `version = 2` |
| 0015 | Contrôle ontologique avant persistance : preuve Graphiti, NO-GO commun tant que C2 Zep n’est pas démontré |
| 0016 | Périmètre de validation d'ontologie Graphiti : C2 recentré sur Graphiti, refus strict de garantie distante Zep |
| 0017 | Politique ontologique durable et rétrogradation transactionnelle Graphiti |

---

## 10. Ce qui est déjà réglé — ne pas re-dériver

Ces faits ont été vérifiés et coûtent du temps à retrouver. Les redériver, c'est
du gaspillage ; les refaire sans leurs conditions, c'est reproduire leurs bugs.

| Fait vérifié | Où c'est écrit |
|---|---|
| Zep Community Edition est déprécié ; Graphiti est la voie OSS | ADR 0001 |
| Aucun fork communautaire n'est adoptable : bugs silencieux, zéro test, gelés depuis mars | ADR 0002, `LOCAL-FIRST.md` §12 |
| L'ontologie custom est une v2, **pas** le premier chantier | ADR 0003, désormais **en cours** : epic 007, la pose effective est faite (story 007-1, `done` ; story 007-2 `done` (C2 Graphiti qualifié, ADR 0016/0017), story 007-3 `done` (sonde C3 et revue BMAD)) |
| `zep_entity_reader.py:262` filtre les nœuds sans label d'ontologie → **le graphe revient vide en silence** | ADR 0003 |
| L'endpoint gratuit exige un en-tête de session, et **le client de Graphiti n'en envoie pas** | ADR 0004 |
| `chunk_size` compte des **caractères** (500), pas des mots → ~54 mots par chunk | PRD de l'epic 001 |
| Le patch du fork de référence est figé sur `graphiti-core` 0.25 (actuel 0.30) | `LOCAL-FIRST.md` §12.3 |
| **`camel-oasis` et `graphiti-core` ne coexistent pas** : `neo4j==5.23.0` est un pin exact qu'aucune version ne desserre, `graphiti-core` exige un plancher `>=5.26.0` — aucune combinaison publiée ne résout | ADR 0010, ADR 0011, story 001-1 · `LOCAL-FIRST.md` §11.4 |
| **Le driver forcé a été validé à l'exécution** : `neo4j 5.28.6` tient contact avec `Neo4j 5.26.31 community` — écriture, relecture après `stop`/`start` (C3), et toute la surface de l'ADR 0011 exercée, 17/17 contrôles deux fois. **L'ADR 0010 n'est pas supersédé** | ADR 0010, story 001-2 · [`mesure-001-2-compose.txt`](docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt) |
| **`Neo4jError` et `DriverError` sont des branches sœurs** sous `GqlError`, pas une chaîne — mesuré sur 5.28.6. `camel` attrape `ClientError`, ce qui reste juste, mais un `except DriverError` n'attraperait pas `ClientError` | story 001-2 § Notes de complétion |
| **`graphiti-core 0.30.2` n'a besoin d'aucune procédure APOC**, et `camel-oasis` en a besoin : `apoc.meta.data()` dès le `__init__` de `Neo4jGraph`, `apoc.merge.node` à l'écriture. Le plugin reste installé pour `camel`, pas pour Graphiti | story 001-2, `architecture.md` §4 |
| **`CALL db.indexes()` n'existe pas sur un serveur 5.x**, et `graphiti-core` l'appelle dans `delete_all_indexes` — atteint seulement par `build_indices_and_constraints(delete_existing=True)`, donc hors chemin d'écriture | story 001-2, `deferred-work.md` |
| **`apoc.merge.*` est refusé par défaut** même plugin installé ; sans `dbms.security.procedures.unrestricted`, `camel` accuse une installation manquante qui est présente | `docker-compose.neo4j.yml`, story 001-2 |
| Le compose d'épreuve tourne **sans `.env` modifié** : le mot de passe vient de `${NEO4J_PASSWORD}`, interpolé, et pas de `env_file` — qui passerait `LLM_API_KEY` dans un conteneur Neo4j | `docker-compose.neo4j.yml`, `test_neo4j_serveur_epreuve.py` |
| **La mesure de la 001-1 est rejouable, sur les deux arbres** : `mesurer-001-1.sh` normalise `pyproject.toml` dans l'état qu'il veut mesurer, puis restaure `pyproject.toml`, `uv.lock` et le venv à l'octet initial ; il refuse un arbre ambigu (override d'un autre périmètre, `[tool.uv]` portant d'autres clés, geste à moitié posé) au lieu de le deviner. Les **deux sorties sont versionnées** dans [`mesures-001-1b.md`](docs/plans/001-epreuve-graphiti-local/mesures-001-1b.md) | story 001-1, story 001-1b |
| **L'override est posé, et sa version résolue est gardée** : `pyproject.toml` porte `override-dependencies = ["neo4j>=5.26.0,<6.0.0"]` avec `neo4j 5.28.6` en commentaire, et un test échoue si le lock s'en écarte — donc à chaque CI | story 001-1b · ADR 0011 |
| **L'hypothèse de conflit `sentence-transformers` est levée** : `graphiti-core` ne fournit aucun embedder interne et utilise l'interface `EmbedderClient` abstraite ; `sentence-transformers==3.0.0` (fourni par `camel-oasis`) s'exécute localement sans extra ni modification de `pyproject.toml` | story 001-4 |
| **Verdict GO de l'épreuve Graphiti local (Epic 001)** : space-bunny sur OpenCode Go avec SentenceTransformerEmbedder et Neo4j 5.26 extrait 29/30 chunks sans erreur, 0 défaut session, 49 nœuds et 45 relations persistés. Aucun modèle payant requis (coût marginal 0 €) | story 001-5, story 001-6, `rapport.md`, `STATUS.md` |
| **`apoc.merge.*` refusé alors que le plugin est installé** | `camel` dit « plugin absent », le message est faux : il faut `NEO4J_dbms_security_procedures_unrestricted: "apoc.*"` dans le compose |
| `CALL db.indexes()` échoue en `ProcedureNotFound` | `graphiti-core` l'appelle dans `delete_all_indexes` ; la commande a disparu en 5.x. Utiliser `SHOW INDEXES YIELD name DROP INDEX name` |
| `cypher-shell` dans un healthcheck : le `$$` de Compose | `$$` pour le shell du conteneur, `$` pour Compose ; un seul `$` est consommé par l'interpolation |
| Un nom d'index avec un tiret | `mirofish-verification_fulltext` est une faute de syntaxe Cypher : les identifiants ne prennent que lettres, chiffres et `_` |
| Le `docker-compose.yml` pointe l'image amont, pas la nôtre | ADR 0006 |
| Les tests passent sans `.env` — ils sont hermétiques | `LOCAL-FIRST.md` §2 |
| **Un label d'ontologie persiste, mesuré sur deux domaines** : `add_episode(..., entity_types=...)` fait porter aux nœuds le nom de la classe ; 100 % des nœuds du fixture télécom et du fixture énergie portent un label custom, invariant « au plus un label non-`Entity` » tenu | story 007-1 · [`mesure-007-1.txt`](docs/plans/007-ontologie-dynamique/mesure-007-1.txt) · ADR 0014 |
| **Le nom de la classe Pydantic, pas son index, devient le label Cypher** : `Graphiti.add_episode` attend un **dictionnaire** `entity_types`, et `_build_entity_types_context` insère un type générique `Entity` en identifiant **0** — les types déclarés commencent à **1**. Un `entity_type_id = 0` produit donc un nœud `:Entity`, par construction | story 007-1 · `graphiti_core/utils/maintenance/node_operations.py:156` |
| **Neo4j Community refuse toute propriété-map, même vide** : `SET n.attributes = {}` échoue en `Property values can only be of primitive types or arrays thereof`. Graphiti écrit chaque attribut d'ontologie comme une **propriété scalaire** à plat (`entity_data.update(node.attributes)`) — donc un attribut nommé comme une clé de `attributes` casserait l'écriture | mesuré sur `neo4j:5.26.31-community` · story 007-1 |
| **Un LLM peut renvoyer le fragment de schéma JSON d'un champ au lieu de sa valeur**, et ce fragment est un dictionnaire qui traverse la validation Pydantic (qui ignore l'inconnu) puis devient une propriété. `MiroFishLLMClient._filtrer_champs_valides` l'écarte : sans ce filet, une seule valeur inventée fait échouer tout un épisode | story 007-1 · `tests/test_llm_response_sanitizer.py` |
| **Les noms réservés par le moteur de graphe doivent être refusés dans une ontologie** : un type nommé `Episodic`, `Community`, `Node` ou `Entity` poserait sur chaque nœud un label indistinguable d'un nœud interne, et la relecture ascendrait des entités comme des épisodes | `RESERVED_ONTOLOGY_TYPE_NAMES` · story 007-1 |
| `EntityNode.model_fields` est la source de vérité des noms réservés | `attributes`, `created_at`, `group_id`, `labels`, `name`, `name_embedding`, `summary`, `uuid` — mesuré, et un test échoue si la liste `RESERVED_ONTOLOGY_ATTRIBUTE_NAMES` s'en écarte |
| **L'identifiant d'instantané n'est pas une adresse de contenu** | `snapshot_id = f"snap_{uuid.uuid4().hex[:12]}_{date_suffix}"` — un uuid de *capture*. Deux générations sur les mêmes preuves figées portent **deux identifiants distincts pour la même empreinte SHA-256**. C'est l'empreinte qui prouve l'identité des preuves ; comparer sur l'identifiant rendrait non comparables tous les couples A/B de l'Epic 013 | story 013-2 (`evidence_snapshot_service.py`), story 013-5 § Notes de développement point 10 — mesuré sur deux régénérations réelles (`snap_f0e55dd0b705…` / `snap_a97649816fd4…`, empreinte commune `57127e619a0ebd32…`) |
| **Un `meta.json` de rapport tronqué faisait échouer tout l'historique** | `ReportManager.get_report` propageait l'exception de parsing JSON, et `list_reports` parcourt *tous* les rapports du disque : un seul fichier corrompu faisait répondre 500 à `GET /api/report/simulation/<sim_id>/history` | story 013-5 — `get_report` renvoie désormais `None` avec un avertissement journalisé |
| **Un rapport corrompu inscrit dans l'index restait listé** | `list_reports_by_simulation` faisait `results.append(item)` **hors** du `if rep:` : l'entrée d'index servait, `evidence_snapshot_sha256` périmé compris, alors que `GET /api/report/<id>` répond 404 pour elle. L'IHM proposait une version qui ne s'ouvrait pas, et le verdict de comparabilité pouvait fonder une « comparaison contrôlée » sur un rapport sans contenu | story 013-5, 2e revue BMAD — l'entrée d'index dont le rapport est illisible est **écartée**, et son empreinte retirée |
| **L'égalité de `snapshot_id` impliquait bien l'égalité des preuves — ne pas y toucher** | `snapshot_id` est un uuid **par capture** (`snap_<uuid4[:12]>_<date>`) : deux captures distinctes ne le partagent jamais, donc l'égalité de cet identifiant implique l'égalité de la capture, donc du jeu de preuves. Le verdict « comparable » sur la seule égalité de `snapshot_id` est **correct** ; c'est l'autre sens (deux captures du même jeu) qui exige l'empreinte SHA-256 | story 013-5, 2e revue BMAD — 3 couches de revue sur 4 ont proposé de « corriger » ce point ; la correction aurait été un défaut |
| **Le corps `llm_profile` envoyé par le navigateur pouvait fixer la passerelle et la clé** | `ReportLLMProfile.from_dict()` acceptait `base_url` et `api_key` du client, et `POST /api/report/generate` acceptait ce corps : un client pouvait désigner une passerelle OpenAI-compatible arbitraire et y faire transiter le paquet de preuves entier. Le Fail-Closed tarifaire de la 013-4 était désarmable de la même façon (`billing_mode: "free"`) | story 013-5, 2e revue BMAD — `from_client()` aligne le profil sur le catalogue : destination et clé refusées, facturation non déclassable, plafonds non relevables, `profile_id` dérivé du couple (modèle, effort) |
| **Le graphe n'est PAS dans l'empreinte des preuves** | `replay_frozen` ne gèle que les interactions OASIS live : les outils graphe du `ReportAgent` (`insight_forge`, `panorama_search`, `quick_search`, `get_edge_provenance`) interrogent toujours Neo4j. Deux variantes peuvent donc voir un graphe différent sans que l'empreinte SHA-256 des preuves le révèle. Le banc de benchmark mesure donc l'état du graphe (nœuds et arêtes) avant la première variante et après chacune, et **écarte** toute variante dont l'état diffère. C'est le principal biais résiduel du protocole A/B, et il est déclaré comme tel dans le rapport de qualification | story 013-6 (`backend/scripts/verifier_benchmark_epic_013.py`) — décision d'ingénierie n° 3 |
| **L'empreinte figée de R7 est stable et connue** | `sim_80a54d7bbd7b` → `26cf493ea7bbd579be7162c0eec3ee7074f905f0e5532a3c004cb9c017989f56` : 5 fichiers de preuves scellés, **737 événements**, **41 acteurs**, `has_archived_interviews=False`, stable sur deux captures consécutives. C'est la référence des campagnes A/B de l'Epic 013. Le graphe de R7 (`mirofish_c34a65988c24496b`) mesuré au même instant : 42 nœuds, 163 arêtes | story 013-6, mesuré le 20 octobre 2026 sur la stack Docker de référence |
| **Une génération isolée ne permet pas de conclure sur l'effet de l'effort** | Une seule génération par variante confond l'effet de l'effort de raisonnement et la variabilité stochastique du modèle. Le banc expose `--repetitions` pour mesurer cette variance, mais le rapport de qualification déclare le nombre de répétitions par variante et le déclare comme un biais résiduel tant qu'il reste à 1 | story 013-6, § 7 du rapport de qualification |
| **Le paquet de preuves figé ne contient pas les matériaux du rapport** | `EvidenceSnapshotService.CANONICAL_AUDIT_FILES` (`evidence_snapshot_service.py:49-56`) scelle 6 artefacts : `actors.json`, `interviews_archive.json`, `observed_events.jsonl`, `simulation_brief.json`, `simulation_config.json`, `source_manifest.json`. **Ni `actions.jsonl` (216 actions), ni les fiches persona (`reddit_profiles.json`, `twitter_profiles.csv`), ni le brief seul.** Matériaux utilisés par la rédaction, hors de l'empreinte : c'est le fondement du régime de preuve de l'Epic 014 | story 014-1, mesuré sur R7 |
| **Un `project.json` corrompu casse la provenance de TOUS les rapports** | `ProjectManager.get_project` (`project.py:307-325`) fait `json.load` sans garde ; `list_projects` (`:337-348`) parcourt tout le répertoire ; `find_projects_by_graph_id` (`:352-359`) propage l'exception, que `_resolve_project` avale (`report_agent.py:1414-1424`) → projet résolu `None` → la section affiche « Aucun document source structuré » alors que le projet en a. Mesuré : `backend/uploads/projects/proj_d850cdad31ee/project.json` est tronqué | story 014-2, mesuré sur R7 |
| **L'étiquette `[Événements simulés réels]` n'est produite par aucun code** | C'est une invention du LLM de rédaction, et l'extracteur l'avale comme un **nom d'agent** : le claim devient `agent_name: "Événements"` (`backend/tests/fixtures/qualification_epic_012/r6_bundle/report_claims.json:1046`). Toute étiquette de provenance posée par le LLM dans le texte est donc **non fiable** — seul un typage émis par le code l'est | story 014-1, mesuré |
| **Un rapport R7 complet demande ~1 270 s en effort `medium` et ~4 500 s en effort `high`** | Mesuré le 20 octobre 2026 sur la stack Docker de référence, passerelle Antigravity locale, simulation `sim_80a54d7bbd7b` (5 sections, boucle ReACT). L'effort de raisonnement `high` coûte donc **~3,5 fois** le temps mural de `medium` sur le même jeu de preuves. Le plafond mural par défaut des profils de rapport a été relevé de 900 à **5 400 s** : à 900 s la variante `high` était tronquée en section 2, à 1 800 s en section 3. Le plafond **budgétaire** (2 $) ne mord pas sur une passerelle locale : le coût facturable y est réellement nul, seul le plafond mural s'applique | story 013-6, `ReportLLMProfile.max_wall_seconds` |

---

## 11. Contrat de session

**Au début, dans cet ordre** — c'est ce qu'il faut lire pour reprendre le
travail sans mémoire :

1. ce fichier,
2. [`docs/STATUS.md`](docs/STATUS.md) — où on en est, questions ouvertes,
3. [`docs/plans/001-epreuve-graphiti-local/epic-001.md`](docs/plans/001-epreuve-graphiti-local/epic-001.md) — le contrat de l'epic en cours, et ses 11 documents de référence,
4. le fichier de story de la tâche du moment,
5. l'ADR concerné (§9).

**Environnement** — avant de modifier quoi que ce soit :
`cd backend && uv run pytest tests/ -q` doit afficher 333 passed. Sinon, on
corrige avant de commencer, pas après.

**À la fin** — tests verts, lint vert, structure validée, commit explicatif,
doc et ADR à jour, `sprint-status.yaml` à jour, story passée en `review` (pas
en `done` directement), `AGENTS.md` régénéré si le cadre a bougé, tag si
jalon.

Ne pas laisser dans l'arbre de travail du travail non commité : c'est la
première cause de perte de travail sur ce dépôt.
