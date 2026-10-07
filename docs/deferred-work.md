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
