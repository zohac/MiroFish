---
id: "001-2"
epic: "001"
titre: "Neo4j 5.26 + APOC en local, premier test comportemental du driver forcé"
statut: backlog
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

- [ ] `docker compose up` démarre un Neo4j **joignable**, et le healthcheck passe
      au vert sans intervention manuelle
- [ ] **Le premier test comportemental du driver forcé** : une écriture puis une
      relecture passent par `neo4j 5.28.6` sous le `pin camel-oasis`, sans
      workaround
- [ ] Un nœud écrit **survit à l'arrêt puis au redémarrage** du conteneur — le
      volume nommé fait son travail, et c'est la moitié de C3 qui ne dépend pas
      encore de l'extraction
- [ ] Les quatre symboles de la surface relevée par l'ADR 0011 sont **exercés à
      l'exécution** : `GraphDatabase.driver()`, une transaction gérée,
      `Query`, et les quatre types d'exceptions
- [ ] La hiérarchie d'exceptions est **éprouvée**, pas seulement importée : on
      provoque un `ClientError` réel et on vérifie qu'il remonte comme attendu.
      C'est ce que l'ADR 0011 désigne comme « ce qui a le plus de chances de
      bouger entre deux versions majeures »
- [ ] La version du **serveur** et celle du **driver** sont consignées, et leur
      écart est expliqué — pas laissé dans un `compose.yaml`
- [ ] Un test garde que le serveur supporté est compatible avec le driver locké,
      donc qu'un `neo4j` mis à jour dans le compose ne casse pas en silence
- [ ] Les 235 tests existants restent verts, et **au moins un nouveau** couvre
      ce que la story produit
- [ ] `ruff`, `validate_plans.py` et `pytest` verts ; le compose est **versionné**
- [ ] **Le verdict est écrit** dans les notes de complétion : le driver tient, ou
      il ne tient pas. Dans le second cas, l'ADR à écrire est nommé
- [ ] `docs/STATUS.md` et `docs/sprint-status.yaml` à jour

## Tâches

- [ ] 1. Écrire `docker-compose.neo4j.yml` — **séparé** du compose de
      l'application, avec un volume nommé et les ports exposés explicitement
- [ ] 2. Choisir et **figer** le tag du serveur (voir les notes), avec un
      healthcheck qui teste l Bolt et pas seulement le processus
- [ ] 3. `docker compose -f docker-compose.neo4j.yml up -d`, puis relever la
      version **effective** du serveur et la consigner
- [ ] 4. Écrire `backend/scripts/verifier_driver_neo4j.py` — le test
      comportemental : écriture, relecture, transaction, `Query`, exceptions
- [ ] 5. Exercer chaque symbole de la surface de l'ADR 0011, et consigner ce qui
      tient ou non
- [ ] 6. Arrêter puis redémarrer le conteneur, relire : le nœud est-il là ?
- [ ] 7. Vérifier qu'**APOC est ou non nécessaire** à Graphiti 0.30.2, et dire
      le résultat plutôt que de le supposer (voir les notes)
- [ ] 8. Ajouter le test qui garde la compatibilité serveur / driver locké
- [ ] 9. Rédiger le verdict, mettre à jour `STATUS.md` et `sprint-status.yaml`

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

_À remplir à la fin : ce qui a divergé du plan, et pourquoi._

## Risques

| Risque | Parade |
|---|---|
| Le driver 5.28.6 casse à l'exécution contre un serveur 5.26.31, et l'ADR 0010 tombe | c'est **le** but de la story : on le découvre ici, sur un périmètre minimal, plutôt qu'à la 001-5 au milieu d'une extraction |
| `camel-oasis` casse sur son propre chemin d'écriture, pas le nôtre | distinction écrite dans les notes de développement ; si ça arrive, l'erreur n'est pas dans l'override |
| Le tag `neo4j:5.26` glisse et l'épreuve devient irreproductible | patch figé (`5.26.31-community`), version effective relevée et consignée dans la sortie |
| APOC inutile, téléchargé à chaque `compose up` sans raison | mesuré en tâche 7, résultat consigné — pas présumé |
| Un secret Neo4j finit versionné | mot de passe dans `.env` via `env_file`, jamais en clair dans le compose ; vérifié avant le commit (AGENTS.md §2.4) |
| Le test comportemental se dégrade en « ça démarre, c'est tout » | la surface de l'ADR 0011 est **exercée**, pas importée ; chaque symbole a son assertion |
| La story grossit et empiète sur la 001-5 | son périmètre est écrit noir sur blanc dans les notes : une connexion, une écriture, une relecture, un redémarrage |