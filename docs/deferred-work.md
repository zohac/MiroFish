# Travail différé

Choses réelles, mais hors du périmètre de la revue en cours. Chaque entrée dit
pourquoi elle est différée et ce qui la déclencherait.

## Deferred from: code review of story-001-1.md (2026-10-03)

Revue des commits `c1e17e0` + `0cdf1c0` (`ad4ef4c..HEAD`), le 3 octobre 2026.

- **`AGENTS.md:231` — `definition_of_ready` annoncé comme un identifiant lu par `validate_plans.py`.** `STORY_META_REQUIRED` vaut `("id", "epic", "titre", "statut", "auteur")` ; la clé n'est lue nulle part et ne subsiste que dans le tableau YAML d'ADR 0007, le format que l'ADR 0009 a supprimé. Un agent qui suit `AGENTS.md` §2.10 ajoutera une clé que le validateur ignore en silence. *Différé : le correctif édite un fichier de contexte agent.*
- **`AGENTS.md:428` — ancre `LOCAL-FIRST.md §11.4` pendante.** §11 « Points ouverts » n'a aucune sous-section ; ses items sont une liste numérotée. §12, lui, a bien `### 12.1`–`### 12.6`. Deux notations pour deux types de sections, dans le tableau « ce qui est déjà réglé — ne pas re-dériver » dont la valeur tient à ce que les ancres restent valides. *Différé : le correctif édite un fichier de contexte agent.*
- **`docs/decisions/0010-override-driver-neo4j.md` — la revalidation à chaque release du driver n'a pas de propriétaire.** L'ADR nomme le coût, admet que « rien ne surveille la dérive en continu », et ne dit ni qui revalide ni comment on le remarquerait. La version résolue est désormais consignée (`neo4j 5.28.6`, ADR 0011), ce qui fixe **ce qui** est testé ; il reste à dire **qui** réévalue quand le driver sort une 5.x. **Partiellement traité le 4 octobre 2026** (story 001-1b) : *comment on le remarquerait* est désormais mécanique — `test_resolved_version_comment_matches_the_lock` échoue dès que la version lockée s'écarte de la version consignée, et la suite tourne en CI. *Il reste **qui**, voir l'entrée de la 001-1b ci-dessous. Le modifier suppose un ADR de précision, l'ADR 0010 étant immuable. La partie `LOCAL-FIRST.md` §12.6 de ce constat a été traitée dans le même mouvement que le patch documentaire.*
- **`docs/README.md:29-33` — l'ADR 0010 n'y figure pas.** L'index s'arrête à 0005 ; 0006-0009 manquent déjà. Ce diff ajoute 0010 à `docs/decisions/README.md` mais pas à `docs/README.md`, que `AGENTS.md` §9 liste pourtant comme index de la documentation. *Différé : préexistant, et de faible enjeu.*
- **`backend/scripts/validate_plans.py:43-50,101-108` — titres de section en NFD (décomposition Unicode).** Le motif `^##\s+Tâches\s*$` ne correspondrait pas à un titre en NFD, qui serait rapporté « section obligatoire absente » pour les six sections à la fois. *Différé : `maybe-false` — aucun fichier de story de ce dépôt n'est en NFD, et l'échec serait bruyant en nommant le titre attendu. Ce qui trancherait : un fichier de story en NFD atteignant le validateur, et la confirmation qu'un plan rédigé sur un poste macOS peut en produire un.*

## Deferred from: code review of story-014-1.md (2026-10-22)

Revue BMAD du commit `e3f868f` (« feat(014-1): régime de provenance des entretiens de rédaction »).

- **Artefacts manquants pour la clôture de la story 014-1** — `backend/tests/test_provenance_regime.py`, `backend/scripts/verifier_provenance_interviews.py` et `docs/plans/014-integrite-preuves-redaction/mesure-014-1.md` sont absents alors que la définition de fini et l'AC10/AC11 les exigent ; les notes de complétion l'admettent. La story ne peut pas être marquée `done` tant qu'ils ne sont pas produits. *Déclencheur : rédaction du fichier de tests et du script de mesure, puis re-qualification.*

## Deferred from: story-001-1b.md (2026-10-04)

Pose de l'`override-dependencies` du driver `neo4j`, geste des ADR 0010 et
0011. Ces trois points sont **les dettes que l'override contracte**, pas du
travail laissé en suspens par la story.

- **Qui réévalue l'override quand le driver sort une 5.x.** L'ADR 0010 nomme le
  coût — « rien ne surveille la dérive en continu » — sans nommer de
  propriétaire ; l'entrée de la revue 001-1 ci-dessus le constatait déjà. Il
  reste ouvert après cette story : **le propriétaire proposé est l'agent qui
  rouvre l'epic 001**, à chaque `uv lock`, et le déclencheur est mécanique —
  `backend/tests/test_pyproject_override.py::test_resolved_version_comment_matches_the_lock`
  échoue dès que la version lockée s'écarte de celle consignée dans
  `backend/pyproject.toml`. C'est une amélioration réelle par rapport à l'ADR
  0010, qui disait « rien ne surveille la dérive en continu » : la suite la
  surveille, donc la CI la surveille. *Ce qui reste à faire, et qui n'est pas
  fait : nommer ce propriétaire dans un **ADR de précision** (l'ADR 0010 est
  immuable), et décider si une release du driver doit déclencher une story de
  revalidation plutôt qu'un simple correctif de commentaire.*
- **L'override promet une compatibilité que rien ne prouve à l'exécution.**
  `neo4j 5.28.6` est lockée, les imports passent dans l'ordre, les 204 tests
  sont verts — et **aucune connexion n'a jamais été ouverte** sous cet override.
  Le comportement réel reste au compte de la story 001-2, qui est le premier
  test comportemental ; s'il casse, l'ADR 0010 est **supersédé**, pas réécrit.
  *Ce qui déclencherait : une 5.x plus récente, ou un changement d'API dans la
  surface relevée par l'ADR 0011 (`GraphDatabase.driver`, `Query`, quatre types
  d'exceptions).*
- **La télémétrie de `graphiti-core` est coupée par défaut, mais rien ne la surveille en continu.** `posthog 7.62.1` est un transitif de `graphiti-core` : la bibliothèque écrit une télémétrie d'initialisation vers `us.i.posthog.com` depuis `Graphiti.__init__`, **activée par défaut** (`telemetry.py:36`). Le 4 octobre 2026, `app/config.py` l'a désactivée par défaut et posée dans l'environnement, avec six tests. Ce que ça ne couvre pas : le jour où `graphiti-core` ajoute un **autre** client de télémétrie, ou déplace sa cible, rien ne le verra — `test_the_library_default_would_have_been_on` vérifie le défaut de la bibliothèque d'aujourd'hui, pas son périmètre. *Ce qui déclencherait : une mise à jour de `graphiti-core`, qui exige de rejouer ce test et de relire `graphiti_core/telemetry/`.*
- **`uv sync --frozen` n'était pas une garantie, et le dépôt le croyait.** L'image et la CI ont utilisé `--frozen` (« ne pas mettre à jour le lock ») pendant qu'on croyait que cela signifiait « vérifier que le lock est à jour ». Vérifié le 4 octobre 2026 : sur un `pyproject.toml` que le lock ne satisfait pas, `--frozen` sort en **0** et l'image part sans la dépendance — c'est `--locked` qui sort en 1. Corrigé dans `Dockerfile:24` et `.github/workflows/ci.yml`. *Ce qui reste : la même confusion peut revenir sur le flag frontend (`pnpm install --frozen-lockfile`), qui a une sémantique analogue et n'a pas été testée comme celle-ci.*
- **La surface relevée par l'ADR 0011 est un relevé ponctuel, pas un contrat.**
  Il porte sur `camel-oasis 0.2.5` et `camel-ai 0.2.78`. Le réintégrage de
  l'amont (`AGENTS.md` §2.6, ~100 commits depuis mars) peut apporter une
  surface supplémentaire. *Ce qui déclencherait : un `git rebase upstream/main` —
  ~~le relevé est à refaire avant la story 001-2~~ (périmé au 5 octobre 2026 : c'est
  cette story qui l'a fait).*
  **Partiellement traité le 5 octobre 2026** (story 001-2) : la surface est
  désormais **exercée** et non seulement importée, par
  `backend/scripts/verifier_driver_neo4j.py` — 17 contrôles, dont les quatre
  types d'exceptions obtenus pour de vrai. Si le réintégrage ajoute un symbole,
  le contrôle correspondant manquera, et le rapport le dira d'autant moins
  qu'il ne peut pas voir ce qu'il ne cherche pas. *Ce qui reste : refaire le
  relevé **avant** la story 001-5, et non après — la 001-5 est le premier
  chemin où une surface manquante se paie en extraction ratée.*

## Deferred from: story-001-2.md (2026-10-05)

Ce que la mesure a trouvé et que la story ne traite pas, faute de périmètre ou
de suite de tests. Aucun de ces points n'est un doute : tous sont des faits
mesurés, consignés dans les sorties versionnées.

- **`graphiti-core 0.30.2` appelle `CALL db.indexes()`, que Neo4j 5.26 n'a pas.**
  `graphiti_core/driver/neo4j/operations/graph_ops.py:73` et
  `neo4j_driver.py:198` l'utilisent pour `delete_all_indexes`, atteint uniquement
  par `build_indices_and_constraints(delete_existing=True)`. Mesuré le
  5 octobre 2026 : `ClientError … ProcedureNotFound`. **Ce n'est pas bloquant pour
  l'extraction** — le chemin d'écriture d'épisodes n'y passe pas, et le chemin
  d'indexation que `Graphiti.__init__` lance en tâche de fond passe intégralement
  (31 index créés et visibles dans `SHOW INDEXES`, mesuré). Mais la story 001-5
  butera dessus si elle veut repartir de zéro par cette voie. *Ce qui
  déclencherait : le choix de la 001-5 sur sa stratégie de remise à zéro — le
  contournement est un `SHOW INDEXES YIELD name DROP INDEX name` en Cypher pur,
  et la décision de ne pas patcher la bibliothèque appartient à un ADR, pas à
  une story de mesure.*
- **La hiérarchie d'exceptions du driver n'est pas celle qu'on imaginait.**
  `Neo4jError` et `DriverError` sont des branches **sœurs** sous `GqlError`, pas
  une chaîne : mesuré le 5 octobre 2026 sur `neo4j 5.28.6`. Ce n'est donc pas
  une dérive 5.23 → 5.28, c'est une structure qui n'a jamais été celle que
  l'ADR 0010 supposait. Ce que `camel` attrape reste correct — `ClientError`
  couvre bien `AuthError`, `CypherSyntaxError` et `ConstraintError` — mais un
  `except DriverError` n'attraperait **pas** `ClientError`. L'ADR 0011 reste
  donc valable sur la surface, et son inventaire ne doit pas être lu comme une
  hiérarchie. *Ce qui déclencherait : une version de driver qui unifie les deux
  branches — le contrôle de hiérarchie du script le verrait.*
- **L'override de `pyproject.toml` ne contraint pas le serveur.**
  `neo4j>=5.26.0,<6.0.0` borne le **driver** ; le serveur est choisi par le
  compose, et rien dans les dépendances ne l'aligne. L'écart 5.28.6 / 5.26.31
  est mesuré et gardé par `backend/tests/test_neo4j_serveur_epreuve.py`, mais ce
  test lit le compose : une image de serveur reconstruite **sous le même tag**
  passerait. *Ce qui déclencherait : la construction de l'image Neo4j par
  l'epic 005 — il faudra alors un test qui compare le tag au contenu, ou acter
  qu'on accepte l'image amont de confiance.*
- **Le healthcheck du compose interroge le Bolt, mais pas le contenu.**
  Il vérifie qu'une requête passe, pas que le graphe survit. C'est suffisant
  pour un démarrage, et c'est le script `ecrire`/`relire` qui porte C3. *Ce qui
  déclencherait : le besoin d'un healthcheck « la base a du contenu », qui n'a
  pas de sens pour une base neuve et n'en aurait que pour un graphe d'épreuve
  déjà construit — donc probablement jamais.*

## Deferred from: code review of story-001-2.md (2026-10-05)

Revue du commit `61fc51a` par quatre couches indépendantes. **Trois constats
avaient été différés** ; deux ont été **traités dans le même mouvement** que la
clôture de la story, parce que les fichiers étaient déjà ouverts et que laisser
un chiffre faux vieillir coûte plus cher que le corriger :

- ~~**`AGENTS.md` §4 ne listait pas quatre des sept livrables de la 001-2.**~~
  **Traité le 5 octobre 2026** : le protocole `verifier-001-2.sh`, les deux
  sorties de mesure et les deux fichiers de tests sont dans la carte du dépôt.
- ~~**`epic-001.md` NFR-5 restait à « 234 ».**~~ **Traité le 5 octobre 2026** :
  NFR-5 porte le compte réel (279) et **dit désormais que le seuil suit les
  stories** — c'est la règle, pas le chiffre, qui doit tenir.

Reste un constat, qui ne se corrige pas dans une story :

- **La story est passée `backlog → review` en un seul commit, sans passer par
  `in-progress`.** `git log` ne montre que deux révisions du fichier :
  `3eddc18` (`statut: backlog`) puis `61fc51a` (`statut: review`). `AGENTS.md`
  §2.8 exige `backlog → in-progress → review → done`, « jamais de saut », et
  reconnaît lui-même que la règle « n'est outillée par rien » :
  `validate_plans.py` lit des fichiers, pas un historique, et passe. Le garde-fou
  de la constitution a donc été contourné sans bruit. *Ce qui déclencherait : rien
  d'automatique. Le seul remède est une trace dans le fichier de story — donc
  dans la spec sous revue — que la revue de code n'a pas le droit de réécrire.*
  *Ce qui reste à faire, hors revue : décider si la constitution doit gagner un
  contrôle outillé de la transition, puisqu'elle admet elle-même que la règle
  n'est pas appliquée.*

## Deferred from: code review of story-002-5.md (2026-10-07)

Revue contradictoire menée sur les flux de lecture et d'interrogation du graphe (Story 002-5) :

- **`zep_entity_reader.py:203` et `zep_tools.py:716` — Repli sur `target_graph_id = "default"` en cas d'absence de `graph_id`.** Les signatures amont historiques de `get_node_edges(node_uuid)` et `get_node_detail(node_uuid)` ne prenaient pas de `graph_id`. Dans un store partitionné (Graphiti / Neo4j), requêter `"default"` échouerait si la partition n'existe pas. *Différé : casser ces signatures impacterait les appelants amont ; la refonte globale des signatures de lecture est planifiée dans l'Epic 003.*
- **`zep_entity_reader.py:388-398` — Boucle séquentielle N+1 `store.get_node` dans `get_entity_with_context`.** Pour chaque relation connectée à une entité, `get_node` est appelé séquentiellement. *Différé : code hérité du comportement amont, sans régression introduite. L'optimisation par requête de voisinage groupée sera traitée avec l'introduction du GraphitiGraphStore en Epic 003.*

## Deferred from: code review of story-003-1.md (2026-10-08)

Revue contradictoire menée sur le squelette et l'initialisation de GraphitiGraphStore (Story 003-1) :

- **`backend/app/utils/graph_store/graphiti_store.py:110` — Absence de méthode de fermeture explicite du pool de connexions (`close()`) sur `GraphStore` et `GraphitiGraphStore`.** Ni l'interface abstraite `GraphStore` (`base.py`) ni `ZepGraphStore` ne définissent de méthode `close()` ou de context manager pour libérer les ressources réseau sous-jacentes. Dans `GraphitiGraphStore`, le pool de connexions du driver Neo4j reste alloué jusqu'au garbage collection du processus. *Différé : l'ajout d'une méthode de cycle de vie relève d'une évolution de l'interface commune `GraphStore` partagée avec l'ensemble des backends (Epic 003 ou Epic 005).*

## Deferred from: code review of story-005-2.md (2026-10-09)

Revue contradictoire menée sur l'environnement unifié `docker-compose.yml` (Story 005-2) :

- **`frontend/src/api/index.js:6` — `baseURL` absolu `http://localhost:5001` contournant le proxy interne Vite.** Axios initialise une instance avec `baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'`, ce qui fait partir les requêtes du navigateur directement vers le port hôte au lieu d'utiliser le proxy relatif `/api` géré par Vite (`http://backend:5001`). Si l'utilisateur accède à MiroFish depuis une IP distante ou avec un `FLASK_PORT` alternatif sans configurer `VITE_API_BASE_URL`, les appels API échouent. *Différé : code hérité du dépôt amont, à traiter globalement lors de la qualification e2e de l'environnement Docker de référence (Story 005-5).*

## Deferred from: code review of story-009-1.md (2026-10-11)

Revue contradictoire à quatre couches (Blind Hunter, Edge Case Hunter, Verification Gap, Acceptance Auditor) des changements non commités de la story 009-1. Trois constats différés, mesures et vérifications faites fichier et ligne en main :

- **`AGENTS.md:535` (§11) + §4 + `docs/LOCAL-FIRST.md:168` — Index documentaires périmés après la barrière d'éligibilité.** §11 exige encore « 333 passed » au démarrage de session, la carte du dépôt (§4) ne liste ni `app/services/actor_classifier.py`, ni `app/models/actor_eligibility.py`, ni `scripts/verifier_eligibilite_acteurs.py`, et la description du pipeline dans `LOCAL-FIRST.md` ignore la barrière et cite `oasis_profile_generator.py:385-409` (plage déplacée). Y figurent aussi l'état et les compteurs d'avant clôture (AGENTS.md §1/§2.2, `docs/STATUS.md` : « story 009-1 en review », « 903 réussis »). *Différé : corrections d'index hors du lot de code, à traiter avec la mise à jour documentaire suivante.*
- **`docs/plans/009-eligibilite-acteurs-et-sources/prd.md:3` et `architecture.md:3` — Statut `backlog` et « composants non encore implémentés » alors que l'epic est `in-progress` et les modules livrés.** *Différé : mise à jour d'artefacts de plan, à faire à la prochaine actualisation d'epic.*
- **`docker-compose.yml:63-65` — Le décompte Docker « 903 réussis » n'est pas reproductible par la commande de la constitution.** `docker compose run --rm backend uv run pytest tests/ -q` exécute l'arbre figé dans l'image (727 réussis, 3 ignorés, 730 collectés constatés), le compose ne montant que `uploads/` et `simulations/` ; `AGENTS.md` §2.9 affirme pourtant que le code est monté en volume en développement. Le décompte de la story dépend du protocole « copie explicite » qui n'est pas consigné. *Différé : reconstruction d'image et consignation du protocole relèvent d'un geste séparé, hors du lot 009-1.*

## Deferred from: code review of story-009-4.md (2026-10-12)

Revue contradictoire à quatre couches (Blind Hunter, Edge Case Hunter, Verification Gap, Acceptance Auditor) des changements non commités de la story 009-4. Tous les constats sont vérifiés fichier et ligne en main. Le passage direct `backlog → done` est traité en `decision_needed` dans la story.

- **Incohérence de comptage de tests : 14 réels vs 15 annoncés** [story-009-4.md §Revue, sprint-status.yaml]. Comptage effectif : `test_provenance_tools_service.py` (5) + `test_simulation_action_verifier.py` (5) + `test_report_agent_provenance.py` (4) = 14 tests. La section « Revue » dit 14, le `sprint-status.yaml` dit +15 et `rapport-qualification-epic-009.md` dit `1145 passed = 1130 + 15`. *Différé : alignement d'un chiffre dans la documentation.*
- **`build_sources_provenance_section` catche `Exception` avec `logger.debug`** [backend/app/services/report_agent.py:1899-1908]. Un échec d'intégration (par exemple, base corrompue) se manifeste comme « aucun document source », pas comme un diagnostic. *Différé : passage à `logger.warning` quand la section sera revisitée.*
- **`build_sources_provenance_section` prend le premier projet parmi plusieurs** [backend/app/services/report_agent.py:1898-1906]. Si plusieurs `Project` partagent un `graph_id`, seul le premier est rendu. *Différé : le multi-projet par `graph_id` n'est pas un cas d'usage actuel.*
- **`analyze_intentions` `break` au premier match** [backend/app/services/simulation_action_verifier.py:372]. Un post contenant plusieurs intentions (« je vais boycotter et voter ») ne détecte que la première. *Différé : cas multi-intentions rare en pratique.*
- **Chemins de plateformes hardcodés dans `load_simulation_actions`** [backend/app/services/simulation_action_verifier.py:210-214]. L'ajout d'une plateforme exige une édition de code. *Différé : pas de plateforme supplémentaire planifiée.*
- **Chinois dans les docstrings et retours de `ReportAgent`** [backend/app/services/report_agent.py:909, 1072, 1090]. Le fichier préexistait en chinois ; les ajouts 009-4 sont cohérents avec ce style mais mélangent marqueurs CN et texte FR d'avertissement. *Différé : la conversion globale du fichier en français dépasse le périmètre 009-4, à arbitrer dans le lot i18n (Epic 008).*
- **`verifier_critere_c5` parse la sortie pytest via `token.isdigit()`** [backend/scripts/verifier_qualification_epic_009.py:342-345]. Le premier entier de la sortie n'est pas toujours le `passed_count`. *Différé : le verdict se réduit à `returncode == 0` ; le compteur est informatif.*
- **`verifier_critere_c3` perd un caractère entre f1 et f2** [backend/scripts/verifier_qualification_epic_009.py:203-209]. `texte_source[0:88]` puis `texte_source[89:183]` laisse l'espace à la position 88 hors fragments. *Différé : cosmétique, l'assertion passe.*
- **`verifier_critere_c6` utilise un SHA-256 de chaîne vide comme `input_fingerprint`** [backend/scripts/verifier_qualification_epic_009.py:399]. `e3b0c44298...` est l'empreinte de la chaîne vide. *Différé : valeur de fixture.*
- **`ReportAgent.generate_report` écrit le rapport directement** [backend/app/services/report_agent.py:1821-1823]. `open(full_path, 'w', encoding='utf-8')` contourne `ReportManager` après l'assemblage. *Différé : le code fonctionne, l'isolation concernerait l'Epic 005 si la persistance devenait un point de couplage.*
- **Détection par sous-chaîne `Sources & Provenance`** [backend/app/services/report_agent.py:1818]. Une section titrée « Provenance documentaire » ne déclencherait pas l'injection. *Différé : déduplication de fait peu probable en pratique.*
- **Cas None dans `SimulationActionVerifier`/`build_sources_provenance_section`** (post_content None, source_documents avec None, document_text None, Config.UPLOAD_FOLDER None, action_args non-dict, ref None dans `format_conflicts_for_report`). *Différé : aucun de ces cas n'est atteint en pratique avec les appelants actuels.*
- **`verify_action` construit un `claim_text` non utilisé** [backend/app/services/report_agent.py:1069]. `f"{agent_id} a fait {action_type}"` est stocké dans `original_claim` mais jamais affiché. *Différé : la décision est portée par `agent_id` et `action_type`.*
- **`compute_event_id` sensible à la précision de timestamp** [backend/app/services/simulation_action_verifier.py:184-195]. Un round-trip JSONL qui tronque à la seconde peut fusionner deux événements distincts. *Différé : la couche d'écriture actuelle préserve la précision.*

## Deferred from: revue BMAD de la story 007-1 (2026-10-12)

Revue contradictoire à quatre couches (blind-hunter, edge-case-hunter,
verification-gap, acceptance-auditor) des changements non commités de la story
007-1, sur le code du lot A. Les findings traités sont dans
`story-007-1.md § Revue` ; ceux-ci restent ouverts et sont **réellement** du
travail différé.

- **L'ontologie appliquée est mémorisée par instance de store, donc par requête**
  [`GraphitiGraphStore._applied_ontologies`, `factory.get_graph_store`]. Une
  ontologie posée par `GraphBuilderService` pendant une requête est perdue pour
  l'écrivain suivant : `ZepGraphMemoryUpdater` obtient son propre store et écrit
  donc des nœuds `:Entity` **dans un graphe dont les nœuds ingérés portent le
  label déclaré**. Sur Zep l'ontologie est côté serveur et survit : les deux
  stores divergent donc précisément ici, ce que l'ADR 0014 ne dit pas assez
  explicitement. *Ce qui déclencherait : la story 007-4, qui doit pouvoir relire
  l'ontologie d'un projet à la volée ; elle imposera une persistance réelle
  (`OntologyVersionStore`), pas une mémoire d'instance.*
- **`close()` ne purge pas l'ontologie appliquée** [`GraphitiGraphStore.close`].
  Après fermeture — puis ré-initialisation — `get_applied_ontology` affirme encore
  une ontologie en vigueur. Sans effet aujourd'hui (les classes sont du Python
  pur), mais l'état annoncé dépasse le cycle de vie. *Différé : à traiter avec la
  persistance réelle, ou par un `close()` qui purge.*
- **Un champ d'attribut qui masque un attribut de `BaseModel` ne passe qu'avec un
  simple `UserWarning`** [`ontology_pydantic`, mesuré sur pydantic 2.12.5].
  `model_fields`, `copy`, `dict`, `json`, `schema`, `construct`, `validate` sont
  acceptés par `OntologyToPydantic.from_dict`, et `graphiti_core` lit
  `entity_type.model_fields` en plusieurs endroits. Aucun crash aujourd'hui,
  surface durable en cas de montée de version. *Différé : refus des noms réservés
  de `BaseModel`, quand la liste sera jugée stable.*
- **Un nom de type d'ontologie ne peut pas être un label interne, mais un nom
  d'attribut peut être un mot de `BaseModel`** : voir ci-dessus. Les *noms de
  types* sont refusés (`RESERVED_ONTOLOGY_TYPE_NAMES`).

## Deferred from: relecture BMAD de story-007-1 (groupe A : contrat/stores) (2026-10-12)

Relecture à quatre couches (blind-hunter, edge-case-hunter, verification-gap,
acceptance-auditor) du noyau contrat + implémentations, sur le code post-patches
de la première revue BMAD de la story 007-1. Deux constats réellement ouverts,
complémentaires des 4 déjà inscrits par la première vague (mémoire par instance,
`close()`, attributs `BaseModel`, message « no-op »).

- **Concurrence sur `_applied_ontologies` (Flask `threaded=True`)**
  [`run.py:45`, `graphiti_store.py:247`, `zep_store.py:499`] —
  `Dictionary.__setitem__` n'est pas atomique pendant un rehash, et Flask est
  lancé en mode multi-threads (`app.run(threaded=True)`). `get_graph_store()`
  (`factory.py:71-74`) instancie par appel, donc la portée d'un store est
  étroite ; le risque réel se limite aux services qui conservent `self.store`
  (`GraphBuilderService`, `ZepGraphMemoryUpdater`). *Ce qui déclencherait :
  la story 007-4, qui imposera une persistance réelle (`OntologyVersionStore`)
  et une lecture à la volée plutôt qu'une mémoire d'instance — la question
  de concurrence tombera avec elle. D'ici là, un `threading.Lock` ciblé est
  une parade locale, à arbitrer avec le cycle de vie des services.*

- **Piège sémantique `AppliedOntology.__bool__`** [`base.py:495-498`] —
  `bool(AppliedOntology(entity_type_names=(), edge_type_names=("REGULATES",)))`
  vaut `True`. Un `if store.get_applied_ontology(gid):` sur un graphe où
  seules les relations ont été posées serait True alors qu'aucune entité
  n'est en vigueur. La distinction « `None` vs listes vides » du contrat
  est ténue. *Ce qui déclencherait : la story 007-2 (politique
  `strict_ontology`), qui consommera `AppliedOntology` et stabilisera ses
  call sites ; le contrat `__bool__` sera redéfini à ce moment-là, en
  concertation avec les services qui testent la présence d'ontologie.*

## Deferred from: relecture BMAD de story-007-1 (groupe D : sonde réelle C1) (2026-10-12)

Relecture à quatre couches (blind-hunter, edge-case-hunter,
verification-gap, acceptance-auditor) du script `verifier_ontology_persistence.py`,
la *preuve* de C1. Trois constats réellement ouverts, complémentaires
des 13 déjà inscrits par les quatre vagues précédentes.

- **Les tests `test_le_decompte_exclut_les_labels_generiques` et
  `test_la_mesure_calcule_le_ratio_depuis_le_decompte` sont des mocks
  auto-fulfilling** [`test_verifier_ontology_persistence.py:302-311, 437-446`]
  — les assertions ne portent que sur la valeur de retour du mock, pas
  sur le comportement effectif de la requête Cypher. Une régression du
  filter (par exemple, retirer `label <> 'Entity'` du `WHERE`) ne serait
  pas détectée par pytest. *Ce qui déclencherait : la prochaine
  exécution réelle sous Docker (T10 de la story) qui verrait un ratio
  faussement à 100 % sur un graphe non typé. Parade naturelle : la
  mesure elle-même est la qualification.*

- **Pas de shell script rejouable `verifier-007-1.sh`**
  [`docs/verifier-007-1.sh`] — la convention AGENTS.md §4 fait d'un
  shell script l'entrée canonique rejouable (cf. `verifier-001-2.sh`
  pour la mesure de l'Epic 001). La sonde C1 n'a pas son équivalent ;
  connaître la commande exacte exige de mémoriser l'incantation
  `docker compose run --rm backend uv run python scripts/verifier_ontology_persistence.py …`
  et les conventions (modes `--mock-llm` / réel, `--output` / stdout,
  `--keep-graph`, etc.). *Ce qui déclencherait : un besoin de rejouer
  la mesure régulièrement (par exemple, à chaque release de
  `graphiti-core`, qui peut changer la sémantique de `add_episode`).
  À ce moment-là, poser un `verifier-007-1.sh` qui orchestre la
  commande, capture la sortie et la compare au SHA-256 canonique.*

- **UTF-8 BOM dans un document** [`verifier_ontology_persistence.py:158`]
  — un BOM (3 octets `0xEF 0xBB 0xBF`) en tête de fichier serait inclus
  dans le texte lu, contaminant le SHA-256 et le découpage en
  fragments. *Ce qui déclencherait : le jour où la sonde lira des
  documents utilisateur (au-delà des fixtures de la story). Parade
  simple : `chemin.read_text(encoding="utf-8-sig")`.*

## Deferred from: relecture BMAD de story-007-1 (groupe C : filet LLM + graph_builder + verifier) (2026-10-12)

Relecture à quatre couches (blind-hunter, edge-case-hunter, verification-gap,
acceptance-auditor) du sanitizer `MiroFishLLMClient._filtrer_champs_valides`,
du câblage `GraphBuilderService.set_ontology`, et des scripts
`verifier_provenance_documents.py` / `verifier_integration_graphiti.py`.
Deux constats réellement ouverts, complémentaires des 11 déjà inscrits par
les trois vagues précédentes.

- **`verifier_integration_graphiti.py` change le print sans ajouter
  d'assertion réelle** [`verifier_integration_graphiti.py:265`] — le script
  d'intégration Graphiti + Neo4j local se contente de renommer le message
  « no-op gracieux v1 » → « pose effective, ADR 0014 », sans vérifier
  qu'un `add_episode` post-`set_ontology` produit des nœuds portant les
  labels déclarés. *Ce qui déclencherait : la qualification C1 elle-même
  (exercée par `verifier_ontology_persistence.py`, qui est dans le filet
  pytest post-relecture D) — si la pose C1 échoue, c'est ce script qui
  sert de deuxième rideau manuel. À automatiser le jour où ce script sera
  rejoué régulièrement et où on voudra intégrer son verdict dans la
  qualification.*

- **Couplage caché avec `RESERVED_ONTOLOGY_TYPE_NAMES` sur les verifiers**
  — `verifier_provenance_documents.py` déclare `"DocumentedFact"`,
  `verifier_integration_graphiti.py` déclare `Organization` / `Person` /
  `Topic`. Aucun assert que ces noms ne sont pas dans
  `RESERVED_ONTOLOGY_TYPE_NAMES` ; si la liste grandit (ajout de
  `Organization`, par exemple), les scripts cassent en silence sur une
  vraie exécution Docker. *Ce qui déclencherait : un relèvement de la
  liste réservée qui attrape un nom utilisé par un verifier. Parade
  simple — un `assert "Person" not in RESERVED_ONTOLOGY_TYPE_NAMES` au
  début de chaque verifier suffit — à poser quand le script sera rejoué
  dans le filet pytest.*

## Deferred from: relecture BMAD de story-007-1 (groupe B : OntologyToPydantic) (2026-10-12)

Relecture à quatre couches (blind-hunter, edge-case-hunter, verification-gap,
acceptance-auditor) de la factory `OntologyToPydantic` et du helper
`safe_ontology_attribute_name`, sur le code post-clôture du groupe A. Trois
constats réellement ouverts, complémentaires des 8 déjà inscrits par les deux
vagues précédentes (mémoire par instance, `close()`, attributs `BaseModel`
partiellement traité, message « no-op », concurrence `_applied_ontologies`,
piège `__bool__`).

- **Récursion sur `_reject_reference_cycles`**
  [`ontology_pydantic.py:284-315`] — la détection de cycle est en Python
  récursif (`def visit(name): ...; visit(target)`). Une ontologie avec
  plusieurs centaines de types en chaîne pourrait dépasser la limite de
  récursion (~1000) et lever `RecursionError`. *Ce qui déclencherait : un
  relèvement de `MAX_ONTOLOGY_TYPES` (10 actuellement), ou l'exposition du
  validateur à un corpus où la profondeur est plus grande que le nombre de
  types. Une réécriture en DFS itératif avec pile explicite résoudrait le
  point.*

- **O(n²) sur l'unicité des attributs d'arête**
  [`ontology_pydantic.py:375-379`] — `any(field.name == field_name for field
  in fields)` au lieu d'un `Set[str]` (qui est ce que fait la résolution
  d'entité, ligne 199-203). *Ce qui déclencherait : un relèvement de
  `MAX_ONTOLOGY_ATTRIBUTES` ou une réécriture du path entité ; la
  convergence serait l'occasion d'aligner.*

- **`from_dict` avec uniquement `edge_types` rend `{}`**
  [`ontology_pydantic.py:436-475`] — `from_dict({"entity_types": [],
  "edge_types": [{"name": "RELATED_TO"}]})` retourne un dict vide, et le
  caller doit appeler `edge_types_from_dict` séparément. `architecture.md`
  §4.1 le prévoit (entités et relations sont deux produits distincts) ;
  la docstring de `from_dict` sera clarifiée par le patch #9 du groupe B.
  *Ce qui déclencherait : un caller qui croirait que `from_dict` rend
  *toutes* les classes. Le contrat actuel demande deux appels explicites,
  c'est un choix d'architecture documenté — pas une dette.*

## Deferred from: cadrage de l'epic 007 (2026-10-12)

Deux chantiers que l'[epic 007](../plans/007-ontologie-dynamique/epic-007.md) et
son [PRD](../plans/007-ontologie-dynamique/prd.md) §3.2 et §10 déclarent hors
périmètre. Le hub et le PRD annonçaient tous deux « note consignée dans
`deferred-work.md` » — **elle ne l'était pas**, et la revue d'acceptation de la
story 007-1 l'a relevé. La note manquante est écrite ici plutôt que retirée de
la promesse : le renvoi était juste, c'est la note qui n'existait pas.

- **La boucle auto-évolutive acteur → ontologie → extraction.** Aujourd'hui
  l'ontologie est inférée du corpus et du brief, puis figée ; les entités
  extraites ne la nourrissent pas. Une boucle fermée — où ce que la simulation
  fait émerger enrichit les types et où un type enrichi change l'extraction
  suivante — est **écartée par l'arbitrage du 12 octobre 2026**, qui restreint la
  v2 à « persistance + validation ». La raison est mesurable : une boucle
  ouverte rend la **régénération non déterministe** (NFR-3 exige l'inverse), et
  elle couple deux mécanismes qui doivent rester dissociés pour que le filet
  d'éligibilité de l'Epic 009 reste vérifiable seul. *Ce qui la déclencherait :
  un besoin produit où le typage figé est démontré insuffisant sur un corpus
  réel — pas une intuition.*
- **La migration rétroactive des graphes de l'Epic 006 vers l'ontologie v2.**
  Les graphes migrés portent `:Entity` sans label custom (ADR 0012) et la v2 ne
  les re-type pas : `set_ontology` ne retouche jamais des nœuds déjà écrits
  (ADR 0014, § « Conséquences »). Une passe de typage a posteriori — inférence
  du type d'un nœud `:Entity` déjà présent, puis `SET n:TypeInféré` — est
  techniquement possible et n'a pas été arbitrée sur le fond. *Ce qui la
  déclencherait : la story 007-4, si la régénération doit s'appliquer à un
  projet dont le graphe a été migré ; l'arbitrage se fera alors sur un cas réel
  plutôt que sur une hypothèse.*

## Deferred from: code review de story-007-2 (2026-10-12)

- **D1 — Actualiser contexte et suivi avant clôture.** `AGENTS.md`,
  `docs/STATUS.md` et l’index `epic-007.md` conservent le blocage de 007-2
  malgré le recentrage accepté par l’ADR 0016 et l’implémentation en revue.
  Le routage du skill diffère les changements de fichiers de contexte agent
  et de spécification ; synchroniser leur vue après traitement des correctifs,
  avec les compteurs effectivement vérifiés et l’index ADR à jour.
  Les ADR acceptés restent immuables. Voir `### Review Findings` de la story.

  **Résolu le 13 octobre 2026** lors de la préparation de 007-3 et du commit
  de 007-2 : contexte, suivi humain, hub et index ADR synchronisés ; preuve
  Docker de 1431 collectés / 1428 réussis + 3 ignorés conservée. Les ADR acceptés
  restent inchangés.

## Deferred from: code review of story-007-3.md (2026-10-13)

- **D1 — Mise à jour des suivis et compteurs de tests dans `STATUS.md`, `epic-007.md` et `sprint-status.yaml`** [AGENTS.md ; docs/STATUS.md ; docs/sprint-status.yaml] — Différé conformément au protocole BMad pour les fichiers de contexte agent et spécifications ; les compteurs finaux et synchronisations d'états sont répercutés lors de la clôture définitive de la story.

  **Résolu le 13 octobre 2026** lors de la clôture de la story 007-3 : contexte `AGENTS.md`, suivi humain `docs/STATUS.md`, agrégat `sprint-status.yaml`, hub `epic-007.md` et table des ADRs synchronisés avec le nouveau filet validé à 1459 tests verts sur l'hôte.

## Deferred from: code review of story-007-5.md (2026-10-14)

Revue des modifications de la story 007-5 (`local-first`), le 14 octobre 2026.

- **`backend/app/services/simulation_manager.py:357` — Initialisation anticipée de `applied_ontology_id` dès `create_simulation`.** Lors de l'instanciation initiale de `SimulationState`, `applied_ontology_id` reste à `None` jusqu'à l'exécution de `prepare_simulation`. L'événement E5 spécifie formellement le rattachement de la version d'ontologie lors de la préparation/lancement de la simulation (AC1) ; anticiper cette affectation dès la création initiale n'apporte pas de gain immédiat et ne casse aucun consommateur. *Différé : amélioration architecturale de confort, non bloquante pour l'éligibilité ni la cohérence E5.*

## Deferred from: code review of story-007-6.md (2026-10-14)

Revue des modifications de la story 007-6 (`local-first`), le 14 octobre 2026.

- **`backend/app/services/report_agent.py:2163` — Requête Cypher agrégée pour décompte d'instances sur très grands graphes.** `_get_ontology_instance_counts` rapatrie les nœuds en mémoire Python via `get_all_nodes` pour agréger les labels. Sur des graphes massifs (>100k nœuds), une requête Cypher directe `MATCH (n) RETURN labels(n), count(n)` optimiserait l'empreinte mémoire. *Différé : choix architectural préexistant aligné avec l'abstraction GraphStore, les simulations locales actuelles portant sur des graphes de taille modérée (<1000 nœuds).*

## Deferred from: code review of story-008-2.md (2026-10-16)

Revue contradictoire à quatre couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) de l'intégration et bascule IHM frontend Vue 3.

- **`frontend/tests/i18n.test.js:41-49` — Tests de composants Vue avec montage réel et événements DOM.** L'outillage de test actuel (`node --test`) valide le contrat, les formatteurs et Axios sans environnement DOM/jsdom ni `@vue/test-utils` ; l'ajout d'une stack de test de composants Vue complète relève de la phase de qualification Docker globale (Gate 2).
- **`frontend/src/components/Step3Simulation.vue:605-615` — Grammaire des badges d'action UPVOTE/DOWNVOTE.** `getActionTypeLabel` mappe `UPVOTE_POST`/`DOWNVOTE_POST` vers `ui.upvotedPost` ('Publication approuvée') / `ui.downvotedPost` ('Publication désapprouvée') au lieu de libellés impératifs courts ('VOTE +', 'VOTE -') ; cosmétique, à harmoniser lors de la refonte globale des badges d'actions sociales.
- **`frontend/src/i18n/regionalFormat.js:18-36` — Optimisation par mémoïsation des instances Intl.DateTimeFormat et Intl.NumberFormat.** Chaque appel instancie un nouvel objet `Intl` sans cache ; impact négligeable sur les volumes actuels (<100 éléments), optimisation préventive à traiter si un profiling mémoire le justifie.
- **`frontend/src/i18n/regionalFormat.js:38-42` — Paramètre d'options timezone pour formatLogTimeValue.** `formatLogTimeValue` n'expose pas d'argument `options` pour forcer un fuseau spécifique (ex: UTC) dans les tests, contrairement à `formatDateValue`/`formatTimeValue`.
- **Intégration responsive mobile globale du frontend MiroFish.** L'affichage mobile présente des limites d'empilement vertical et de débordement d'en-tête inhérentes au frontend amont d'origine (conçu strictement desktop-first). L'arbitrage du 16 octobre 2026 confirme que la localisation FR n'a introduit aucune régression et acte le report de l'optimisation responsive mobile dans un chantier/story d'ergonomie dédié.

## Deferred from: code review of story-008-3.md (2026-10-16)

Revue contradictoire à quatre couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) de la génération de personas, simulations et rapports en français (prompts LLM et banc de validation).

- **`backend/scripts/run_parallel_simulation.py:1539` — Injection de consigne linguistique directe dans le moteur camel-oasis.** `set_locale(os.environ.get('MIROFISH_SIMULATION_LOCALE') or self.config.get('locale'))` initialise le thread-local dans les processus de simulation, mais `camel-oasis` est une bibliothèque externe sans interaction directe avec `locale.py` ; l'alignement linguistique des actions des agents repose sur les personas générés (`_add_agent_language_guidance`) et sera mesuré empiriquement lors du banc de qualification sous Docker (T7).

## Deferred from: code review of story-012-2.md (2026-10-17)

Revue contradictoire à quatre couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) des rôles de scénario et statuts de décision d'adoption déterministes.

- **`backend/app/models/cohort_coverage.py:471-477` — Arbitrage de préséance entre ADOPTED_VERIFIED et objections antérieures en cas de conversion tardive.** Si un persona exprime une objection au Round 1 mais souscrit formellement au Round 5, la condition `elif any("refus"...):` priorise actuellement le statut de refus ou d'hésitation sur l'adoption. Maintenu en l'état pour préserver le principe anti-affabulation conservateur (fail-safe contre le sur-optimisme) de l'Epic 012.

## Deferred from: code review of story-013-2.md (2026-10-19)

Revue contradictoire à quatre couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) du mode replay isolé et vérifiable (`replay_frozen`) avec empreinte SHA-256.

- **`backend/app/services/report_agent.py:1131` — Propagation de l'instance LLM/profil de ReportAgent vers ZepToolsService.** `self.zep_tools = zep_tools or ZepToolsService()` ne transmet pas le client LLM dédié ou le profil configuré (`llm_client=self.llm`). `ZepToolsService` initialise donc son propre `LLMClient()` par défaut pour `_synthesize_offline_interviews`. *Différé : préexistant à l'Epic 013, à harmoniser lors des travaux de calibrage et consommation des profils LLM (Story 013-5).*


## Deferred from: code review of story-013-4.md (2026-10-19)

Revue contradictoire à quatre couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) de la télémétrie d'usage, de la mesure des temps et des plafonds budgétaires du `ReportAgent`.

- **`AGENTS.md` — Chiffres de référence désynchronisés.** Le diff met à jour le tableau d'axes et « la tâche du moment » à 1 920 tests, mais §2.2 s'arrête à `post-011-4 : 1719`, §3 annonce « 1431 tests collectés au 12 octobre 2026 » et §11 « 333 passed ». *Différé : correction d'un fichier de contexte agent, hors du correctif automatique de revue.*
- **`docs/plans/013-benchmark-llm-report-replay/story-013-4.md` — Écart de référence du filet.** Le passage de 1 881 à 1 920 tests (+39) pour 40 tests ajoutés indique que la base antérieure réellement collectée valait 1 880. *Différé : dérive de reporting antérieure, sans effet sur le code.*
- **`docs/decisions/` — ADR manquant sur la tarification, le budget et l'accès à l'`usage` brut.** Exigé par le PRD source §12.4 et AGENTS.md §2.3. Les arbitrages sont désormais tranchés (grille alignée sur le PRD source, Fail-Closed réservé aux profils `metered`, `free` validé contre la grille) : il reste à les consigner formellement.
- **`backend/app/models/report_usage.py:311-327` — Télémétrie du cache, des erreurs et des reprises.** Le PRD source §6.3/§6.6 demande de comptabiliser séparément entrée, sortie, cache et raisonnement, et de conserver erreurs et reprises par appel ; `CallUsageRecord` ne porte ni `cached_tokens` ni `finish_reason`. *Différé : hors AC1–AC6 de la story, à traiter avec le banc 013-6.*
- **`backend/app/api/report.py` — `dry_run` (PRD source FR-08) absent au niveau de l'API.** L'estimation sans appel LLM avant démarrage n'est pas exposée par `POST /api/report/generate`. *Différé : la story 013-6 (rédigée le 20 octobre 2026) couvre le `dry_run` **au niveau du banc** (`verifier_benchmark_epic_013.py --dry-run`), pas au niveau de l'API ; l'endpoint HTTP reste à ouvrir, car il supposerait d'exposer l'estimation de coût du catalogue dans l'IHM — ce que la story 013-5 a volontairement laissé hors de son périmètre (le navigateur ne reçoit que des métadonnées de modèle).*
- **`backend/app/utils/llm_client.py:133-137` — Amplification des reprises du SDK au-delà du plafond temporel.** Le client `OpenAI` conserve `max_retries=2` par défaut : un `timeout` égal au temps restant peut être rejoué jusqu'à trois fois. *Différé : borner le plafond mural suppose de modifier la construction du client, d'impact global.*

## Deferred from: code review of story-013-5.md (2026-10-20)

Revue contradictoire à quatre couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) de l'IHM Step 4 : sélecteur de rapport, régénération et comparaison (`11e2fc8..f3cd648`).

- **`docs/STATUS.md`, `AGENTS.md`, `story-013-5.md` — Décompte des clés i18n `step4.*` faux : 74, pas 78.** Mesuré : 50 → 124 clés feuilles sous `step4` dans `locales/{fr,en,zh}.json`. Le « 78 » annoncé trois fois compte les lignes ajoutées au JSON, pas les clés. *Différé : correction d'un fichier de contexte agent et de documents de référence.*
- **`AGENTS.md:558` — Statut de la story 013-5 contradictoire dans le même fichier.** La ligne 558 annonce encore « stories 013-1 à 013-4 `done`, 013-5 `review` » alors que les lignes 34 et 48 la donnent `done`. *Différé : correction d'un fichier de contexte agent.*
- **`docs/plans/013-benchmark-llm-report-replay/story-013-5.md` — La story a sauté l'état `review`.** Le diff bascule `statut: in-progress` → `statut: done` en un seul commit ; `AGENTS.md` §2.8 impose `backlog → in-progress → review → done` et le validateur ne contrôle que l'état courant, jamais l'historique de transition. *Différé : fait d'historique, non rattrapable par un correctif de code ; l'état `review` n'existe dans aucun fichier. La story 013-6 doit passer par `review`.*

## Deferred from: code review of story-013-6.md (2026-10-20)

Revue contradictoire à quatre couches (logique, secrets et honnêteté, qualité des
tests, architecture) du banc de benchmark A/B du `ReportAgent`.

- **La clé de l'aveuglement vit dans le même dossier que le matériel de revue.** Le
  dossier de campagne contient `variante-A.md`, `variante-B.md`,
  `grille-aveugle.md`, `correspondance.json` **et** `mesure-benchmark-013.json` : les
  deux derniers portent le couple variante ↔ profil. C'est ce qu'exige la
  définition de fini de la story 013-6 (« `correspondance.json` dans le **même**
  dossier de campagne »), et la règle de procédure (« la correspondance ne
  s'ouvre qu'après remplissage de la grille ») est désormais écrite dans la
  grille elle-même. *Différé : un paquet de revue exportable (les seuls
  `variante-*.md` et `grille-aveugle.md`) qui serait la seule chose remise à
  l'évaluateur ; cela suppose de trancher ce que le dépôt doit versionner.*
- **La règle de comparabilité est écrite deux fois** — en Python
  (`app/utils/report_benchmark_score.py::evaluate_comparability`) et en JavaScript
  (`frontend/src/utils/reportComparison.js::evaluateComparability`). Les deux
  implémentations ont été alignées cas par cas le 20 octobre 2026 (instantané
  absent, simulation différente, empreinte SHA-256, repli sur l'identifiant
  d'instantané), et la règle est énoncée dans le rapport. Rien n'empêche
  demain une divergence. *Différé : une table de cas partagée, exécutée par les
  deux suites (`pytest` et `node --test`), qui exige des verdicts identiques.*
- **La politique d'admission de l'API n'est reproduite qu'en partie par le banc.**
  `POST /api/report/generate` exige un statut de run terminal, l'absence d'un
  updater de graphe actif, et une revalidation du projet sous
  `graph_lifecycle_lock`. Le banc reproduit le projet `GRAPH_COMPLETED`, la
  concordance des `graph_id`, l'exigence de simulation non vide et le verrou —
  mais pas l'état terminal du run ni l'absence d'updater. *Différé : un service
  d'admission partagé (`app/services/report_generation_admission.py`), appelé par
  l'API et par le banc ; cela sort du périmètre de la story 013-6, qui ne touche
  pas à l'API.*
- **L'empreinte de contenu du graphe ne couvre pas toutes les propriétés.** Le
  garde-fou de cohérence (décision d'ingénierie n° 3) mesure les identifiants, les
  noms et les résumés des nœuds, et les identifiants et faits des arêtes. Un
  attribut enrichi en dehors de ces champs ne serait pas vu. *Différé : le
  `GraphStore` n'expose pas l'objet d'attributs complet dans `get_all_nodes` ;
  le contrat devrait le porter.*

## Deferred from: code review of story-013-6.md (2026-10-20) — suite

- **`backend/tests/test_report_llm_profile.py::test_antigravity_proxy_build_gemini_request_translates_effort` — échec intermittent sous charge de l'hôte.** Le test importe `backend/scripts/antigravity_proxy.py` par un `sys.path.insert(0, .../scripts)`, puis appelle `_build_gemini_request` (fonction pure, sans E/S). Le test est **antérieur à la story 013-6** et n'a pas été touché par son diff. Observé : **2 échecs sur ~10 exécutions complètes** de la suite backend, **0 échec** sur 7 exécutions isolées du fichier et sur 3 suites complètes consécutives (2 067 passantes chacune). Les deux échecs sont survenus sur des exécutions lancées immédiatement après une forte activité Docker sur la même machine. *Différé : l'import par `sys.path` rend le test dépendant de l'état de la machine ; un correctif propre passerait par un import relatif du module (`from scripts import antigravity_proxy`), ou par un `conftest` qui rend `backend/scripts` importable une fois pour toutes. hors périmètre de la story 013-6, qui ne touche pas ce test.*

## Deferred from: campaign benchmark-013-20261020-203040 (2026-10-21) — défauts de pipeline révélés par la revue aveugle

La revue aveugle de la campagne a mis en évidence trois défauts **systématiques**
du `ReportAgent`, présents dans **les deux** variantes et donc indépendants de
l'effort de raisonnement. Ils sont chiffrés et sourcés dans
`docs/plans/013-benchmark-llm-report-replay/benchmark-013-20261020-203040/grille-aveugle.md`.

- **Les citations d'`interview_agents` sont présentées comme des événements
  observés du jeu figé.** L'outil interroge les agents **pendant la rédaction**
  du rapport : ces réponses sont hors du paquet de preuves scellé par
  l'empreinte SHA-256, et hors des 72 h simulées. La variante `high` en compte
  **24 sur 31 citations** de cette origine, étiquetées
  `[Événements simulés réels]`. *Différé : c'est le défaut le plus lourd des
  deux ; il demande un régime de preuve explicite dans le `ReportAgent`
  (typologie distincte pour un entretien de rédaction, et exclusion de ce
  régime du paquet de preuves). Hors périmètre de la story 013-6, qui livre
  l'appareil de mesure et non le correctif de rédaction.*
- **La section « Sources & Provenance » certifie une traçabilité que le registre
  d'affirmations du même rapport nie.** Les deux rapports écrivent « toute
  affirmation qualifiée d'action observée est reliée à un événement horodaté »
  et « aucune divergence intention/action non résolue détectée », alors que
  **0 affirmation** (A : 159 ; B : 178) ne porte d'`evidence_refs` et que
  7 (A) / 8 (B) sont `CONTRADICTED`. *Différé : la section est produite par le
  `ReportAgent` à partir des outils graphe, pas du registre ; elle doit lire le
  registre d'affirmations, ou s'abstenir de certifier.*
- **La fiction de scénario d'un persona non admis fuit dans les affirmations
  « observées ».** Émilie n'est pas admise dans la simulation
  (`eligibility_status: review`, 0 action, `present_no_action`) : les deux
  rapports lui attribuent pourtant un arc, des citations et une section, et
  l'un des deux lui oppose une formatrice. La règle de silence C7 du registre
  ne l'empêche pas — elle n'agit que sur les affirmations extraites, pas sur
  la prose. *Différé : la règle de silence doit remonter jusqu'à la
  rédaction, ou le persona doit être filtré des fiches de profil fournies à
  l'agent.*

## Deferred from: code review of story-014-1.md (2026-10-22, 2e passe)

Revue contradictoire BMAD 4 couches sur le diff `cce6087..HEAD` (code pertinent).

- **Pas d'ADR pour `ProvenanceRegime`** — le type est introduit comme un second axe de provenance distinct d'`InformationOrigin` (ADR 0012/0013 gelés), décision documentée dans la story (décision 1) mais aucun ADR dédié. *Déclencheur : rédaction d'un ADR précisant l'axe, son ordre de priorité Fail-Closed et pourquoi `InformationOrigin` reste gelé.*
- **`report_interviews.json` absent quand aucun entretien** — AC8 parle de « par appel » (par appel d'entretien) ; les consommateurs attendant toujours le fichier pourraient casser. *Déclencheur : décision de l'utilisateur sur le contrat (fichier toujours présent, vide, vs présent seulement si entretien).*

## Deferred from: code review of story-014-2 (2026-10-22)

- `find_projects_by_graph_id` n'a pas de garde propre et ignore silencieusement les projets corrompus sans avertissement dédié. [backend/app/models/project.py:365] — deferred: pre-existing reliance on list_projects, no crash demonstrated.
- Réinitialisation de `_tool_observations`/`_interview_records` plus tôt dans `_generate_report_internal` pour éviter la pollution d'un run précédent après échec partiel. [backend/app/services/report_agent.py:2412] — deferred: low, reset already near top of method.
- `test_verified_count_matches_registry` ne couvre pas le cas `verified > 0` ni le taux de vérification. [backend/tests/test_sources_provenance_honesty.py] — deferred: test coverage gap.
- Aucun test ne vérifie que `_generate_report_internal` transmet bien `claims_registry` à `build_sources_provenance_section`. [backend/app/services/report_agent.py] — deferred: test coverage gap.
- Aucun test ne couvre la bannière `provenance_banner_unknown`. [backend/app/services/report_agent.py] — deferred: test coverage gap.
- Extraction des jetons de régime (`[[PROVENANCE:...]]`) dans les observations et le texte des claims non vérifiée par test. [backend/app/services/report_agent.py] — deferred: test coverage gap.
- Chemin de `get_project` sur fichier JSON valide mais schéma invalide non testé. [backend/app/models/project.py] — deferred: test coverage gap.
- Le commit mélange des préoccupations de la story 014-1 (realname/username, repli replay-mode, jeton de régime, i18n des limitations, bannière unknown). [commit 83a7a9e] — deferred: scope/hygiène, pas un défaut runtime.
- Le chemin de l'index d'attribution dans `run_manifest.json` est un chemin absolu serveur, moins portable pour un tiers. [backend/app/services/simulation_audit_service.py] — deferred: low, la spec demande seulement « le chemin ».

## Deferred from: code review of story-014-4.md (2026-10-24)

Revue BMAD du commit `f7590d4` (« feat(brief): audit de cohérence biographique et filtrage des non-admis (Story 014-4) »).

- **`backend/scripts/verifier_benchmark_epic_013.py:675,734` — absence de filtrage des personas non admis dans le banc de benchmark.** Le script hérité de l'Epic 013 injecte directement le texte brut de `simulation_requirement` dans `generer_variante` sans appliquer `filter_non_admitted_personas_from_text`. Sur un rejeu benchmark ciblant une simulation comme R7, les personas non admis peuvent fuiter dans le prompt de la variante. *Différé : script de banc benchmark issu de l'Epic 013, non modifié par la Story 014-4.*
