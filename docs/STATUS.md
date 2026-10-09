# État du projet

Une page, mise à jour à chaque changement d'epic. La source de vérité est
[`sprint-status.yaml`](sprint-status.yaml) — ce fichier en est la **vue
humaine**, pas un second saisie.

> Dernière mise à jour : **9 octobre 2026** · branche `local-first`

---

## Où on en est

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

## En cours

**Epic 004 — Construire un graphe en local sans clé Zep** (ADR 0001, ADR 0003).
Preuve finale de bout en bout de l'application : documents → graphe Graphiti → personas → simulation → rapport, sans `ZEP_API_KEY`.
- **Story 004-1 (done)** : Paramétrabilité universelle du LLM via `.env` (compatible OpenAI, gratuit ou payant). `Config.LLM_REASONING_EFFORT` déclaré et exposé, résolution des paramètres homogénéisée entre `LLMClient` et `MiroFishLLMClient`, neutralité stricte prouvée (aucun en-tête OpenCode vers OpenAI, DeepSeek, Groq ou Ollama), robustesse aux espaces parasites, transmission propre de `reasoning_effort` et suite de tests unitaires dédiée (+15 tests, revue BMad validée). Filet global porté à **577 tests verts**.

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

Le compose d'épreuve est **séparé** — [`docker-compose.neo4j.yml`](../../docker-compose.neo4j.yml)
— parce que `docker-compose.yml` pointe l'image amont (AGENTS.md §2.9). L'epic
005 l'absorbera quand l'environnement de référence existera.

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
| 004 | Construire un graphe sans clé Zep — la preuve finale (en cours) | 003 |
| 005 | Docker local : Neo4j dans le compose — **le compose d'épreuve existe déjà**, il s'y substituera | 003 |
| 006 | Migrer le graphe Zep existant — ou acter qu'on jette | 003 |
| 007 | Ontologie dynamique (v2) | 003 |

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

1. **Démarrer la Story 004-2** : Levée des gardes `ZEP_API_KEY` dans les routes API `/api/graph/` et `/api/simulation/` et les services associés lorsque `ZEP_BACKEND='graphiti'`.
2. **Poursuivre avec la Story 004-3** : Pipeline d'ingestion et construction de graphe local sans clé Zep.

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
| Tests | **571**, tous verts, **sans `.env`** (filet de tests post-Story 004-1 ; 562 avant Epic 004) |
| Lint | ruff, règles volontairement étroites (amont) |
| Amont | `666ghj/MiroFish` — AGPL-3.0, très actif |
| ADR | 11 acceptés, 0 supersédé |
| Node | pnpm 10.23.0, version figée dans `packageManager`, `package-lock.json` supprimés |
| Environnement de référence | Docker dès que l'epic 005 est fait (ADR 0006) — en attendant, on travaille en local, et c'est dit |
| Fork audités | 6 — 0 adopté |
