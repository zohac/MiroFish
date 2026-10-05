---
id: "001-2"
epic: "001"
titre: "Neo4j 5.26 + APOC en local, premier test comportemental du driver forcé"
statut: done
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
      `backend/tests/test_neo4j_serveur_epreuve.py`, 29 tests
- [x] Les 235 tests existants restent verts, et 44 nouveaux les couvrent —
      **279 au total**, contre 235 au départ. Les 2 derniers viennent de la revue
      de code, qui a fermé le trou laissé par deux affirmations que rien ne
      gardait (APOC chez Graphiti, importabilité du script)
- [x] `ruff`, `validate_plans.py` et `pytest` verts ; le compose est **versionné**
- [x] **Le verdict est écrit** dans les notes de complétion : le driver tient
- [x] `docs/STATUS.md` et `docs/sprint-status.yaml` à jour
- [x] **La revue de code est passée et ses 28 correctifs sont appliqués**, chacun
      vérifié — six par mutation sur le vrai fichier, restauré à l'octet initial.
      Les deux sorties de mesure ont été **rejouées** sur le code corrigé

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

> **Note de placement.** Les constats de la revue de code sont écrits ici, et
> non dans une sous-section de `Tâches` : `validate_plans.py` refuse toute case
> ouverte dans `Tâches` pour une story en `review`, et cette section n'est pas
> dans le régime de cases contrôlé. Les constats sont donc lisibles sans casser
> la CI, et la story reste `review` — c'est-à-dire qu'elle attend une décision,
> ce qu'elle mérite.

### Constats de revue

Revue du commit `61fc51a` par quatre couches indépendantes
(blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor), puis
tri et vérification à la source. **31 constats retenus (28 correctifs, 3
différés), 11 rejetés** — dont un pour lequel trois couches sur quatre se
trompaient dans le même sens, et qui est documenté en annexe. La décision
requise (la largeur de `procedures_unrestricted`) a été arbitrée par un humain le
5 octobre 2026 : restreindre aux procédures réellement mesurées. **Le rejeu a
corrigé cette décision dans le geste même** : la première liste écrite
(`apoc.merge.*,apoc.create.*`) laissait `camel` casser au premier
`refresh_schema`, parce qu'`apoc.meta.data` est **sandboxed** et exige lui aussi
`unrestricted`. La liste livrée porte les quatre procédures, et le test les
exige nommément.

Les **28 correctifs sont appliqués** et la suite est à **279 tests**. Ce qu'ils
ont changé, et qu'il faut savoir en les relisant :

- **Un garde-fou mort est devenu un garde-fou.** `test_aucun_secret_en_clair_dans_le_compose`
  ne pouvait pas échouer ; il échoue maintenant sur un mot de passe en clair,
  **vérifié par mutation** sur le compose livré, puis restauré à l'octet initial.
  Cinq autres l'ont été aussi — la valeur de `procedures_unrestricted`,
  l'extraction du mot de passe dans le healthcheck, les deux identifiants de
  conteneur gelés, le refus de mot de passe. Le mutation testing des
  « mutants vérifiés » de la story n'avait pas été fait sur ces cinq.
- **C3 ne repose plus sur une coïncidence.** La sonde des procédures écrit
  désormais sur son propre nœud, `NODE_PROCEDURES`. La phase `relire` ne peut
  plus recréer une partie du graphe qu'elle certifie ; le critère tient par
  propriété, plus par la forme du graphe de vérification.
- **Les transactions sont comparées.** `controler_transactions` rendait `ok=True`
  sans regarder la valeur obtenue — l'affirmation « chaque symbole a son
  assertion » était fausse pour trois des dix-sept contrôles.
- **Deux nouveaux tests** gardent ce qui n'était gardé par aucun : que
  `graphiti-core` n'appelle aucune procédure APOC (lue dans le paquet installé),
  et que le script de vérification **s'importe** avec les symboles qu'il mesure.
- **`docs/STATUS.md` est corrigé** : il annonçait `234 + 42 = 276`. La story
  disait juste, `STATUS.md` se trompait.

> **Les deux sorties de mesure ont été rejouées, et ce rejeu a trouvé un défaut
> de plus — dans le correctif lui-même.** Le raisonnement qui justifiait la liste
> étroite tenait `apoc.meta.data` pour une lecture ordinaire, donc couverte par
> la liste par défaut. C'est faux : APOC marque ses procédures d'introspection
> comme **sandboxed**, et une sandboxed est refusée même quand lire est permis.
> Le premier rejeu, sur `apoc.merge.*,apoc.create.*`, a rendu **16/17** avec
>
> ```
> apoc.meta.data is unavailable because it is sandboxed and has dependencies
> ```
>
> et `code de sortie : 1`. La liste livrée nomme donc les quatre procédures que
> `camel` appelle, `apoc.meta.data` compris, et **le test les exige nommément** —
> c'est lui qui gardera l'erreur si quelqu'un resserre la liste « pour
> simplifier ». Les deux modes sont repassés à **17/17**, et les deux sorties
> versionnées portent désormais la même empreinte de compose et de script.
>
> C'est la démonstration de ce que la story répète depuis le début : *mesurer,
> ne pas présumer*. Le correctif le plus récent est celui qui a le plus vite
> cassé, et seule l'exécution pouvait le dire — aucune relecture ne l'aurait vu,
> parce que la ligne de dérogation était **plausible**.

Ce qui tient : les cinq critères d'acceptation de l'epic pour la 001-2 sont
**prouvés**, le compte de 17 contrôles est **juste** (vérifié contrôle par
contrôle dans la sortie versionnée), et le mutation testing a réellement été fait
— c'est lui qui a produit la démonstration de la sortie « sans APOC ». Ce que la
revue trouve, c'est la **qualité des garde-fous** et la **cohérence des
comptages**, pas la validity du verdict.

#### Correctifs

- [x] [Revue][Correctif] Restreindre `procedures_unrestricted` aux procédures réellement mesurées [docker-compose.neo4j.yml:78] — `apoc.*` débridait tout sans justification. Arbitrage humain le 5 octobre 2026. **La première liste écrite était fausse** : elle omettait `apoc.meta.data`, que le rejeu a fait apparaître comme **sandboxed** — donc refusé malgré sa nature de lecture. La liste livrée nomme les quatre procédures de `camel`, le test les exige nommément, et le commentaire dit pourquoi la liste est étroite.

- [x] [Revue][Correctif] `test_aucun_secret_en_clair_dans_le_compose` : corps de boucle inatteignable [backend/tests/test_neo4j_serveur_epreuve.py:461] — la garde ignore toute ligne contenant `AUTH`, et la branche à vérifier exige `NEO4J_AUTH:`. Le test ne peut pas échouer ; c'est `test_le_mot_de_passe_ne_vient_pas_d_un_env_file:222` qui porte réellement le secret.
- [x] [Revue][Correctif] Six tests « Négatifs » n'exercent aucun code du dépôt [backend/tests/test_neo4j_serveur_epreuve.py:494,506,533 ; backend/tests/test_verifier_protocol.py:339] — la section s'intitule « vérifier que ces tests testent vraiment » et c'est précisément ce qu'elle ne fait pas.
- [x] [Revue][Correctif] `test_le_compose_est_valide_pour_docker_compose` passe au vert au lieu de se déclarer non conduit [backend/tests/test_neo4j_serveur_epreuve.py:639] — deux `return` nus ; le docstring promet l'inverse et cite AGENTS.md §2.2.
- [x] [Revue][Correctif] `test_un_identifiant_fige_echouerait_reellement` **échoue** sur un poste sans Docker [backend/tests/test_verifier_protocol.py:388] — pas de garde `shutil.which` ; `subprocess.run` lève `FileNotFoundError`. Le commentaire « sans Docker, la commande échoue aussi » est faux.
- [x] [Revue][Correctif] Caractères étrangers et docstrings en anglais [backend/tests/test_neo4j_serveur_epreuve.py:163 ; backend/tests/test_verifier_protocol.py:117,347,386] — `꼴oulderait`, `而不是`, « case lacked », « sans resolution ». AGENTS.md §2.10.
- [x] [Revue][Correctif] `test_le_plugin_apoc_est_installe` vérifie la clé, pas la valeur [backend/tests/test_neo4j_serveur_epreuve.py:317] — muté en `"apoc.read.*"`, les 41 tests passent. C'est la conclusion n° 2 de la story qui n'est pas gardée.
- [x] [Revue][Correctif] `test_le_healthcheck_interroge_le_bolt` ne vérifie pas l'extraction du mot de passe [backend/tests/test_neo4j_serveur_epreuve.py:243] — mutée en `-p "$${NEO4J_AUTH}"`, les 41 tests passent et `up --wait` ne devient jamais healthy.
- [x] [Revue][Correctif] `controler_transactions` rend `ok=True` sans comparer la valeur obtenue [backend/scripts/verifier_driver_neo4j.py:451] — le script annonce « chaque symbole a son assertion » ; `valeur` n'est qu'interpolé. `oasis` consomme ce retour dans `range()`.
- [x] [Revue][Correctif] `controler_schema_graphiti` passe à vide si l'extraction de noms échoue [backend/scripts/verifier_driver_neo4j.py:662] — `len(crees) == len(attendus)` vaut `0 == 0`.
- [x] [Revue][Correctif] La phase `relire` écrit dans le graphe qu'elle certifie [backend/scripts/verifier_driver_neo4j.py:993] — `controler_procedures` fait un `MERGE` sur `NODE_ALPHA` avant `relire_graphe`. C3 échoue encore par `NODE_BETA` et l'arête, par coïncidence de forme du graphe, pas par propriété.
- [x] [Revue][Correctif] `une_ligne()` lève `IndexError` sur un message vide, depuis les gestionnaires d'exception [backend/scripts/verifier_driver_neo4j.py:250] — une exception à `str()` vide transforme un diagnostic en traceback, et le rapport n'est jamais rendu.
- [x] [Revue][Correctif] `en_tete` peut rester non liée → `UnboundLocalError` avant tout rapport [backend/scripts/verifier_driver_neo4j.py:1007]
- [x] [Revue][Correctif] `controler_schema_graphiti` supprime des index qu'il n'a pas créés [backend/scripts/verifier_driver_neo4j.py:676] — `avec_avant` est un `SHOW INDEXES` d'après création ; sur le serveur que l'epic 001-5 réutilisera, cela effacerait le schéma du graphe d'épreuve.
- [x] [Revue][Correctif] Le compose affirme comme natives des procédures que le script et la story réfutent [docker-compose.neo4j.yml:57] — `db.idx.fulltext.createNodeIndex` est donné pour une procédure Graphiti, alors que `verifier_driver_neo4j.py:556-559` dit que ce nom appartient à FalkorDB et Kuzu.
- [x] [Revue][Correctif] Comptage des tests faux dans `docs/STATUS.md` [docs/STATUS.md:96,191] — « 234 + 42 » et « 234 avant » donnent 276, pas 277. La story est juste (235 + 42) ; c'est STATUS.md qui est faux.
- [x] [Revue][Correctif] Aucun test ne garde les deux faits sur lesquels la story repose [backend/tests/test_neo4j_serveur_epreuve.py:288] — ni « `graphiti-core` n'a besoin d'aucune procédure APOC » (une montée à 0.31 rendrait six documents faux en silence), ni le couplage du script à `graphiti_core` / `camel` (le seul test est un `py_compile` plus un grep qui passe aussi sur des commentaires).
- [x] [Revue][Correctif] `17/17` compte un écart connu et son dénominateur est conditionnel [backend/scripts/verifier_driver_neo4j.py:192,669] — `CALL db.indexes()` est `ok=True, connu=True`, donc au numérateur ; `index Graphiti tous visibles` n'existe qu'en cas d'échec. Six documents reprennent le chiffre nu.
- [x] [Revue][Correctif] Le protocole fuit son fichier temporaire sur six sorties [docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh:61] — pas de `trap` ; `mktemp` puis `rm` manuel sur trois branches seulement.
- [x] [Revue][Correctif] Les tests écrivent trois scripts dans la racine du dépôt, sur une justification fausse [backend/tests/test_verifier_protocol.py:57,129,357] — le commentaire invoque `dirname $0`, que les extraits n'utilisent pas, et un « arbre propre » que le protocole n'exige pas.
- [x] [Revue][Correctif] Commentaires et littéraux des fichiers opérationnels affirment plus que le mesuré [docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh:10,110,206 ; docker-compose.neo4j.yml:31,66 ; backend/tests/test_neo4j_serveur_epreuve.py:17] — `mesure-001-2.txt` n'existe pas ; `driver 5.28.6` est un littéral alors que la version est lue l. 176 ; le mot de passe **est** passé en argument de `cypher-shell` (l. 100, 174) ; trois dates pour le même relevé (2, 4, 5 octobre) alors que les sorties sont horodatées au 5.
- [x] [Revue][Correctif] Gardes construites sur une forme littérale exacte [backend/tests/test_verifier_protocol.py:215,229] — l'assertion l. 215 est tautologique dès lors que la précédente passe ; l. 229 ne voit que `docker exec "$CONTENEUR"`.
- [x] [Revue][Correctif] `ECART_MAXIMAL` est vacuous et son commentaire ment sur sa valeur [backend/tests/test_neo4j_serveur_epreuve.py:74,373] — un écart de majeures entre `5.x` et `5.x` vaut toujours 0 ; le commentaire dit « Trois » pour `ECART_MAXIMAL = 2`. Le contrôle qui porte vraiment est `test_le_driver_locke_est_celui_de_la_borne_de_l_adrs`.
- [x] [Revue][Correctif] Le parseur de tag est fragile là où le compose évoluera [backend/tests/test_neo4j_serveur_epreuve.py:99,338,402] — `tag_serveur` renvoie la première ligne `image:` du fichier sans se soucier du service ; `tag.split(":", 1)[1]` sans garde.
- [x] [Revue][Correctif] La sortie « sans APOC » n'enregistre pas la surcharge réellement mesurée [docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh:154] — le sha consigné est celui du compose de base, jamais celui du `mktemp` de cinq lignes. C'est le `ProcedureNotFound` consigné qui porte la preuve, pas le fichier.
- [x] [Revue][Correctif] `test_le_verdict_de_la_sortie_versionnee_est_lisible` passerait pour `0/17` [backend/tests/test_neo4j_serveur_epreuve.py:578] — il vérifie la présence de « contrôles passés », pas le résultat.
- [x] [Revue][Correctif] Hygène du dépôt [backend/tests/test_neo4j_serveur_epreuve.py:39 ; story-001-2.md] — `import sys` inutilisé, invisible de `ruff` dont le `select` exclut `F401` ; pas de newline final sur cette story.
- [x] [Revue][Correctif] `docs/deferred-work.md:49` garde un déclencheur devenu faux — « le relevé est à refaire avant la story 001-2 » alors que c'est cette story qui l'a fait, et que la ligne 55 dit correctement « avant la 001-5 ». AGENTS.md §2.8 demande de le barrer et de le dater, pas de le laisser contredire la ligne du dessous.

#### Différés

- [x] [Revue][Différé] La story est passée `backlog → review` en un seul commit, sans `in-progress` [AGENTS.md §2.8] — deferred: le seul remède est une trace dans ce fichier, donc dans la spec sous revue ; l'historique est ce qu'il est.
- [x] [Revue][Différé] ~~`AGENTS.md` §4 ne liste pas quatre des sept livrables~~ — **traité le 5 octobre 2026**, en même temps que la clôture : le protocole, les deux sorties et les deux fichiers de tests sont dans la carte du dépôt.
- [x] [Revue][Différé] ~~`epic-001.md` NFR-5 reste à « 234 »~~ — **traité le 5 octobre 2026** : NFR-5 porte le compte réel, et dit désormais que **le seuil suit les stories** — c'est la règle, pas le chiffre, qui doit tenir.

#### Annexe — rejets

| Constat | Verdict | Réfutation |
|---|---|---|
| `restart: unless-stopped` casserait le `stop` du critère C3 | `false` | `unless-stopped` honore un arrêt explicite : `docker compose stop` marque le conteneur comme arrêté manuellement. |
| `controler_schema_graphiti` aurait un `assert attendus` | `false` | Aucun `assert` de ce type n'existe aux l. 644-662 : le code fait `re.findall`, `set(noms)`, puis `len(crees) == len(attendus)`. Le garde-fou cité n'a jamais été écrit. |
| `test_le_protocole_ne_detruit_pas_le_volume` raterait `down --volumes` | `false` | `down --volumes` détruit bien le volume : le test doit échouer. Le sous-chaîne `-v` y est correct. |
| `SITES` non liée dans `identifiant()` sous `set -u` | `false` | Le `case` (l. 120-136) affecte `SITES` avant tout appel ; le premier est l. 144. |
| Le second `up -d --wait` réintroduirait l'identifiant figé | `false` | Aucune recréation n'a lieu entre l. 139 et l. 155, et `$CONTENEUR` n'est plus utilisé après l. 162. La redondance, elle, est corrigible. |
| `lignes_actives()` casserait sur un commentaire de fin de ligne | `false` | Le compose livré n'en a aucun, et un commentaire en fin de ligne rendrait le tag `None`, ce qui échoue bruyamment. |
| **L'arithmétique de la story sur les tests serait fausse** | `false` | Mesuré : 41 tests dans les deux fichiers + 1 `test_script_compiles[verifier_driver_neo4j.py]` auto-paramétré = 42 ; 277 − 42 = **235**. La story est juste, `STATUS.md` est faux. Trois couches sur quatre se sont ici trompées dans le même sens. |
| Les deux tests de sortie ne prouveraient rien | `low` | Ils ne pinnent pas la propriété, mais les artefacts la portent : `mesure-001-2-sans-apoc.txt:63` porte le `ProcedureNotFound`, et les deux identifiants de conteneur diffèrent (`1021a39…` / `8a3dbda…`). |
| `test_un_mot_de_passe_absent_est_refuse` passerait pour la mauvaise raison | `low` | Le code de sortie vient bien du `set -u` sur `$SANS_APOC` non lié, pas du `exit 1` — mais les assertions de sortie portent réellement le refus. |
| `17/17` inclut un contrôle qui constate une absence | `low` | Vrai, mais la sortie le déclare sur sa propre ligne ; c'est la reprise du chiffre nu dans six documents qui pose question. |
| Les échecs d'authentification volontaires pollueraient le serveur | `false` | Un nœud unique sans mécanisme de verrouillage n'a rien à déclencher ; le commentaire du script le dit. |

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
| 29 tests sur le serveur déclaré | `backend/tests/test_neo4j_serveur_epreuve.py` |
| 14 tests sur le protocole lui-même | `backend/tests/test_verifier_protocol.py` |

Les deux versions mesurées : **driver `neo4j 5.28.6`**, lockée par
`backend/uv.lock` ; **serveur `Neo4j 5.26.31` `community`**, lue de
`CALL dbms.components()` et non déduite du tag.

Les deux sorties versionnées ont été **rejouées le 5 octobre 2026** sur le code
corrigé par la revue, et portent les mêmes empreintes de contenu — c'est ce qui
permet de dire qu'elles décrivent la même configuration :

| Empreinte | Valeur |
|---|---|
| `docker-compose.neo4j.yml` | `b00ec4eedd02a265…` |
| `backend/scripts/verifier_driver_neo4j.py` | `0f293f36378bc6a5…` |
| surcharge « sans APOC » | `ac897c512125c217…` |

Un `git rev-parse HEAD` n'aurait pas suffi : au premier passage il pointait sur un
commit qui ne contenait pas encore le compose. Une empreinte de **contenu**, elle,
identifie exactement le fichier mesuré et reste vraie après le commit.

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
défaut.** Le compose porte `NEO4J_dbms_security_procedures_unrestricted`, sans
quoi `apoc.merge.node` échoue en `ClientError` **alors que le plugin est
installé** — et `camel` dit dans ce cas « le plugin n'est pas installé », donc
l'erreur est fausse. C'est le pire état des deux : le message accuse un
diagnostic, et le remède qu'il suggère ne change rien. Le test
`test_le_plugin_apoc_est_installe` garde la valeur de la dérogation, pas
seulement sa clé.

**2 bis. Une procédure d'introspection est *sandboxed*, et se débride comme une
écriture.** Trouvé par la revue, puis corrigé par le rejeu — le 5 octobre 2026,
après l'arbitrage qui avait restreint la dérogation à `apoc.merge.*` et
`apoc.create.*`. `camel` appelle aussi `apoc.meta.data` au `__init__` de son
`Neo4jGraph`, et l'intuition disait qu'une **lecture** n'avait pas besoin d'être
débridée. Faux : APOC marque `apoc.meta.data` comme **sandboxed**, et une
sandboxed est refusée même quand lire est permis. Le rejeu a rendu **16/17** :

```
apoc.meta.data is unavailable because it is sandboxed and has dependencies
```

La liste livrée nomme donc les **quatre** procédures de `camel` —
`apoc.meta.data`, `apoc.merge.*`, `apoc.create.*` — et le test les exige
nommément. C'est la deuxième fois que la story apprend la même leçon : la
question « APOC est-il nécessaire ? » ne se répond pas par catégorie (écriture
vs lecture), seulement par exécution. La ligne était **plausible**, et aucune
relecture ne l'aurait vue.

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
