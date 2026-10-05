---
id: "001-2"
epic: "001"
titre: "Neo4j 5.26 + APOC en local, premier test comportemental du driver forcé"
statut: review
auteur: agent
format: "2"
---

# Story 001-2 — Neo4j 5.26 en local, avec volumes nommés

## Pourquoi cette story

L'`override-dependencies` est posé depuis la 001-1b, et il a été **vérifié de
tout façon sauf une** : le lock résout, les imports passent dans l'ordre, les
tests sont verts. Personne n'a ouvert une connexion. Un override qui produit un
lock valide et un runtime cassé est le pire des deux mondes — et c'est
précisément ce que l'ADR 0010 assume comme risque.

Cette story est ce test. Elle ne mesure pas l'extraction, elle ne touche pas au
LLM, elle ne branche pas d'embedder. Elle répond à **une seule** question :

> `neo4j 5.28.6`, forcé contre le pin `==5.23.0` que `camel-oasis` déclare,
> tient-il contact avec un vrai serveur ?

Si la réponse est non, l'ADR 0010 est **supersédé** — pas réécrit — et on bascule
sur un second environnement. C'est le seul arbitrage de tout l'epic 001 qui
puisse nous faire reculer, donc c'est le premier à lever.

## Définition de prêt

- [x] Critères Given/When/Then écrits et mesurables
- [x] Aucune dépendance externe non résolue — le driver est locké (`5.28.6`), le
      plan de la story est fixé ci-dessous
- [x] Stratégie de test identifiée
- [x] Documents à consulter lus — [`epic-001.md`](epic-001.md),
      [`architecture.md`](architecture.md) §4,
      [ADR 0010](../../decisions/0010-override-driver-neo4j.md),
      [ADR 0011](../../decisions/0011-inventaire-driver-et-format-de-story.md),
      [`story-001-1b.md`](story-001-1b.md),
      [`docs/STATUS.md`](../../STATUS.md), `backend/pyproject.toml`

## Définition de fini

- [x] `docker compose up` démarre un Neo4j **joignable**, et le healthcheck passe
      au vert sans intervention manuelle — *mesuré* : `Healthy` dès le premier
      `up -d --wait`, sans aucune commande manuelle
- [x] **Le premier test comportemental du driver forcé** : une écriture puis une
      relecture passent par `neo4j 5.28.6` sous le `pin camel-oasis`, sans
      workaround — *mesuré* : 17/17 contrôles, deux fois
- [x] Un nœud écrit **survit à l'arrêt puis au redémarrage** du conteneur — le
      volume nommé fait son travail — *mesuré* : `valid_at` relu à l'identique
      après `stop` puis `start`
- [x] Les quatre symboles de la surface relevée par l'ADR 0011 sont **exercés à
      l'exécution** : `GraphDatabase.driver()`, une transaction gérée,
      `Query`, et les quatre types d'exceptions
- [x] La hiérarchie d'exceptions est **éprouvée**, pas seulement importée — et
      **elle n'est pas celle qu'on supposait** : `Neo4jError` et `DriverError`
      sont sœurs sous `GqlError`, pas une chaîne. Voir les notes de complétion.
- [x] La version du **serveur** et celle du **driver** sont consignées, et leur
      écart est expliqué — `5.26.31` / `5.28.6`, dans le compose **et** dans les
      deux sorties versionnées
- [x] Un test garde que le serveur supporté est compatible avec le driver locké —
      `backend/tests/test_neo4j_serveur_epreuve.py`, 27 tests
- [x] Les 235 tests existants restent verts, et 42 nouveaux les couvrent —
      **277 au total**, contre 235 au départ
- [x] `ruff`, `validate_plans.py` et `pytest` verts ; le compose est **versionné**
- [x] **Le verdict est écrit** dans les notes de complétion : le driver tient
- [x] `docs/STATUS.md` et `docs/sprint-status.yaml` à jour

## Tâches

- [x] 1. Écrire `docker-compose.neo4j.yml` — **séparé** du compose de
      l'application, avec un volume nommé et les ports exposés explicitement
- [x] 2. Choisir et **figer** le tag du serveur : `neo4j:5.26.31-community`, avec
      un healthcheck qui teste le Bolt — mesuré, et deux tests gardent le tag
- [x] 3. `docker compose -f docker-compose.neo4j.yml up -d`, puis relever la
      version **effective** du serveur et la consigner — `CALL dbms.components()`
      renvoie `5.26.31` `community`, pas le tag deviné
- [x] 4. Écrire `backend/scripts/verifier_driver_neo4j.py` — le test
      comportemental : écriture, relecture, transaction, `Query`, exceptions
- [x] 5. Exercer chaque symbole de la surface de l'ADR 0011, et consigner ce qui
      tient ou non — tout tient, et la hiérarchie a une forme inattendue
- [x] 6. Arrêter puis redémarrer le conteneur, relire : le nœud est-il là ? — oui,
      arête et `valid_at` compris
- [x] 7. Vérifier qu'**APOC est ou non nécessaire** — mesuré dans les deux sens :
      Graphiti s'en passe, `camel-oasis` en a besoin. La question avait une seule
      réponse dans les notes de développement ; elle en a deux.
- [x] 8. Ajouter le test qui garde la compatibilité serveur / driver locké — 27
      tests, mutants vérifiés
- [x] 9. Rédiger le verdict, mettre à jour `STATUS.md` et `sprint-status.yaml`

## Notes de développement

**Ce que cette story ne doit pas faire.** Elle ne doit pas écrire un épisode, ni
appeler le LLM, ni toucher à l'embedder. Si le script de mesure touche l'un des
trois, on ne saura plus ce qui a cassé. Le périmètre se tient à : une connexion,
une écriture, une relecture, un redémarrage. C'est petit exprès — c'est la
première fois qu'on ouvre une connexion sous cet override, et on ne veut pas
deux sources d'échec possibles.

**Le serveur est 5.26, figé sur un patch — et c'est un choix.** Trois
considérations, dans l'ordre :

1. **5.26 est le plancher de `graphiti-core`**, donc 5.26 est la version
   minimale que la bibliothèque déclare supporter. C'est aussi une **LTS**, et
   c'est le choix de `architecture.md` §4.
2. **Le tag `neo4j:5.26` est flottant, et il a bougé deux jours avant cette
   story** — vérifié sur Docker Hub, où `5.26` pointe aujourd'hui sur `5.26.31`.
   Un tag flottant dans un compose versionné signifie qu'un `docker compose up`
   six mois après peut démarrer autre chose que ce qu'on a mesuré. **On fige donc
   le patch.** C'est le même raisonnement que la version résolue de l'override
   consignée dans `pyproject.toml` (ADR 0011).
3. **Édition `community`, pas l'édition par défaut.** Le tag `neo4j:<version>`
   sans suffixe est l'édition Enterprise, qui réclame un accord de licence. Pour
   une épreuve locale à 0 € (NFR-1), c'est hors de question. Le tag retenu est
   donc **`neo4j:5.26.31-community`**.

**L'écart driver / serveur n'est pas un détail.** Le driver est en `5.28.6`, le
serveur en `5.26.31`. C'est délibéré : 5.26 est le plancher que déclare
`graphiti-core`, et un même tag évite d'avoir à justifier d'un 5.x plus récent.
La **compatibilité** de cet écart n'est pas présumée — elle est l'un des objets
de la story, vérifiée par une connexion réelle. Ce qui doit être écrit ici, c'est
que la 001-2 a été mesurée avec cet écart : le jour où quelqu'un aligne les deux
« pour simplifier », il faut savoir ce qui change. Un test le garde.

**APOC : à vérifier, pas à supposer.** `architecture.md` §4 prescrit
`NEO4J_PLUGINS: '["apoc"]'`, et c'est recopié depuis le fork de référence. Or
`graphiti-core 0.30.2` n'appelle **aucune procédure APOC** : ses requêtes
utilisent `db.create.setNodeVectorProperty`, `db.idx.fulltext.createNodeIndex` et
`db.index.fulltext.queryNodes` — des procédures **natives** de Neo4j 5. C'est un
point à **mesurer** (tâche 7), pas à présumer dans les deux sens : si APOC est
inutile, le plugin est inutile et il coûte un téléchargement à chaque
`compose up` ; s'il est nécessaire, on le découvre maintenant et non à la 001-5.

**`Graphiti()` ne bloque pas sur l'embedder.** Vérifié dans la bibliothèque
installée : `graphiti.py:223` construit un `OpenAIEmbedder()` **par défaut** si
aucun embedder n'est passé. Sans clé OpenAI, cet embedder ne sert tant qu'on
n'écrit aucun épisode — et cette story n'en écrit pas. **C'est pourquoi la
001-4 n'est pas un bloquant ici**, alors qu'elle l'est pour la 001-5. Il ne
faudrait pas s'étonner de cette asymétrie : elle est dans la bibliothèque, pas
dans notre organisation.

**Ce que le script de vérification doit faire, et comment.** Il doit **exercer**
la surface de l'ADR 0011, pas l'importer. Une surface importée qui n'est jamais
appelée ne prouve rien — l'ADR 0011 le dit lui-même : « `neo4j.Version` n'est
référencé nulle part », et c'est précisément le genre d'erreur qu'un relevé de
surface laisse passer. Donc : `GraphDatabase.driver()` pour ouvrir,
une transaction gérée pour écrire, `Query` pour une requête paramétrée, et une
requête volontairement invalide pour provoquer un `ClientError` réel.

Le script doit **sortir non zéro** en cas d'échec, et son.sortie doit être
versionnée avec la date et les deux versions — serveur et driver. Sinon la
preuve ne sera pas rejouable, et une preuve non rejouable ne vaut pas une preuve
(NFR-3). On s'appuie sur le même principe que
[`mesurer-001-1.sh`](mesurer-001-1.sh) : un protocole, une sortie capturée,
l'arbre rendu à son état initial.

**Le compose ne touche pas à l'application.** `docker-compose.yml` pointe
l'image amont et ne contient pas notre code (AGENTS.md §2.9). Ajouter un service
`neo4j` dedans ferait dépendre le test comportemental d'un environnement qui
n'est pas le nôtre. D'où un fichier séparé, `docker-compose.neo4j.yml`, qui ne
sert qu'à l'épreuve et que l'epic 005 absorbera plus proprement quand
l'environnement de référence existera.

**Données de test.** On écrit un graphe de deux nœuds et une arête, avec des
noms reconnaissables (`mirofish-verification-…`) pour pouvoir les retrouver et
les nettoyer. Pas de document réel ici : le document AN n° 2506 appartient à la
001-5, et mélanger les deux ferait échouer la 001-2 pour une raison qui la
regarde pas.

**Ce que cette story ne prouve toujours pas.** Elle ne prouve pas que
l'extraction fonctionne — c'est le PRD et la 001-5. Elle ne prouve pas non plus
que l'override est *bon* pour `camel-oasis` en usage réel : `camel-oasis`
utilise le driver pour son **stockage graphe interne**, et cette story n'exerce
que le nôtre. Si `oasis` casse sur son propre chemin d'écriture, il faudra
l'exercer aussi — mais ce n'est pas le même test, et le confondre ferait
attribuer à l'override un problème qui serait ailleurs.

## Revue

Suivis éventuels : _aucun pour l'instant._

## Notes de complétion

### Verdict — le driver forcé tient

> **`neo4j 5.28.6`, forcé par l'`override-dependencies` de l'ADR 0010 contre le
> pin `==5.23.0` de `camel-oasis`, tient contact avec un vrai serveur.**
> Écriture, relecture après arrêt et redémarrage, surface de l'ADR 0011
> entière, hiérarchie d'exceptions comprise : **17/17 contrôles passés**, deux
> fois, sur deux configurations de serveur différentes.
>
> **L'ADR 0010 n'est pas supersédé.** Il reste valide, et sa règle 2 — « un
> `override` est une promesse faite au résolveur, pas au projet » — vient
> d'être confirmée par la mesure plutôt que par un relevé d'API.

Ce que la story a produit :

| Livrable | Où |
|---|---|
| Compose d'épreuve, séparé, tag figé, healthcheck Bolt | `docker-compose.neo4j.yml` |
| Script de vérification, 17 contrôles, 3 phases | `backend/scripts/verifier_driver_neo4j.py` |
| Protocole rejouable, deux modes | [`verifier-001-2.sh`](verifier-001-2.sh) |
| Sortie du compose livré | [`mesure-001-2-compose.txt`](mesure-001-2-compose.txt) |
| Sortie sans le plugin APOC | [`mesure-001-2-sans-apoc.txt`](mesure-001-2-sans-apoc.txt) |
| 27 tests sur le serveur déclaré | `backend/tests/test_neo4j_serveur_epreuve.py` |
| 14 tests sur le protocole lui-même | `backend/tests/test_verifier_protocol.py` |

Les deux versions mesurées : **driver `neo4j 5.28.6`**, lockée par
`backend/uv.lock` ; **serveur `Neo4j 5.26.31` `community`**, lue de
`CALL dbms.components()` et non déduite du tag.

### Ce qui a divergé du plan, et pourquoi

**1. La question « APOC est-il nécessaire ? » avait une seule réponse ; elle en
a deux.** Les notes de développement annonçaient le résultat, et annonçaient le
mauvais : si APOC était inutile, le plugin serait inutile. **Mesuré, c'est
inversé.**

- Sur le serveur **sans** plugin, tout ce que `graphiti-core` réclame passe :
  `db.create.setNodeVectorProperty`, `db.index.fulltext.queryNodes`, et les
  31 requêtes d'indexation que `Graphiti.__init__` lance en tâche de fond.
  Zéro occurrence de `apoc` dans `graphiti-core==0.30.2`, mesuré sur le paquet.
  **Graphiti n'a pas besoin d'APOC.**
- `camel-oasis` en a besoin : `Neo4jGraph.__init__` appelle `refresh_schema()`,
  qui exécute `CALL apoc.meta.data()` — `neo4j_graph.py:28`, `:120`, `:128` — et
  `add_nodes_from_df` utilise `apoc.merge.node`, `apoc.merge.relationship` et
  `apoc.create.addLabels` (`:470`, `:500`). Sans le plugin, le chemin Neo4j de
  `camel` casse sur un `ClientError` dès le premier `refresh_schema`, avec un
  message qui accuse l'utilisateur d'une installation manquante.

Le plugin **reste donc dans le compose**, mais pour une raison que
`architecture.md` §4 ne donnait pas : ce document le prescrit « repris du fork
de référence », et le fork avait APOC parce que `camel` en a besoin. La mesure
donne la raison, et `architecture.md` §4 mérite d'être corrigé en ce sens.

C'est aussi ce qui a justifié deux exécutions du protocole au lieu d'une. Une
seule ne pouvait pas distinguer « aucun des deux n'en a besoin » de « seul
Graphiti n'en a pas besoin » — c'est-à-dire elle ne pouvait pas soutenir
l'affirmation, seulement la constante. Deux mesures opposées, deux conclusions
opposées, et un plugin installé pour la bonne raison.

**2. `apoc.merge.*` est une procédure d'écriture, et elle est refusée par
défaut.** Le compose porte `NEO4J_dbms_security_procedures_unrestricted:
"apoc.*"`. Sans elle, `apoc.merge.node` échoue en `ClientError` **alors que le
plugin est installé** — et `camel` dit dans ce cas « le plugin n'est pas
installé », donc l'erreur est fausse. C'est le pire état des deux : le message
accuse un diagnostic, et le remède qu'il suggère ne change rien. Le test
`test_le_plugin_apoc_est_installe` garde les deux lignes ensemble.

**3. La hiérarchie d'exceptions n'est pas une chaîne, et ce n'est pas une dérive.**
Le contrôle l'a d'abord **échoué**, et le test avait tort : il affirmait
`Neo4jError ⊂ DriverError`. Mesuré sur `neo4j 5.28.6` :

```
Neo4jError         ⊂ GqlError
DriverError        ⊂ GqlError
ClientError        ⊂ Neo4jError
CypherSyntaxError  ⊂ ClientError
AuthError          ⊂ ClientError
ServiceUnavailable ⊂ DriverError
```

`Neo4jError` et `DriverError` sont des branches **sœurs** sous `GqlError` — d'où
son nom. Ce n'est donc pas une dérive 5.23 → 5.28 : c'est une structure qui n'a
jamais été celle qu'on imaginait, et qu'aucune résolution de dépendances ne
pouvait montrer. L'ADR 0011 reste valable sur sa surface ; il ne doit pas être
lu comme une hiérarchie. Ce que `camel` attrape reste juste — `ClientError`
couvre bien `AuthError`, `CypherSyntaxError` et `ConstraintError` — mais un
`except DriverError` n'attraperait pas `ClientError`, et c'est ce que l'ADR 0010
supposait implicitement.

**4. `graphiti-core` appelle une procédure qui n'existe pas sur un serveur 5.x.**
`CALL db.indexes()` — `graph_ops.py:73`, `neo4j_driver.py:198` — répond
`ProcedureNotFound` sur 5.26.31. C'est `delete_all_indexes`, atteint seulement
par `build_indices_and_constraints(delete_existing=True)`, donc **hors du chemin
d'écriture d'épisodes** : le chemin d'indexation du démarrage passe
intégrellement. Le rapport le classe « écart connu », pas échec, parce que les
confondre attribuerait au driver un défaut qui n'est pas le sien. La 001-5
butera dessus si elle veut repartir de zéro par cette voie ; c'est consigné dans
[`deferred-work.md`](../../deferred-work.md).

Un relevé par `grep 'CALL db\.'` sur le paquet aurait présenté
`db.idx.fulltext.createNodeIndex` comme une procédure du chemin Neo4j — elle
appartient à **FalkorDB** et à **Kuzu**. Le script tire donc ses requêtes de
`graphiti_core.graph_queries` avec le fournisseur Neo4j, au lieu de les
recommencer.

**5. Un test a échoué trois fois, et chaque fois c'était le script.** `Neo4jError
⊂ DriverError` (le test avait tort), un `YIELD name` sur `apoc.meta.data()` qui
n'a pas cette sortie, un étiquette d'équipe contenant un tiret. Les trois
venaient de la même cause : le script **supposait** au lieu de mesurer, ou
mesurait autre chose que ce qu'il croyait. La correction n'a jamais été
d'assouplir le test.

**6. Le protocole a buté sur son propre bug, et le temps d'attente l'a masqué.**
`CONTENEUR` était résolu une fois au début ; le mode « sans APOC » change
l'environnement, ce qui **recrée** le conteneur et change son ID. Le protocole a
attendu 180 secondes un Bolt joignable sur un conteneur disparu — alors que le
conteneur recréé était `Healthy` trois secondes plus tôt. Corrigé par
`identifiant()`, appelé à chaque fois ; `test_l_identifiant_du_conteneur_est_resolu_a_chaque_appel`
garde le cas.

**7. Les tests d'intégration ne sont pas en CI, et c'est un choix assumé.**
`backend/tests/test_neo4j_serveur_epreuve.py` ne démarre aucun conteneur : il
lit le compose livré et les sorties versionnées. Le test comportemental reste
un protocole à lancer à la main, dont les deux sorties sont versionnées. Ajouter
un service Neo4j à la CI pour 17 contrôles coûtait plus, à chaque commit, que ce
qu'il prouvait — et la CI n'a pas de service Neo4j.

**8. Le compose `docker-compose.yml` n'a pas été touché.** Comme prévu dans les
notes : il pointe l'image amont. Un test échoue s'il mentionne `neo4j`.

### Ce que cette story a trouvé en passant — et qui ne la concerne pas

L'`override` borne le **driver**, pas le serveur : rien dans les dépendances
n'aligne `5.28.6` sur `5.26.31`. Le test garde l'écart, mais il lit le tag — une
image reconstruite **sous le même tag** passerait. C'est un point pour l'epic
005, qui construira l'image ; il est dans [`deferred-work.md`](../../deferred-work.md).

## Risques

| Risque | Parade |
|---|---|
| Le driver 5.28.6 casse à l'exécution contre un serveur 5.26.31, et l'ADR 0010 tombe | c'est **le** but de la story : on le découvre ici, sur un périmètre minimal, plutôt qu'à la 001-5 au milieu d'une extraction |
| `camel-oasis` casse sur son propre chemin d'écriture, pas le nôtre | distinction écrite dans les notes de développement ; si ça arrive, l'erreur n'est pas dans l'override |
| Le tag `neo4j:5.26` glisse et l'épreuve devient irreproductible | patch figé (`5.26.31-community`), version effective relevée et consignée dans la sortie |
| APOC inutile, téléchargé à chaque `compose up` sans raison | mesuré en tâche 7, résultat consigné — pas présumé |
| Un secret Neo4j finit versionné | interpolation `${NEO4J_PASSWORD}` depuis le `.env`, jamais en clair dans le compose ; un test échoue sur un `NEO4J_AUTH` littéral, et pas de `env_file` non plus — il ferait entrer `LLM_API_KEY` dans un conteneur Neo4j (AGENTS.md §2.4) |
| Le test comportemental se dégrade en « ça démarre, c'est tout » | la surface de l'ADR 0011 est **exercée**, pas importée ; chaque symbole a son assertion |
| La story grossit et empiète sur la 001-5 | son périmètre est écrit noir sur blanc dans les notes : une connexion, une écriture, une relecture, un redémarrage |