# État du projet

Une page, mise à jour à chaque changement d'epic. La source de vérité est
[`sprint-status.yaml`](sprint-status.yaml) — ce fichier en est la **vue
humaine**, pas une seconde saisie.

> Dernière mise à jour : **16 octobre 2026** · branche `local-first`

---

## Où on en est

L'**Epic 010 (Fiabilisation du cycle de vie et de la complétion des simulations) est intégralement clos avec succès (3/3 stories validées — 1580 tests verts)** :
- **Story 010-1 (done au 15 octobre 2026)** : Arrêt déterministe (`--no-wait`) et statut `COMPLETED` automatique. Injection systématique de `--no-wait` par défaut dans `SimulationRunner._start_simulation` pour les simulations parallèles, Twitter et Reddit, empêchant le verrouillage historique en fin de simulation. Support optionnel du mode interactif persistant `keep_alive_on_completion: bool | None = None` via l'API `POST /api/simulation/start`, `SimulationRunState` et `simulation_config.json`. Supervision active de complétion dans `_monitor_simulation` via `_check_all_platforms_completed(state)` avec préservation stricte du mode interactif (Patch 1 BMAD), délai de grâce (5 s), émission de repli de la commande IPC `send_close_env()` et terminaison de sécurité forcée à 10 s (NFR-3). Bascule déterministe vers `RunnerStatus.COMPLETED` avec horodatage strict ISO 8601 (`completed_at`), écriture atomique dans `run_state.json` et synchronisation sans délai. Barrière de drain mémoire `ZepGraphMemoryManager.stop_updater()` respectée sous verrou de finalisation (AC5). 11 tests unitaires hermétiques dédiés créés dans `backend/tests/test_simulation_runner_completion.py`, filet global porté à **1562 tests passants sur l'hôte** (0 échec).
- **Story 010-2 (done au 15 octobre 2026)** : Réconciliation d'état OS/cache et résilience IHM (`Step3Simulation.vue`). Réconciliation de vivacité dans `SimulationRunner.get_run_state` vérifiant `process.poll()` pour les processus gérés et `os.kill(pid, 0)` / `OpenProcess` (`STILL_ACTIVE`) pour les PID système, avec bascule sous verrou de finalisation vers les statuts terminaux réels (`COMPLETED`, `STOPPED` ou `FAILED`), élimination des statuts orphelins sans PID et fermeture des descripteurs de logs. Invalidation de cache temps réel par comparaison du `mtime` de `run_state.json`. Détection de complétion par les faits côté IHM Vue 3 dans `Step3Simulation.vue` (`factsCompleted` via `progress_percent >= 100` et achèvement des plateformes actives) permettant le déblocage immédiat de la phase 2 et du bouton de génération de rapport, maintien du polling jusqu'à la fin de la barrière mémoire et tolérance aux erreurs 409 transitoires. 9 tests unitaires hermétiques dédiés créés dans `backend/tests/test_simulation_runner_reconciliation.py`. Revue contradictoire BMAD 4 couches validée (4 patches appliqués). Filet global porté à **1571 tests passants sur l'hôte** (0 échec).
- **Story 010-3 (done au 15 octobre 2026)** : Thread-safety SentenceTransformers et drain mémoire résilient. Sécurisation thread-safe de `SentenceTransformerEmbedder._encode_sync` via le verrou `self._lock` sérialisant l'inférence PyTorch et éliminant définitivement les erreurs de meta-tensors (`Cannot copy out of meta tensor; no data!`). Ajout du paramètre `strict: bool = True` dans `ZepGraphMemoryUpdater.stop()` permettant en mode résilient (`strict=False`) de journaliser les échecs de lots d'activités résiduels non critiques sans bloquer la finalisation de la simulation. Sécurisation du dé-enregistrement de l'updater dans `ZepGraphMemoryManager.stop_updater(simulation_id, strict=False)` sous bloc `finally:` et purge garantie de `_pending_episode_uuids`. Bascule nominale de `SimulationRunner._monitor_simulation` vers `RunnerStatus.COMPLETED`. 9 tests unitaires hermétiques dédiés créés dans `backend/tests/test_sentence_transformer_thread_safety.py`. Revue contradictoire BMAD 4 couches validée (2 patches appliqués). Filet global de tests porté à **1580 tests passants sur l'hôte** (0 échec). L'Epic 010 est **clos**.

L'**épreuve Graphiti local (Epic 001)** a été validée avec succès (**Verdict GO**).

L'**interface `GraphStore` (Epic 002) est intégralement close (6 stories terminées et validées)** :
l'abstraction du store de graphe (`GraphStore`) est posée avec ses modèles de données neutres immutables
et sa hiérarchie d'exceptions agnostiques. L'implémentation existante `ZepGraphStore` est encapsulée, la factory
`get_graph_store()` (pilotée par `ZEP_BACKEND`, défaut `'cloud'`) est en place avec support d'override, et
l'intégralité des flux d'ingestion/écriture et d'interrogation/lecture a été migrée sans régression.
Une suite de tests d'isolation permanente (`test_graph_store_isolation.py`) garantit par analyse AST
**0 import direct** du SDK Zep dans les services et routes API, et **0 bifurcation conditionnelle** `if zep else graphiti`
dans le code applicatif. Le filet global atteint **470 tests verts** (100 % passants). L'Epic 002 est **clos**.

L'**Epic 003 (`GraphitiGraphStore` — écriture et chemin de lecture) est intégralement clos avec succès (5/5 stories terminées et validées)** :
- **Story 003-1 (done)** : squelette de `GraphitiGraphStore`, déclaration formelle des 14 méthodes du contrat `GraphStore`, constructeur à injection de dépendances, résolution de variables d'environnement, passerelle synchrone/asynchrone thread-safe `_run_async`, activation de `ZEP_BACKEND='graphiti'` dans la factory `get_graph_store()` et revue contradictoire BMad 4 couches validée (5 patchs appliqués). Suite de 23 tests unitaires hermétiques (`test_graphiti_graph_store.py`). Filet porté à **494 tests verts** (+24).
- **Story 003-2 (done)** : implémentation du cycle de vie (`create_graph`, `delete_graph`, `set_ontology`) et de l'ingestion d'épisodes (`add_episode`, `add_text_batch`, `wait_for_batch`, `wait_for_episodes`) avec partitionnement strict par `group_id = graph_id` (Critère C2, NFR-3). Validation de l'isolation étanche entre graphes, normalisation ISO 8601 UTC ('Z'/'z'), optimisation Cypher indexé `:Episodic` et revue contradictoire BMad 4 couches validée (5 patchs appliqués). 27 nouveaux tests unitaires dans `test_graphiti_graph_store.py` (50 tests sur le fichier). Filet porté à **521 tests verts** (+27).
- **Story 003-3 (done)** : implémentation de la lecture Cypher (`get_all_nodes`, `get_all_edges`), des parcours de voisinage (`get_node`, `get_node_edges`), de l'agrégation API (`get_graph_data`, `get_graph_info`) et de la recherche hybride temporelle (`search` avec scopes `edges`, `nodes`, `hybrid`). Préservation intégrale de la temporalité (C3, NFR-4), résolution des noms de nœuds connectés, partitionnement étanche `group_id` sur toutes les requêtes Cypher et revue contradictoire BMad 4 couches validée (6 patchs appliqués). 24 nouveaux tests unitaires dans `test_graphiti_graph_store.py` (74 tests sur le fichier). Filet porté à **545 tests verts** (+24).
- **Story 003-4 (done)** : adaptation de la lecture d'entités (`zep_entity_reader.py`, `EntityNode`, `GraphNode`) pour supporter le typage agnostique et les entités génériques Graphiti (`:Entity`). Levée du filtrage aveugle qui ignorait 100 % des nœuds Graphiti, chaîne de résolution déterministe de `get_entity_type()` (labels spécifiques > attributs `entity_type`/`type`/`category` > `Entity`), filtrage `filter_defined_entities()` avec ou sans `defined_entity_types`, compatibilité validée avec `simulation_config_generator` et `oasis_profile_generator`, revue BMad validée (3 patchs appliqués). 10 tests unitaires hermétiques dédiés (`test_zep_entity_reader_graphiti.py`). Filet porté à **555 tests verts** (+10).
- **Story 003-5 (done)** : banc d'intégration réelle (`backend/scripts/verifier_integration_graphiti.py`) validé contre le conteneur Neo4j local (`docker-compose.neo4j.yml`). 100 % des 14 méthodes exercées avec succès (C1), partitionnement multi-tenant étanche prouvé sans fuite (C2), métadonnées temporelles préservées (C3), extraction `ZepEntityReader` validée sur le graphe réel (C4), factory opérationnelle sans clé Zep (C5), filet global porté à **562 tests verts** (+7 tests, dont 2 tests unitaires hermétiques issus de la revue BMad). Rapport de validation versionné ([`rapport-validation-integration.md`](plans/003-chemin-de-lecture-graphiti/rapport-validation-integration.md)) avec **VERDICT GO**. L'Epic 003 est **clos**.

L'**Epic 004 (Construire un graphe en local sans clé Zep) est intégralement clos avec succès (5/5 stories terminées et validées — 632 tests verts)** :
- **Story 004-1 (done)** : Paramétrabilité universelle du LLM via `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT`), harmonisation `LLMClient`/`MiroFishLLMClient`, neutralité d'hôte stricte (0 en-tête vers OpenAI/Ollama, `x-opencode-session` uniquement vers `opencode.ai`), suite de tests unitaires dédiée (+15 tests). Filet porté à **577 tests verts**.
- **Story 004-2 (done)** : Levée des gardes `ZEP_API_KEY` dans les routes API et les services métiers. Helper `Config.requires_zep_api_key()` posé, gardes bloquants levés dans `backend/app/api/graph.py` et `backend/app/api/simulation.py` lorsque `ZEP_BACKEND='graphiti'`, non-régression cloud préservée, 24 tests unitaires dédiés (`test_zep_api_key_guards.py`). Filet porté à **601 tests verts**.
- **Story 004-3 (done)** : Ingestion et construction de graphe de bout en bout avec `GraphitiGraphStore` et `GraphBuilderService`. Ingestion asynchrone `/api/graph/build` validée, banc d'épreuve réel Neo4j validé (`scripts/verifier_ingestion_graphiti.py`) avec critère C3 formellement satisfait (6 nœuds ≥ 5, 4 arêtes ≥ 3), 13 tests unitaires et d'intégration dédiés. Filet porté à **614 tests verts**.
- **Story 004-4 (done)** : Extraction d'entités, génération de personas et configuration de simulation sans Zep. Extraction `ZepEntityReader`, génération des profils Reddit JSON et Twitter CSV conformes aux spécifications OASIS par `OasisProfileGenerator`, configuration `simulation_config.json` et banc d'épreuve Neo4j validé (`scripts/verifier_personas_simulation_graphiti.py`), 10 nouveaux tests unitaires dédiés. Filet porté à **624 tests verts**.
- **Story 004-5 (done)** : Banc de qualification globale local-first (`scripts/verifier_qualification_local_first.py`) orchestrant le flux complet sans clé Zep. 100 % des critères de sortie C1 à C5 satisfaits (0 blocage API, LLM universel, graphe Neo4j réel de 6 nœuds et 4 arêtes, 6 personas OASIS Reddit/Twitter avec simulation prête, filet de tests porté à **632 tests verts** (+8 tests, `test_verifier_qualification_protocol.py` et revue BMad 5 patchs)). Rapport de qualification finale consigné ([`rapport-qualification-epic-004.md`](plans/004-bascule-sans-zep/rapport-qualification-epic-004.md)) avec **VERDICT GO**. L'Epic 004 est **clos**.

L'**Epic 005 (Environnement Docker de référence — Docker-first, ADR 0006) est intégralement clos avec succès (5/5 stories terminées et validées — 711 tests verts, VERDICT GO)** :
- **Story 005-1 (done)** : Dockerfiles spécialisés pour le backend (`python:3.11-slim`, `uv sync --locked`) et le frontend (`node:20-slim`, `pnpm install --frozen-lockfile`) construits localement depuis les sources avec `.dockerignore` étanche. 19 tests unitaires hermétiques (`test_docker_build_config.py`). Filet porté à **651 tests verts**.
- **Story 005-2 (done)** : `docker-compose.yml` unifié orchestrant les 3 services (`neo4j:5.26.31-community` avec volume nommé persistant `neo4j_data` et healthcheck Bolt, `backend` Flask sur `bolt://neo4j:7687` avec healthcheck HTTP, `frontend` Vue 3 avec proxy dynamique `BACKEND_URL`) sur réseau bridge `mirofish_network` avec ordonnancement strict. 13 tests unitaires hermétiques (`test_docker_compose_config.py`). Filet porté à **664 tests verts**.
- **Story 005-3 (done)** : Validation de l'exécution intégrale du filet de tests (671 tests) et de l'outillage (`ruff check .`, `validate_plans.py`) dans le conteneur `backend` de référence. Adaptation sans `.git`, 7 tests unitaires hermétiques (`test_docker_tooling_parity.py`). Filet porté à **671 tests verts**.
- **Story 005-4 (done)** : Sonde autonome de persistance des données Neo4j (`scripts/verifier_persistance_neo4j_docker.py`). Preuve formelle de conformité au Critère C3 : 100 % des nœuds et arêtes préservés au SHA-256 près après `docker compose down && up -d` (sans `-v`), purge propre sur `down -v`, préservation des volumes bind (`uploads`, `simulations`). 12 tests unitaires hermétiques (`test_docker_volume_persistence.py`). Filet porté à **684 tests verts**.
- **Story 005-5 (done)** : Sonde d'orchestration de qualification Docker (`scripts/verifier_qualification_docker.py`) validant l'ensemble des 5 critères C1 à C5 du PRD. Démarrage unifié mesuré en 6.2s ($\le 60$s, C1), filet de tests au vert (C2), persistance validée (C3), pipeline complet e2e local-first exécuté avec code retour 0 dans le conteneur `backend` (C4), 0 secret dans les calques Docker (`docker history`) et CI 100 % conforme (C5). 26 tests unitaires hermétiques (`test_verifier_qualification_docker.py`). Rapport de qualification final ([`rapport-qualification-epic-005.md`](plans/005-docker-local/rapport-qualification-epic-005.md)) avec **VERDICT GO**. Filet porté à **711 tests verts**. L'Epic 005 est **clos**.

L'**Epic 009 (Éligibilité des acteurs et fiabilisation des sources) est intégralement clos avec succès (4/4 stories terminées et validées — 1157 tests verts, VERDICT GO)** :
- **Story 009-1 (done)** : Modèle `ActorEligibility`, classifieur agnostique à deux passes (`ActorClassifierService`), barrière stricte interdisant l'activation de profils non-acteurs (produits, prix, concepts, dates), preuve de qualification et mesure réelle C2 (0 faux positif sur 21 entités, spatial & télécom). Filet porté à 924 tests verts.
- **Story 009-2 (done)** : [ADR 0012](decisions/0012-contrat-de-provenance-graphstore.md) (contrat de provenance commun `GraphStore`) et [ADR 0013](decisions/0013-semantique-des-sources.md) (statut de validation, conflits, budget de contexte). Modèles `source_document.py` et `simulation_brief.py`, extension des deux stores, découpage par document avec positions exactes `[char_start, char_end]`, diagnostic de long contexte (> 50 000 chars) et mesure réelle C3. Filet porté à 1112 tests verts.
- **Story 009-3 (done)** : Modèle `ActorSelection` et persistance atomique `actors.json` rattachée à la simulation avec empreinte SHA-256 déterministe et journal d'audit. Endpoints Flask `POST /api/simulation/actors/preview` et `review` (409 sur désynchronisation optimiste, rejet des non-acteurs, motif obligatoire). Intégration dans `prepare_simulation` et IHM Vue 3 (`Step2EnvSetup.vue`) avec panneau de prévalidation et blocage volontaire. Filet porté à 1130 tests verts.
- **Story 009-4 (done, revue BMAD du 12 oct. 2026)** : Outils de provenance dans `ZepToolsService` (transport complet des épisodes, `ProvenanceRecord`, `origin` et `origins`), modèle `InformationOrigin` (5 origines d'information étanches), service `SimulationActionVerifier` appliquant la règle d'or anti-affabulation C7 (requalification des intentions non actées, validation déterministe d'événements `compute_event_id`, contrôle verbatim des citations textuelles, formatage des contradictions `SourceConflict`). Intégration `ReportAgent` avec section normalisée « Sources & Provenance » et étanchéité NFR-5. Banc autonome `verifier_qualification_epic_009.py` validant l'intégralité des critères C1 à C7 avec le rapport formel [`rapport-qualification-epic-009.md`](plans/009-eligibilite-acteurs-et-sources/rapport-qualification-epic-009.md) et **VERDICT GO**. Filet global porté à **1157 tests verts** (0 échec). Revue BMAD code-review menée le 12 octobre 2026 : story rétrogradée en `review` (violation `backlog → done`), 10 patches de moyen et haut impact appliqués (AC6 via chargement du document source, NFR-5 dans les prompts LLM, C5 sous Docker, batch `get_edges_provenance`, `get_edge_by_uuid`, invalidation du cache, déterminisme `compute_event_id`, `verify_citation` strict, `source_filename` dans le classifieur, motifs d'intention étendus à 9 types). 15 findings différés dans [`deferred-work.md`](deferred-work.md), 6 rejets vérifiés. L'Epic 009 reste **clos**.

L'**Epic 007 (Ontologie dynamique, v2) est intégralement clos avec succès (7/7 stories validées — 1550 tests verts, VERDICT GO)** :
- **Story 007-1 (done)** : [ADR 0014](../decisions/0014-pose-effective-ontology-graphstore.md) rompt le no-op de `set_ontology`, qui produisait des types métier à coût LLM puis les perdait — tous les nœuds du graphe ne portaient que le label générique `:Entity`. `GraphStore` est versionné (`version = 2`) et gagne deux paramètres keyword-only (`strict`, `ontology`) ; `OntologyToPydantic` traduit le dict d'ontologie en classes Pydantic en deux temps (schéma puis constructibilité) ; les deux implémentations sont alignées par une table de conformité testée. **C1 mesuré sur deux fixtures de domaines distincts** (télécom, énergie — 5 documents chacune, dont un long de plus de 20 000 caractères), sortie consignée dans [`mesure-007-1.txt`](plans/007-ontologie-dynamique/mesure-007-1.txt).
- **Story 007-2 (done)** : validation pré-persistance Graphiti, politique projet durable, routes PATCH/GET et rétrogradation transactionnelle. Les 14 patches de revue sont appliqués ; C2 est qualifié par 12 cas Neo4j réels. D1 est résolu ; la garantie distante Zep reste hors périmètre (ADR 0016/0017).
- **Story 007-3 (done au 13 octobre 2026)** : Entrées figées (corpus 10K et 50K sous `tests/fixtures/ontology/regeneration/`), passage de `OntologyGenerator.generate` à `temperature=0.0`, projection canonique `canonical_ontology_projection` dans `app/utils/ontology.py`. Sonde autonome `verifier_ontology_regeneration.py` avec isolation multi-tenant Neo4j et mode `--mock-llm`. Exécution réelle contre Neo4j et `gpt-6.1-sol` via passerelle Codex locale : intégrité de pose `set_ontology` et isolation conformes (< 10 ms), mais limites empiriques constatées sur le modèle (variations sémantiques nominales `LocalElectedOfficial` vs `LocalOfficial`, temps d'inférence > 90 s) actées en **NO-GO empirique C3** consigné dans [`mesure-007-3-hote.json`](plans/007-ontologie-dynamique/mesure-007-3-hote.json). Revue contradictoire BMAD 4 couches menée à bien (0 décision en suspens, 7 patches appliqués, 1 différé, 5 rejets motivés). Filet de tests porté à 1459 tests hermétiques.
- **Story 007-4 (done au 14 octobre 2026)** : Modèle immuable `OntologyVersion` (`ont_<uuid12>`), magasin atomique `OntologyVersionStore`, extension monotone du `Project` (`applied_ontology_id`, `applied_ontology_version`, `ontology_history`), et câblage réactif des événements : E1 (ajout de document, préservation des labels existants C4), E2 (diff brief substantiel `difflib.SequenceMatcher.ratio() < 0.95`), E3 (demande explicite API `POST /api/project/<id>/ontology/regenerate`), et E4 (initialisation atomique v1 lors de la création de projet). Endpoints d'API dans `backend/app/api/project.py` et rattachement de la version aux avertissements `GraphValidationWarning` (AC6). Revue contradictoire BMAD 4 couches validée. Filet global porté à **1485 tests verts sur l'hôte**.
- **Story 007-5 (done au 14 octobre 2026)** : Cohérence projet (C5, événement E5), transmission ontologique et composition avec `ActorClassifierService` (AC3, AC4, C6). Table `ONTOLOGY_ROLE_MAPPING` posée dans `actor_classifier.py` pour court-circuiter le LLM avec `confidence=1.0` et motivation déterministe lors de labels custom reconnus, tout en préservant la barrière anti-adversariale de l'Epic 009 (redirection vers la cascade standard en cas d'attributs hostiles). Raccordement de `applied_ontology_id` dans `prepare_simulation` / `SimulationManager` et propagation dans `SimulationParameters` (`simulation_config.json`) garantissant l'identité stricte entre simulations successives sans recalcul superflu. Preuve d'isolation multi-projets et transmission ascendante du type d'ontologie dans `OASISProfileGenerator` (`source_entity_type`). 34 nouveaux tests hermétiques ajoutés, filet global porté à **1519 tests verts sur l'hôte** (1516 réussis + 3 ignorés sous Docker). Revue contradictoire BMAD 4 couches validée.
- **Story 007-6 (done au 14 octobre 2026)** : Audit d'ontologie appliquée dans `ReportAgent` et exposition outillée LLM / API. Intégration de la sous-section Markdown « ### 6. Ontologie appliquée (Epic 007, FR-6) » dans `build_sources_provenance_section()` détaillant les types d'entités avec `InformationOrigin` et comptes réels, les types de relations, les métadonnées de version (`ont_<uuid12>`, date ISO 8601, parent, résumé de sources) et la politique de validation avec compte des avertissements récents. Omission conditionnelle stricte sur projet sans ontologie appliquée (AC2, C7). Outil LLM `get_applied_ontology` déclaré dans `_define_tools` et exécutable dans `_execute_tool` avec formatage JSON structuré complet. Décompte tolérant aux pannes `_get_ontology_instance_counts` (AC5, NFR-4) sans rupture de génération en cas d'indisponibilité de la base. Consolidation de `GET /api/project/<id>/ontology` (AC7, PRD Q4) avec politique, avertissements et statistiques sous `include_counts=true` et restitution sécurisée des connexions via `release_graph_store`. 18 tests hermétiques dédiés (`test_report_ontology_audit.py`, 15 initiaux + 3 issus de la revue BMAD), filet global porté à **1537 tests verts sur l'hôte** (0 échec). Revue contradictoire BMAD 4 couches validée.
- **Story 007-7 (done au 14 octobre 2026)** : Sonde autonome d'orchestration globale `backend/scripts/verifier_qualification_epic_007.py` évaluant de bout en bout l'ensemble des critères C1 à C8. Consignation du constat empirique C3 sur modèle externe amont (`gpt-6.1-sol`, 91–193 s) en NO-GO empirique C3 sans altérer le moteur interne. Rapport formel [`rapport-qualification-epic-007.md`](plans/007-ontologie-dynamique/rapport-qualification-epic-007.md) versionné avec **VERDICT GO**. Suite hermétique dédiée de 12 tests (`test_verifier_qualification_epic_007.py`) au vert. Revue contradictoire BMAD 4 couches validée (8 patches appliqués). Filet global porté à **1550 tests verts sur l'hôte** (0 échec). L'Epic 007 est **clos**.

## Fait

| Livrable | Où |
|---|---|
| LLM branché sur l'endpoint gratuit, en-têtes de session compris | commit `28c61d0` |
| Travail sécurisé : branche `local-first`, tag de sauvegarde, fork `zohac/MiroFish` | commits `28c61d0`, `50e9826` |
| Analyse Zep : rôle, rayon d'impact, obstacles | `docs/LOCAL-FIRST.md` §3–§6 |
| Audit des 6 forks communautaires | `docs/LOCAL-FIRST.md` §12 |
| 5 ADR — Graphiti, forks, ontologie, LLM, licence | `docs/decisions/` |
| 7 ADR — + Docker-first, structure par story | `docs/decisions/0006`, `0007` |
| 8 ADR — + pnpm (Node), version figée dans `packageManager` | `docs/decisions/0008` |
| Constitution, suivi, CI + lint ruff | `AGENTS.md`, `docs/sprint-status.yaml`, `.github/workflows/ci.yml` |
| Épreuve Graphiti local (Epic 001) : 6 stories validées, verdict GO documenté | [`docs/plans/001-epreuve-graphiti-local/`](plans/001-epreuve-graphiti-local/rapport.md) |
| Interface `GraphStore` (Epic 002) : 6 stories validées, ZepGraphStore, factory, refactoring services/api, tests AST d'isolation (470 tests verts) | [`docs/plans/002-interface-graphstore/`](plans/002-interface-graphstore/prd.md) |
| `GraphitiGraphStore` complet (Epic 003) : 5 stories validées, write/read pipeline, recherche hybride, reader agnostique, banc d'intégration réelle Neo4j (562 tests verts, Verdict GO) | [`docs/plans/003-chemin-de-lecture-graphiti/`](plans/003-chemin-de-lecture-graphiti/rapport-validation-integration.md) |
| Bascule sans Zep (Epic 004) : 5 stories validées, levée gardes API, LLM universel, ingestion et personas e2e, qualification globale (632 tests verts, Verdict GO) | [`docs/plans/004-bascule-sans-zep/`](plans/004-bascule-sans-zep/rapport-qualification-epic-004.md) |
| Environnement Docker de référence (Epic 005) : 5 stories validées, docker-compose unifié, persistance Neo4j, pipeline e2e conteneurisé, qualification Docker (711 tests verts, Verdict GO) | [`docs/plans/005-docker-local/`](plans/005-docker-local/rapport-qualification-epic-005.md) |
| Migration des données Zep (Epic 006) : 3 stories validées, sonde d'audit, pipeline ETL direct Neo4j, validation relecture GraphStore/OASIS et outil de purge sécurisé (800 tests verts) | [`docs/plans/006-migration-donnees-zep/`](plans/006-migration-donnees-zep/prd.md) |
| Éligibilité des acteurs et fiabilisation des sources (Epic 009) : 4 stories validées, barrière d'éligibilité, contrats ADR 0012/0013, sélection persistée, rapport vérifiable, anti-affabulation C7, qualification C1-C7 (1145 tests verts, Verdict GO) | [`docs/plans/009-eligibilite-acteurs-et-sources/`](plans/009-eligibilite-acteurs-et-sources/rapport-qualification-epic-009.md) |
| Ontologie dynamique (Epic 007) : 7 stories validées, banc C1-C8, rapport formel, 1550 tests verts, Verdict GO | [`docs/plans/007-ontologie-dynamique/`](plans/007-ontologie-dynamique/rapport-qualification-epic-007.md) |

## En cours / Prochaine étape

L'**Epic 008 (« Support complet de la langue française — Localisation FR ») est intégralement clos avec succès** (3/3 stories validées — **1649 tests verts sur l'hôte**, 9 tests frontend Node, VERDICT GO validé) :
- **Story 008-1 (done au 15 octobre 2026)** : Dictionnaire complet de traduction française (`locales/fr.json`) et parité stricte des clés. Rédaction intégrale des 679 clés réparties sur 17 sections (`common`, `meta`, `nav`, `home`, `main`, `step1`, `step2`, `step3`, `step4`, `step5`, `graph`, `history`, `api`, `progress`, `log`, `report`, `console`). Alignement rigoureux de la terminologie métier. Maintien strict de 100 % des variables de template `{var}`. Intégration backend dans `backend/app/utils/locale.py` avec fonction `normalize_locale()` selon RFC 7231 (`fr`, `fr-FR`, `fr-BE`, `fr-CA`). Suite unitaire hermétique de 7 tests (`backend/tests/test_i18n_parity.py`). Revue contradictoire BMAD 4 couches validée. Filet global porté à **1589 tests verts sur l'hôte** (0 échec).
- **Story 008-2 (done au 16 octobre 2026)** : Intégration et bascule IHM frontend Vue 3 (sélecteur accessible `LanguageSwitcher.vue`, formats régionaux `fr-FR` via `regionalFormat.js`, synchronisation dynamique de l'en-tête Axios `Accept-Language`, persistance `localStorage`). Suite unitaire Node hermétique (`pnpm --dir frontend test`, 9/9 tests passés) et compilation Vite sans erreur. Revue contradictoire BMAD 4 couches menée avec succès (5 patches appliqués : localisation de `'FINALIZING'`, parité trilingue des dictionnaires, gardes défensives booléens/tableaux dans `validDate` et `formatNumberValue`, sécurisation de `formatElapsedTime` contre `undefined`/`NaN`, saut de ligne terminal CI). 5 travaux différés consignés dans `docs/deferred-work.md`. Validation visuelle Docker réelle réussie à 100 % sur navigateurs bureau (Accueil, Graphe, Config, Simulation, Rapport, Prévalidation des acteurs sans résidu). Ergonomie responsive mobile préexistante (héritée de l'amont desktop-first) consignée en travail différé pour story ergonomique dédiée. DoD 100 % satisfait. Filet global : **1618 tests verts sur l'hôte**, 9 tests frontend Node.
- **Story 008-3 (done au 16 octobre 2026)** : Génération de personas, simulations et rapports en français (prompts LLM, ReACT et banc de validation). Locale canonique persistée par simulation (`SimulationState.locale`), propagation thread-safe Flask/threads/processus OASIS (`use_locale`). Confinement hermétique des contextes de langue et neutralisation des consignes antérieures lors des régénérations. Invariants stricts respectés (clés JSON anglaises, types PascalCase, relations UPPER_SNAKE_CASE, stances/poster_type et citations verbatim fidèles). 59 tests hermétiques dédiés passants (52 dans `test_simulation_locale.py`, 7 dans `test_verifier_qualification_epic_008_3.py`). Banc d'évaluation autonome sous conteneur Docker avec modèle réel validant AC1–AC8 avec **VERDICT GO** formalisé dans [`rapport-qualification-008-3.md`](plans/008-support-langue-francaise/rapport-qualification-008-3.md). Filet global porté à **1649 tests verts sur l'hôte** (0 échec).

Chantiers consécutifs :
- **Epic 011** : Preuve par les faits simulés, traçabilité épistémique et intégrité des rapports (OASIS post-simulation vivant, `interview_agents`, traces d'actions, anti-affabulation, bouclier ToolShield).

Dossier de plan complet : [`docs/plans/008-support-langue-francaise/`](plans/008-support-langue-francaise/epic-008.md).

L'**Epic 009 (« Éligibilité des acteurs et fiabilisation des sources ») est intégralement clos avec succès (4/4 stories validées — 1157 tests verts, VERDICT GO)**.

Dossier de plan complet : [`docs/plans/009-eligibilite-acteurs-et-sources/`](plans/009-eligibilite-acteurs-et-sources/prd.md) (`prd.md`, `architecture.md`, `epic-009.md`, `rapport-qualification-epic-009.md`).

L'**Epic 007 (« Ontologie dynamique (v2) ») est intégralement clos avec succès (7/7 stories validées — 1550 tests verts, VERDICT GO)**.

Dossier de plan complet : [`docs/plans/007-ontologie-dynamique/`](plans/007-ontologie-dynamique/prd.md) (`prd.md`, `architecture.md`, `epic-007.md`, `rapport-qualification-epic-007.md`).

L'**Epic 010 (« Fiabilisation du cycle de vie et complétion des simulations ») est intégralement clos avec succès (3/3 stories validées — 1580 tests verts)**.
Dossier de plan complet : [`docs/plans/010-fiabilisation-cycle-simulation/`](plans/010-fiabilisation-cycle-simulation/prd.md) (`prd.md`, `architecture.md`, `epic-010.md`).

Chantiers à venir :
- **Epic 011** : Preuve par les faits simulés, traçabilité épistémique et intégrité des rapports — maintien en vie d'OASIS post-simulation pour `interview_agents` en direct, interrogation des traces `actions.jsonl` / SQLite (`OasisLogReaderService`), bouclier `ToolShield` (zéro burn d'itérations), anti-affabulation, typage épistémique des sources, anti-troncature de section et localisation française native (`locales/fr.json`).

### Bilan consolidé de l'Epic 006 — Migration des données Zep (Clos — 800 tests verts)

L'epic 006 est intégralement achevé. Ses 3 stories ont été implémentées, testées et validées :
- **Story 006-1 (done)** : Sonde d'audit autonome `backend/scripts/auditer_graphes_zep.py`, inventaire complet des graphes distants Zep Cloud, détection de corrélation documentaire locale, arbre de décision formel (« Migrer vs Jeter vs Purger ») et export JSON/Markdown. 17 tests unitaires hermétiques (734 tests verts).
- **Story 006-2 (done)** : Pipeline ETL autonome `backend/scripts/migrer_zep_vers_graphiti.py`, rapatriement sans perte des nœuds et arêtes vers Neo4j local par lots Cypher `UNWIND`, préservation temporelle stricte ISO 8601 UTC et de l'attribut `entity_type` (coût marginal nul : 0 €). 36 tests unitaires hermétiques (771 tests verts).
- **Story 006-3 (done)** : Validation de relecture GraphStore et extraction personas OASIS (`valider_relecture_migree`, `SimulatedGraphStore`, flag `--verify-relecture`, critère C4). Outil autonome de purge distante sécurisée `backend/scripts/purger_graphes_zep.py` avec double confirmation interactive stricte, refus de sécurité sans `--yes` en non-interactif et masquage strict des secrets. 28 tests unitaires hermétiques (800 tests verts). Epic 006 clos.

### Bilan consolidé de l'Epic 005 — Environnement Docker de référence (Clos — 711 tests verts)

L'epic 005 est intégralement achevé. Ses 5 stories ont été implémentées, testées et validées :
- **Story 005-1 (done)** : Dockerfiles dédiés backend (`backend/Dockerfile`, Python 3.11, `uv sync --locked`) et frontend (`frontend/Dockerfile`, Node 20, `pnpm install --frozen-lockfile`) construits avec succès depuis les sources locales. Fichiers `.dockerignore` consolidés (0 secret, 0 artefact hôte). Suite de 19 tests unitaires hermétiques (`test_docker_build_config.py`). Filet global porté à **651 tests verts**.
- **Story 005-2 (done)** : `docker-compose.yml` unifié orchestrant les 3 services (`neo4j:5.26.31-community` avec APOC débridé, heap 512m/1G, volumes nommés `neo4j_data`/`neo4j_logs` et healthcheck Bolt `cypher-shell` ; `backend` Flask Python 3.11 sur `bolt://neo4j:7687` avec healthcheck HTTP `/health` ; `frontend` Vue 3 avec port paramétrable et proxy dynamique vers `BACKEND_URL`) sur réseau bridge `mirofish_network` avec ordonnancement strict (`condition: service_healthy`). Zéro secret en clair, injection sécurisée via `env_file` pour backend. Suite de 13 nouveaux tests unitaires hermétiques (`test_docker_compose_config.py`). Filet global porté à **664 tests verts** (+13).
- **Story 005-3 (done)** : Validation du filet global de tests (671 tests unitaires, 668 passants + 3 skipped sous Docker, 671 passants sur l'hôte) et de l'outillage de qualité (`ruff check .`, `validate_plans.py`) dans le conteneur de référence `mirofish-backend:local`. Inclusion des artefacts de gouvernance/docs, exception `!.env.example` dans `.dockerignore` (racine et backend) et adaptation de `test_pyproject_override.py` pour conteneurs sans `.git`. Suite de 7 nouveaux tests unitaires hermétiques (`test_docker_tooling_parity.py`, `test_pyproject_override.py`). Filet global porté à **671 tests verts** (+7).
- **Story 005-4 (done)** : Sonde de vérification autonome de persistance des données Neo4j et cycle de vie des volumes (`backend/scripts/verifier_persistance_neo4j_docker.py`). Preuve formelle de conformité au critère C3 du PRD : 100 % des nœuds et arêtes créés dans Neo4j sont préservés après un cycle `docker compose down && docker compose up -d` (sans `-v`). Preuve de réinitialisation complète lors de `down -v`. Préservation des montages bind `backend/uploads` et `backend/simulations`. Suite de 12 nouveaux tests unitaires hermétiques (`test_docker_volume_persistence.py`). Revue BMad 4 couches validée (6 patchs appliqués). Filet global porté à **684 tests verts** (+13).
- **Story 005-5 (done)** : Sonde d'orchestration de qualification Docker (`backend/scripts/verifier_qualification_docker.py`) validant l'ensemble des 5 critères C1 à C5 du PRD de l'Epic 005. Démarrage unifié mesuré en 6.2s ($\le 60$s, C1), filet de tests au vert (C2), persistance des volumes validée (C3), pipeline e2e local-first sans Zep validé dans le conteneur `backend` avec code retour 0 (6 entités Neo4j, 4 arêtes, 6 personas OASIS, C4), 0 secret dans les calques d'images Docker via `docker history` et CI 100 % conforme (C5). Suite de 26 tests unitaires hermétiques (`test_verifier_qualification_docker.py`). Revue BMad 4 couches validée (5 patchs appliqués). Rapport de qualification final versionné ([`rapport-qualification-epic-005.md`](plans/005-docker-local/rapport-qualification-epic-005.md)) avec **VERDICT GO**. Filet global porté à **711 tests verts** (+27). Epic 005 clos.

### Bilan consolidé de l'Epic 004 — Construire un graphe en local sans clé Zep (Clos — 632 tests verts)

L'epic 004 est intégralement achevé. Ses 5 stories ont été implémentées, testées et validées :
- **Story 004-1 (done)** : Paramétrabilité universelle du LLM via `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT`), harmonisation `LLMClient`/`MiroFishLLMClient` et neutralité d'hôte stricte. 15 tests unitaires hermétiques (577 tests verts).
- **Story 004-2 (done)** : Levée des gardes `ZEP_API_KEY` dans les routes API et les services métiers. Helper `Config.requires_zep_api_key()` posé et non-régression cloud préservée. 24 tests unitaires dédiés (601 tests verts).
- **Story 004-3 (done)** : Ingestion et construction de graphe de bout en bout avec `GraphitiGraphStore` et `GraphBuilderService`. Ingestion asynchrone `/api/graph/build` validée, banc d'épreuve réel Neo4j validé avec critère C3 satisfait (6 nœuds, 4 arêtes). 13 tests unitaires et d'intégration (614 tests verts).
- **Story 004-4 (done)** : Extraction d'entités, personas OASIS (Reddit JSON et Twitter CSV) et configuration de simulation sans Zep. Banc d'épreuve Neo4j validé avec critère C4 satisfait (6 personas conformes). 10 tests unitaires (624 tests verts).
- **Story 004-5 (done)** : Banc de qualification globale local-first (`verifier_qualification_local_first.py`) orchestrant le flux complet sans clé Zep. 100 % des critères C1 à C5 validés contre Neo4j réel, filet étendu à 632 tests verts (+8 tests, revue BMad validée avec 5 patchs) et verdict GO consigné dans [`rapport-qualification-epic-004.md`](plans/004-bascule-sans-zep/rapport-qualification-epic-004.md). Epic 004 clos.

### Bilan consolidé de l'Epic 003 — GraphitiGraphStore et chemin de lecture (Clos — 562 tests verts)

L'epic 003 est intégralement achevé. Ses 5 stories ont été implémentées, testées et validées :
- **Story 003-1 (done)** : Squelette de `GraphitiGraphStore`, déclaration formelle des 14 méthodes du contrat `GraphStore`, injection de dépendances, résolution des variables d'environnement, passerelle thread-safe `_run_async` avec runner d'arrière-plan `_AsyncLoopRunner` et activation de `ZEP_BACKEND='graphiti'` dans la factory `get_graph_store()`. 23 tests unitaires hermétiques (494 tests verts).
- **Story 003-2 (done)** : Implémentation du cycle de vie et de l'ingestion d'épisodes avec partitionnement strict par `group_id = graph_id` (C2). Normalisation ISO 8601 UTC des timestamps et optimisation d'index Cypher. 27 nouveaux tests unitaires (521 tests verts).
- **Story 003-3 (done)** : Implémentation de la lecture Cypher, des parcours de voisinage, de l'agrégation API et de la recherche hybride temporelle (`search` avec scopes `edges`, `nodes`, `hybrid`). Préservation intégrale de la temporalité (C3). 24 nouveaux tests unitaires (545 tests verts).
- **Story 003-4 (done)** : Adaptation du lecteur d'entités `zep_entity_reader.py` pour supporter le typage agnostique et les entités génériques Graphiti (`:Entity`). Résolution ordonnée de type `get_entity_type()` et filtrage préservant 100 % des nœuds valides. 10 nouveaux tests unitaires (555 tests verts).
- **Story 003-5 (done)** : Banc d'intégration réelle (`verifier_integration_graphiti.py`) validé contre l'instance Neo4j locale (`docker-compose.neo4j.yml`). 100 % des 14 méthodes exercées avec succès (C1), partitionnement multi-tenant étanche sans fuite (C2), métadonnées temporelles préservées (C3), extraction `ZepEntityReader` validée sur le graphe réel (C4), factory opérationnelle (C5), filet étendu à 562 tests verts (+7 tests) (C6), revue BMad validée avec 2 patchs appliqués et verdict GO consigné dans [`rapport-validation-integration.md`](plans/003-chemin-de-lecture-graphiti/rapport-validation-integration.md). Epic 003 clos.

### Bilan consolidé de l'Epic 002 — Interface `GraphStore` (Clos — 470 tests verts)

L'epic 002 est intégralement achevé. Ses 6 stories ont été implémentées, testées et validées :
- **Story 002-1 (done)** : Interface abstraite pure `GraphStore` (14 méthodes), modèles neutres immutables (`GraphNode`, `GraphEdge`, `GraphSearchResult`, `EpisodeRecord`, `BatchSubmissionRecord`, `GraphInfo`) et exceptions agnostiques (`GraphStoreError`) posés dans `backend/app/utils/graph_store/`. Zéro dépendance vers `zep_cloud` validée par AST. Filet de tests porté à 341 tests verts (+8).
- **Story 002-2 (done)** : Implémentation `ZepGraphStore` encapsulant 100 % des appels au SDK Zep Cloud, pagination unifiée, retries, conversion bidirectionnelle des modèles et mapping d'exceptions. Filet de tests porté à 409 tests verts (+68).
- **Story 002-3 (done)** : Factory `get_graph_store()`, configuration `ZEP_BACKEND` (`cloud` par défaut, `graphiti` réservé), validation de configuration et support d'override hermétique pour les tests (`override_graph_store`). 33 tests unitaires.
- **Story 002-4 (done)** : Refactoring complet des flux d'ingestion et d'écriture (`graph_builder.py`, `zep_graph_memory_updater.py`, `simulation_runner.py`) pour basculer sur l'interface `GraphStore` et éliminer tout import direct de `zep_cloud` et `utils.zep`. Filet de tests porté à 452 tests verts (+10).
- **Story 002-5 (done)** : Refactoring complet des flux de lecture et d'interrogation (`zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py`, `api/graph.py`). Découplage complet de `zep_cloud` et `utils.zep` via `GraphStore` et `get_graph_store()`. Filet de tests porté à 464 tests verts (+12).
- **Story 002-6 (done)** : Suite de tests d'isolation permanente (`test_graph_store_isolation.py`), validation AST de l'absence totale d'import Zep direct dans `services/` et `api/`, validation formelle des critères de sortie C1 à C6 du PRD, non-régression absolue avec **470 tests verts** et clôture de l'Epic 002.



### Bilan consolidé de l'Epic 001 — Épreuve Graphiti local (Verdict GO — Clos)

L'epic 001 est intégralement achevé. Ses 6 stories ont été implémentées, testées et validées :
- **Story 001-1** : Conflit de dépendances `graphiti-core` vs `camel-oasis` vérifié et mesuré (`mesure-001-1.txt`).
- **Story 001-1b** : `override-dependencies` du driver Neo4j posé dans `backend/pyproject.toml` (`neo4j 5.28.6`), prouvé réversible (`mesures-001-1b.md`), ADR 0010 et ADR 0011 respectés.
- **Story 001-2** : Driver forcé testé contre un vrai serveur `Neo4j 5.26.31-community` avec APOC (`docker-compose.neo4j.yml`), 17 contrôles validés deux fois, persistance C3 démontrée (`mesure-001-2-compose.txt`).
- **Story 001-3** : `MiroFishLLMClient` sous-classant `OpenAIGenericClient`, injection transparente des en-têtes OpenCode Go, mode `json_object` par défaut, critère C2 validé (0 échec `MissingSessionID`).
- **Story 001-4** : `SentenceTransformerEmbedder` local sans extra ni conflit, lazy-loading thread-safe, encodage asynchrone ~7 ms, intégration Graphiti sans clé OpenAI validée.
- **Story 001-5** : Banc de mesure automatisé (`mesurer_extraction_graphiti.py`) et épreuve sur les 30 premiers chunks du rapport AN n° 2506, rapport versionné [`rapport.md`](plans/001-epreuve-graphiti-local/rapport.md).
- **Story 001-6** : Décision formelle GO documentée, clôture de l'epic 001 et synchronisation des référentiels.

### La story 001-2 est `done` — le driver forcé **tient**

> C'est la réponse que l'ADR 0010 attendait et qu'il ne pouvait pas avoir : est-ce
> que `neo4j 5.28.6`, forcé contre le pin `==5.23.0` de `camel-oasis`, tient
> contact avec un vrai serveur ? **Oui.** 17 contrôles, deux fois, sur deux
> configurations de serveur. **L'ADR 0010 n'est pas supersédé.**
>
> La story est passée par **une revue de code à quatre couches** avant d'être
> close, et cette revue a trouvé mieux que des coquilles : **six garde-fous qui ne
> pouvaient pas échouer** — le secret, la dérogation APOC, le healthcheck, deux
> sur l'identifiant de conteneur — et un **critère C3 qui ne tenait que par
> coïncidence** de forme du graphe de vérification. Les 28 correctifs sont
> appliqués, **six vérifiés par mutation** sur le vrai fichier puis restauration à
> l'octet initial, et **les deux mesures ont été rejouées** sur le code corrigé.
> Cinq des « mutants vérifiés » que la story annonçait ne l'avaient pas été : le
> tri de la revue l'a montré, la correction l'a fait.

Premier contact avec un vrai serveur, donc premières mesures :

| Mesuré | Valeur |
|---|---|
| Driver | `neo4j 5.28.6` — lockée par `backend/uv.lock` |
| Serveur | `Neo4j 5.26.31` `community` — lue de `CALL dbms.components()`, pas du tag |
| Surface de l'ADR 0011 | 17/17 : `GraphDatabase.driver`, transactions, `Query`, 4 exceptions |
| Hiérarchie d'exceptions | tient — mais `Neo4jError` et `DriverError` sont **sœurs** sous `GqlError` |
| Volume nommé | le nœud survit à `stop` puis `start`, `valid_at` compris (**C3**) |
| Écart driver / serveur | 5.28.6 / 5.26.31 — mesuré, gardé par un test |

Au jalon 001-2, le compose d'épreuve était **séparé** — [`docker-compose.neo4j.yml`](../docker-compose.neo4j.yml)
— car le compose principal pointait alors l'image amont. Depuis l'Epic 005,
`docker-compose.yml` définit la stack locale de référence ; le compose d'épreuve reste disponible pour rejouer le protocole historique.

Deux mesures, parce qu'**APOC a deux réponses et non une** :

- `graphiti-core==0.30.2` **s'en passe** — zéro occurrence de `apoc` dans le
  paquet, et ses 31 requêtes d'indexation plus ses deux procédures vectorielles
  passent sur un serveur sans plugin ;
- **`camel-oasis` en a besoin** — `Neo4jGraph.__init__` lance `refresh_schema()`,
  qui exécute `CALL apoc.meta.data()`, et `add_nodes_from_df` utilise
  `apoc.merge.node`. Sans plugin, son chemin Neo4j casse dès le premier appel.

Le plugin reste donc dans le compose, mais pour une raison que
`architecture.md` §4 ne donnait pas — il y prescrivait APOC « repris du fork de
référence ». **Cette phrase est désormais fausse** : le fork avait APOC parce
que `camel` en a besoin, et c'est mesuré.

Trois découvertes que personne n'avait faites, toutes dans
[`story-001-2.md`](plans/001-epreuve-graphiti-local/story-001-2.md) § Notes de
complétion : la hiérarchie d'exceptions n'est pas une chaîne ; `graphiti-core`
appelle `CALL db.indexes()`, qui **n'existe pas** sur un 5.x (hors chemin
d'écriture, mais la 001-5 doit le savoir) ; et `apoc.merge.*` est refusé par
défaut même plugin installé — sans quoi `camel` accuse une installation
manquante qui est présente.

Fichiers : [`story-001-2.md`](plans/001-epreuve-graphiti-local/story-001-2.md),
[`verifier-001-2.sh`](plans/001-epreuve-graphiti-local/verifier-001-2.sh),
[`mesure-001-2-compose.txt`](plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt),
[`mesure-001-2-sans-apoc.txt`](plans/001-epreuve-graphiti-local/mesure-001-2-sans-apoc.txt).

### La story 001-3 est `done` — Client LLM Graphiti avec en-tête de session (C2 validé et relu)

> `MiroFishLLMClient` hérite de `OpenAIGenericClient` dans `backend/app/utils/graphiti_llm_client.py`.
> Les `default_headers` injectent automatiquement `x-opencode-session` et `User-Agent: mirofish/0.1.0`
> vers OpenCode Go sans polluer les autres fournisseurs (neutralité préservée même si `base_url=None`),
> le mode `json_object` est actif par défaut, les balises `<think>` des modèles de raisonnement
> sont nettoyées et `LLM_REASONING_EFFORT` est relayé via `extra_body`.
> Sonde de vérification fiabilisée (`backend/scripts/verifier_llm_graphiti.py`) et critère C2 prouvé
> (0 échec `MissingSessionID`). Revue de code contradictoire passée (4 couches, 6 correctifs appliqués).
> Fichier : [`story-001-3.md`](plans/001-epreuve-graphiti-local/story-001-3.md).

### La story 001-4 est `done` — Embedder local Sentence-Transformers pour Graphiti

> `SentenceTransformerEmbedder` sous-classe `EmbedderClient` dans `backend/app/utils/graphiti_embedder.py`.
> L'investigation a levé la fausse hypothèse de blocage : `graphiti-core` n'embarquant aucun embedder
> interne, aucun extra n'est nécessaire et `sentence-transformers==3.0.0` (fourni par `camel-oasis`)
> opère déjà localement.
> Modèle par défaut : `all-MiniLM-L6-v2` (384 dimensions, coût marginal de 0 €), chargement paresseux
> (*lazy-loading*) thread-safe, encodage asynchrone non-bloquant via `asyncio.to_thread` et conversion
> en flottants natifs Python.
> Sonde de vérification validée (`backend/scripts/verifier_embedder_graphiti.py`) : inférence ~7 ms à chaud,
> lot de 8 entités en ~50 ms (~6 ms/entité), mode `--mock` autonome et instanciation conjointe avec `Graphiti`
> sans clé OpenAI. Revue de code contradictoire passée (4 couches, 6 correctifs appliqués).
> 18 tests unitaires hermétiques dans `backend/tests/test_graphiti_embedder.py`. Fichier : [`story-001-4.md`](plans/001-epreuve-graphiti-local/story-001-4.md).

### La story 001-5 est `done` — Épreuve sur 30 chunks exécutée et rapport versionné (Verdict GO)

> Le banc de mesure autonome `backend/scripts/mesurer_extraction_graphiti.py` a exécuté
> l'épreuve complète en conditions réelles sur les 30 premiers chunks du document parlementaire
> (rapport AN n° 2506) avec `space-bunny`, l'embedder local `all-MiniLM-L6-v2` et Neo4j 5.26 :
> - **C1 (Épisodes sans erreur)** : **29/30 (96.7 %)** (seuil ≥ 90 % / 27/30). 1 seule anomalie isolée sur le chunk 22.
> - **C2 (Authentification / session)** : **0 échec `MissingSessionID`**.
> - **C3 (Persistance graphe Neo4j)** : **49 nœuds et 45 relations** persistés et relus.
> - **C4 (Temporalité `valid_at`)** : **11 arêtes temporelles** renseignées (corrigé en revue BMad 4 couches).
> - **C5 (Rapport versionné)** : [`rapport.md`](plans/001-epreuve-graphiti-local/rapport.md) généré avec **Verdict GO** en tête.
> Revue de code contradictoire passée (4 couches, 8 patchs appliqués, 1 rejeté documenté).
> 17 tests unitaires hermétiques dans `backend/tests/test_mesure_extraction_graphiti.py`. Fichier : [`story-001-5.md`](plans/001-epreuve-graphiti-local/story-001-5.md).

### La story 001-6 est `done` — Verdict formel GO et clôture de l'Epic 001

> Le verdict global de l'épreuve est formellement **GO** (aucun modèle payant externe requis).
> Tous les critères C1 à C5 fixés par le PRD sont respectés ou dépassés :
> - **C1 (Extraction sans erreur)** : **29/30 épisodes (96.7 %)** (seuil d'acceptation ≥ 90 % / 27/30). Une seule anomalie isolée (chunk 22, `ValidationError` Pydantic sans blocage de la chaîne).
> - **C2 (Session et auth)** : **0 échec `MissingSessionID`**, étanchéité de session complète.
> - **C3 (Persistance graphe Neo4j)** : Graphe non vide et relisible après redémarrage (**49 nœuds et 45 relations** persistés et relus).
> - **C4 (Temporalité)** : **11 arêtes temporelles** avec attribut `valid_at` explicite.
> - **C5 (Rapport versionné)** : [`rapport.md`](plans/001-epreuve-graphiti-local/rapport.md) généré, daté et versionné avec le verdict GO en tête.
>
> La thèse du projet local-first est confirmée : l'extraction de connaissances à coût marginal de 0 €
> fonctionne de bout en bout sans modèle payant. L'epic 001 est officiellement clos, débloquant l'epic 002.
> Fichier : [`story-001-6.md`](plans/001-epreuve-graphiti-local/story-001-6.md).

**333 tests verts**, tous hermétiques et sans `.env` (+18 par la 001-5 et sa revue).

**`graphiti-core` envoie une télémétrie par défaut — elle est coupée.**
`posthog 7.62.1` entre dans le lock avec `graphiti-core`, et la bibliothèque
écrit une télémétrie d'initialisation vers `us.i.posthog.com` depuis
`Graphiti.__init__`, **activée par défaut** (`telemetry.py:36`, défaut `'true'`).
Un projet dont la thèse est le local-first ne peut pas laisser sortir de la
machine sans l'avoir demandé : `app/config.py` pose
`GRAPHITI_TELEMETRY_ENABLED=false` par défaut **et** pousse la variable dans
l'environnement, parce que c'est là que la bibliothèque la lit. Six tests, dont un
qui prouve que la bibliothèque aurait été active de sa propre initiative.

L'override, dans la forme exacte que l'ADR 0011 impose :

```toml
[tool.uv]
override-dependencies = ["neo4j>=5.26.0,<6.0.0"]
# version effectivement résolue au lock du 2026-10-03 : neo4j 5.28.6
```

Le point difficile n'était pas la déclaration : c'est que poser l'override
**cascait le protocole de mesure de la 001-1**. Il ne casse plus — il **normalise**
`pyproject.toml` dans l'état qu'il veut mesurer, puis restaure l'octet initial,
et **refuse** un arbre ambigu au lieu de le deviner. Rejoué sur les deux arbres,
204 tests verts sur l'arbre d'avant, 234 sur celui d'après — les deux sorties
sont versionnées dans [`mesures-001-1b.md`](plans/001-epreuve-graphiti-local/mesures-001-1b.md).
[`story-001-1b.md`](plans/001-epreuve-graphiti-local/story-001-1b.md).

## À faire

| Epic | Titre | Dépend de |
|---|---|---|
| 006 | Migrer le graphe Zep existant — ou acter qu'on jette (clos) | 003, 004, 005 |
| 009 | Éligibilité des acteurs et fiabilisation des sources (clos, 1157 tests verts) | 004, 005 |
| 007 | Ontologie dynamique (v2) — clos (1550 tests verts, Verdict GO) | 003, 004, 005, 009 |
| 010 | Fiabilisation du cycle de vie et complétion des simulations (clos, 1580 tests verts) | 005, 007, 009 |
| 011 | Preuve par les faits simulés, traçabilité épistémique et intégrité des rapports | 005, 007, 009, 010 |
| 008 | Support complet de la langue française (Localisation FR) | 005 |

---

## Synthèse des critères de l'épreuve (Epic 001) — Verdict GO validé

| # | Critère | Seuil PRD | Mesuré en conditions réelles | Statut |
|---|---|---|---|---|
| C1 | Épisodes extraits sans erreur | **≥ 27 sur 30** chunks (90 %) | **29 sur 30 (96.7 %)** | ✅ Conforme |
| C2 | Échecs d'authentification (`MissingSessionID`) | **0** | **0** | ✅ Conforme |
| C3 | Graphe non vide **et relisible après redémarrage de Neo4j** | ≥ 1 entité, ≥ 1 relation persistées | **49 nœuds, 45 relations** | ✅ Conforme |
| C4 | Temporalité : `valid_at` renseigné | ≥ 1 arête | **11 arêtes temporelles** | ✅ Conforme |
| C5 | Rapport de mesure versionné dans le dépôt | 1 fichier | **[`rapport.md`](plans/001-epreuve-graphiti-local/rapport.md)** | ✅ Conforme |

Échantillon : les 30 premiers chunks du rapport n° 2506 de l'Assemblée
nationale (URL et sha256 dans le PRD de l'epic 001).

**Règle de décision** : tous les critères critiques étant validés, la décision a été un
**GO formel** pour engager le remplacement de Zep par Graphiti + Neo4j derrière
l'interface `GraphStore` (Epic 002, désormais achevé).

## Prochain pas

1. **Poursuivre l'Epic 008** : Support complet de la langue française (Localisation FR) — Story 008-1 validée (`locales/fr.json` à 100 % de parité, normalisation RFC 7231 backend), enchaînement sur Story 008-2 (IHM Vue 3) et 008-3 pour préparer le déploiement de l'Epic 011.
2. **Engager ensuite l'Epic 011** : Preuve par les faits simulés, traçabilité épistémique et intégrité des rapports (maintien d'OASIS vivant pour `interview_agents`, lecture directe des traces `actions.jsonl`/SQLite, `ToolShield`, contrat `ReportClaim`, tableau de couverture, anti-troncature et barrière `ReportQualityGate`).
3. **Graphes migrés de l'Epic 006 clos** : la barrière d'acteurs de 009-1 s'applique désormais à la préparation ; ne pas rouvrir la migration ni inventer une provenance absente.

## Questions ouvertes

| Question | Effet si la réponse change |
|---|---|
| Le graphe Zep actuel contient-il quelque chose à garder ? | Epic 006 : migration possible ou non |
| ~~`camel-oasis` et `graphiti-core` sont-ils compatibles dans un venv ?~~ | **répondu non** (story 001-1) — parade mesurée et rejouable : override du driver, **actée par l'ADR 0010**, précisée par l'ADR 0011 |
| ~~Le driver `neo4j` forcé à **5.28.6** tient-il **à l'exécution** ?~~ | **Validé (story 001-2)** : 17 contrôles réussis deux fois, persistance prouvée, l'ADR 0010 n'est pas supersédé |
| ~~`sentence-transformers` : même conflit que `neo4j` ?~~ | **fausse hypothèse levée** (story 001-4) : `graphiti-core` ne fournit pas d'embedder, l'interface `EmbedderClient` est abstraite et `sentence-transformers==3.0.0` opère déjà sans extra ni override |
| ~~La politique d'usage de l'endpoint gratuit tient-elle à ce volume ?~~ | **Validé (story 001-5)** : 29/30 chunks extraits sans saturation ni blocage réseau sous rate limiting (délai 1s) |
| ~~Le reranker supporte-t-il cet endpoint (logprobs) ?~~ | **Validé (story 001-5)** : repli pass-through local sans appel externe ni clé OpenAI (NFR-1) |

## Chiffres de référence

| | |
|---|---|
| Tests | **1589 tests collectés et réussis sur l'hôte** (**1586 réussis + 3 ignorés sous Docker**), mesure du 15 octobre 2026. Epics 007 et 010 clos, Story 008-1 close (+7 tests unitaires i18n hermétiques). |
| Lint | ruff, règles volontairement étroites (amont) |
| Amont | `666ghj/MiroFish` — AGPL-3.0, très actif |
| ADR | 17 acceptés, 0 supersédé |
| Node | pnpm 10.23.0, version figée dans `packageManager`, `package-lock.json` supprimés |
| Environnement de référence | Docker opérationnel (ADR 0006, Epic 005 clos) — stack 3 services (`neo4j`, `backend`, `frontend`) unifiée |
| Fork audités | 6 — 0 adopté |
