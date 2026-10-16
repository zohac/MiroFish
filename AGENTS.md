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
| Preuve par les faits simulés, traçabilité et intégrité (OASIS post-simulation, ToolShield) | ⏳ à venir — Epic 011 |

- Amont : `666ghj/MiroFish` — AGPL-3.0, ~75 000 ★, très actif
- Fork de travail : `zohac/MiroFish`, branche `local-first`
- État du projet : [`docs/STATUS.md`](docs/STATUS.md)
- Contexte technique détaillé : [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md)

### La tâche du moment

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
16 octobre 2026 compte **1649 tests collectés et réussis sur l'hôte (+ 9 tests frontend Node) ; 1646 réussis + 3 ignorés sous
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
**1649** (1618 + 31 tests hermétiques nets, dont fallbacks config/rapport, boucle ReACT fr et banc de qualification 008-3).

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
| Tests | `backend/tests/` | pytest — 1431 tests collectés au 12 octobre 2026 (Epic 009 clos, stories 007-1/007-2 `done`) |
| Simulations | `backend/scripts/` | `run_{parallel,twitter,reddit}_simulation.py` |
| Outillage | `backend/scripts/validate_plans.py` | validation de la structure de planification |
| Frontend | `frontend/` | Vue + Vite, proxy `/api` vers 5001 |
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
