---
id: "001-1b"
epic: "001"
titre: "Poser l'override-dependencies du driver neo4j"
statut: review
auteur: agent
format: "2"
---

# Story 001-1b — Poser l'`override-dependencies` du driver `neo4j`

## Pourquoi cette story

L'ADR 0010 **tranche** : on force le driver par
`[tool.uv] override-dependencies`, et on n'introduit pas de second
environnement. L'ADR 0011 le **précise** : la surface réelle du driver, et la
version que la borne a résolue. Ni l'un ni l'autre n'applique quoi que ce soit —
`graphiti-core` et l'override sont absents de `backend/pyproject.toml`.

Cette story est le geste. Une ligne de déclaration, un lock régénéré, et la
démonstration que le filet tient — puis, et c'est le plus dur, que le protocole
de mesure de la 001-1 **reste rejouable** sur l'arbre qui en résulte.

Ce n'est pas une story de risque : tout est mesuré et tranché. C'est une story
de **dette** — elle pose une promesse au résolveur, et une promesse non gardée
est pire qu'un conflit assumé.

## Définition de prêt

- [x] Critères Given/When/Then écrits et mesurables
- [x] Aucune dépendance externe non résolue
- [x] Stratégie de test identifiée
- [x] Documents à consulter lus — [`epic-001.md`](../epic-001.md),
      [ADR 0010](../../../decisions/0010-override-driver-neo4j.md),
      [ADR 0011](../../../decisions/0011-inventaire-driver-et-format-de-story.md),
      [`story-001-1.md`](story-001-1.md),
      [`mesurer-001-1.sh`](mesurer-001-1.sh), `backend/pyproject.toml`

## Définition de fini

- [x] `override-dependencies = ["neo4j>=5.26.0,<6.0.0"]` est dans `backend/pyproject.toml`, avec la **version effectivement résolue** écrite dans un commentaire juste à côté — ADR 0011 — `neo4j 5.28.6`, **identique** à celle consignée dans l'ADR 0011
- [x] `graphiti-core` est une dépendance **produit**, **sans extra** — `graphiti-core==0.30.2`, pinné sur la version que la 001-1 a mesurée (voir Notes de complétion : ce pin ne venait pas du plan)
- [x] **L'override ne couvre que `neo4j`** : `sentence-transformers` et `torch` sont inchangés dans le lock — règle 1 de l'ADR 0010 — `3.0.0` et `2.9.1` avant comme après, vérifié sur le diff du lock et par `uv sync --frozen`
- [x] `uv lock` résout et `uv sync --frozen` réussit — c'est ce que fait l'image Docker (AGENTS.md §2.5, §6) — les deux, dans un **venv vierge** en plus du venv de travail
- [x] `oasis`, puis `neo4j`, puis `graphiti_core` s'importent **dans cet ordre**, dans le même interpréteur — `neo4j 5.28.6`
- [x] La version résolue est confrontée à celle consignée dans l'ADR 0011 ; si elle diffère, l'écart est **écrit quelque part de visible**, pas laissé dans un lock — pas d'écart, et un test le vérifie à chaque run
- [x] Le filet de tests est vert et ne rétrécit pas (192 au départ), et **un test nouveau** garde le périmètre de l'override — **204** (192 + 12), dont 5 sur le dépôt réel et 7 négatifs
- [x] `mesurer-001-1.sh` **reste rejouable** sur l'arbre après override, et c'est vérifié en le lançant — **les deux arbres** : après le geste et après `git checkout`
- [x] Réversibilité vérifiée : `git checkout backend/pyproject.toml backend/uv.lock` ramène à l'état initial, et `uv lock` **échoue** sans l'override — c'est la preuve du conflit, pas une restauration du lock — lock revenu au sha `1b41b865…`, celui qu'annonce la 001-1, et refus du résolveur reproduit
- [x] `ruff`, `validate_plans.py` et `pytest` verts ; `uv.lock` régénéré **et commité**
- [x] La version résolue et le propriétaire de la revalidation sont consignés dans [`deferred-work.md`](../../../deferred-work.md) — l'override promet une compatibilité que rien ne surveille

## Tâches

- [x] 1. Ajouter `graphiti-core` aux dépendances produit de `backend/pyproject.toml` — **pas** `graphiti-core[sentence-transformers]` — `==0.30.2`
- [x] 2. Ajouter la table `[tool.uv]` avec `override-dependencies = ["neo4j>=5.26.0,<6.0.0"]`, en fin de fichier, et laisser un commentaire pour la version résolue
- [x] 3. `uv lock` puis `uv sync`, puis **commiter `uv.lock`** : l'image fait `uv sync --frozen` et échoue sur un lock désynchronisé (AGENTS.md §2.5)
- [x] 4. Vérifier `uv sync --frozen` dans un venv propre, et `uv tree --invert --package neo4j` pour documenter qui tire quoi — l'arbre inversé tient en trois lignes : `camel-oasis` **et** `graphiti-core` dépendent tous deux de `neo4j`, et c'est exactement le nœud du conflit
- [x] 5. Vérifier les imports dans l'ordre, et que `sentence-transformers` / `torch` n'ont pas bougé d'une version
- [x] 6. Relever la version résolue, la confronter à l'ADR 0011, l'écrire dans le commentaire de `pyproject.toml` — `5.28.6`, conforme
- [x] 7. Rendre `mesurer-001-1.sh` rejouable **sur l'arbre après override** — voir les notes de développement, le script casse pour deux raisons — il en a cassé **quatre**, les deux annoncées et deux trouvées en lançant
- [x] 8. Ajouter le test qui garde le périmètre de l'override, puis relancer la suite entière — `backend/tests/test_pyproject_override.py`, 12 tests, **204 au total**

## Notes de développement

**Ce n'est pas une ligne.** `pyproject.toml` prend deux ajouts, et le second est
la partie easy à oublier : `graphiti-core` **sans extra**.

**Pourquoi pas l'extra `sentence-transformers`.** `graphiti-core[sentence-transformers]`
exige `sentence-transformers>=3.2.1`, et `camel-oasis==0.2.5` épingle `==3.0.0`.
Écrire l'extra ici, c'est faire échouer `uv lock` une seconde fois — ou, pire,
élargir l'override pour le contourner et **prendre à la 001-4 une décision que
l'ADR 0010 lui laisse explicitement**. La règle 1 de l'ADR 0010 dit que le
périmètre de l'override est `neo4j` seul ; cette story ne la discute pas, elle
l'applique. L'embedder reste le problème de la 001-4, avec son propre arbitrage.

**La borne n'épingle rien, donc la version doit être écrite à côté.**
`neo4j>=5.26.0,<6.0.0` se résout sur la dernière 5.x au jour du lock. Ce n'est
pas un détail : l'ADR 0010 se déclare supersédé si la 001-2 casse, et la 001-2
doit tester **la version qui sera déployée**. Un `uv lock` relance après une
release du driver donne silencieusement `5.29.x`, et la 001-2 testerait alors
autre chose que ce qui part en production. D'où le commentaire à côté de la
déclaration : il rend la dérive visible au lieu de la laisser dans un lock.
L'ADR 0011 fixe la référence à `5.28.6` (relevé le 3 octobre 2026).

**`mesurer-001-1.sh` casse, et pas moyennement.** Deux raisons, toutes deux
dures :

1. ligne 65 — `assert "graphiti-core" not in text`. Après cette story,
   `graphiti-core` est là. L'assertion échoue et le protocole s'arrête au
   premier pas.
2. ligne 71 — `>> "$PYPROJECT"` ajoute une seconde table `[tool.uv]`. TOML
   refuse : `Cannot declare ('tool', 'uv') twice`. Même si l'assertion passait,
   la réécriture serait invalide.

Sans correctif, la mesure de la 001-1 devient **non rejouable** dès que le
geste est posé — exactement ce que NFR-3 interdit, et ce que la revue du
3 octobre vient de réparer. Le protocole doit donc détecter l'état de l'arbre
et prendre un chemin explicite dans les deux cas : « l'override n'est pas
posé » (mesurer le refus du résolveur, puis poser, puis vérifier) et « l'override
est déjà posé » (vérifier, puis retirer temporairement pour refaire la preuve du
refus). L'état ambigu doit être refusé, pas deviné.

**`mesure-001-1.txt` ne se rafraîchit pas.** C'est la sortie d'une exécution
datée du 3 octobre 2026, sur un arbre sans override : c'est la **preuve
historique**, pas un rapport à mettre à jour. Elle reste telle quelle, et ses
`192 passed` ne changent pas — après cette story, le compte bougera.

**Où va la table `[tool.uv]`.** En fin de `pyproject.toml`, après
`[tool.ruff.lint.per-file-ignores]`. `uv` la lit sans peine ; ce qui compte est
qu'il n'y en ait **qu'une**, pour la raison du point 2 ci-dessus.

**Ce que cette story ne prouve pas.** Pas le comportement du driver à
l'exécution : aucun test n'ouvre de connexion ici, il n'y a pas encore de Neo4j.
C'est la 001-2, et elle est le premier test comportemental de cet override. Ne
pas lire un lock valide comme une preuve de fonctionnement.

**Stratégie de test.** Trois niveaux, aucun ne demande de Neo4j :

1. le lock : `uv lock` puis `uv sync --frozen` dans un venv propre ;
2. l'import : `oasis`, `neo4j`, `graphiti_core` dans cet ordre, un seul
   interpréteur ;
3. le garde-fou : un test qui lit le vrai `backend/pyproject.toml` et refuse
   `neo4j` seul — sur le modèle de `test_real_repo_is_valid`, qui valide le
   dépôt réel. C'est le seul moyen automatique de tenir la règle 1 de l'ADR
   0010 ; sans lui, élargir l'override à `sentence-transformers` plus tard ne
   laisserait aucune trace.

## Revue

### Revue de code — 4 octobre 2026

Relecture des quatre commits `971fbc3..204ff33` par quatre couches indépendantes
( chasse aveugle, chasse aux cas limites, écart de vérification, auditeur
d'acceptation), chacune sans voir les autres. Bilan : **60 findings**, dont
**cinq vérifiés comme invalides des affirmations de cette story** — donc
corrigés, pas contestés. Les 55 autres sont dans les sections qui suivent.

> **Pourquoi ces findings sont sous `## Revue` et non sous `## Tâches`.**
> `validate_plans.py` refuse toute case ouverte dans `## Tâches` pour une story
> en `review`. C'est aussi, de toute façon, le bon endroit pour le compte rendu
> d'une revue.

#### Bloquants — une affirmation fausse, corrigée

- [x] **`uv sync --frozen` ne vérifie pas le lock.** La story, `AGENTS.md` §10 et
      `LOCAL-FIRST.md` affirmaient que le piège de build était « surveillé, pas
      évité ». Vérifié : sur un `pyproject.toml` que le lock ne satisfait pas,
      `--frozen` sort en **0** et installe le lock tel quel — la dépendance
      ajoutée est silencieusement absente. C'est `--locked` qui sort en 1.
      **« ne pas mettre à jour le lock » n'est pas « vérifier que le lock est à
      jour ».** Corrigé dans `Dockerfile:24` et `.github/workflows/ci.yml`.
- [x] **Les tests de cohérence lock étaient auto-satisfaits.** `uv run pytest` —
      la commande de la CI comme celle de `AGENTS.md` §3 — **re-résout et
      réécrit `uv.lock` avant que la suite ne l'ouvre**. Démontré : un lock
      amputé de son `[manifest] overrides` donne `1 failed` en interpréteur
      direct et `12 passed` sous `uv run`. Les tests lisaient le lock que `uv`
      venait d'écrire pour coller au pyproject, donc la dérive qu'ils existent
      pour empêcher passait en vert. Le test compare désormais les octets de
      **l'index git**, dans un sous-processus en `UV_FROZEN=1`.
- [x] **La version résolue de `graphiti-core` n'était gardée par rien.** Le pin
      `==0.30.2` est présenté comme une décision dans les notes de complétion,
      et `graphiti-core>=0.30` passait les 204 tests. C'est le pin qui décide de
      ce que la 001-2 importera : il est maintenant gardé, contre le lock, avec
      son négatif.
- [x] **`test_extra_on_graphiti_core_is_reported` ne testait pas ce qu'il
      disait.** Sa fixture *ajoutait* une seconde entrée
      `graphiti-core[sentence-transformers]` à côté de la vraie : elle prouvait
      qu'une entrée porte un extra, pas que la nôtre n'en porte pas. Elle mute
      maintenant **la déclaration livrée**.
- [x] **Le bloc canonique de l'ADR 0011 avait été supprimé de `STATUS.md`.**
      L'ADR exige que `STATUS.md` et la story reprennent cette écriture exacte ;
      le diff retirait le seul bloc qui restait. Restauré.

#### Corrigés sans être bloquants

- [x] **Le périmètre de l'override n'était gardé qu'à moitié.** `constraint-
      dependencies` et `[tool.uv.sources]` sont deux autres façons de forcer une
      version, et rien ne les regardait : élargir l'override par ce levier ne
      laisserait aucune trace, alors que la story affirme le contraire dans trois
      documents. Les deux sont surveillés.
- [x] **La version lockée n'était pas confrontée à la borne.** Un lock sur
      `5.23.0` — le pin de `camel-oasis`, c'est-à-dire l'override qui ne
      s'applique plus — passait, tant que le commentaire suivait. La seule
      comparaison commentaire/lock ne le voit pas.
- [x] **`sentence-transformers 3.0.0` et `torch 2.9.1` n'étaient vérifiés que par
      une lecture du diff, une fois.** La définition de fini les coche ; un test
      les garde désormais, donc la preuve ne disparaît pas au prochain
      `uv lock`.
- [x] **Les deux invariants qui lisent le lock n'avaient aucun test négatif** —
      « sept négatifs sur neuf, les deux trous sont ceux qui vérifient le lock ».
- [x] **Le commentaire de version était cherché n'importe où dans le fichier**,
      alors que l'ADR 0011 dit « à côté de la borne ». Un commentaire en tête de
      fichier.passait et aurait survécu à un changement de borne.
- [x] **Le protocole : `trap` posé après le premier sync** (une interruption
      entre les deux laissait un venv muté, jamais restauré), **`uv lock` et
      `uv sync` non asservis à l'étape 2** (`$LOCKED_NEO4J` était lu dans le venv
      — donc périmé — et consigné comme « version résolue »), **`[tool.uv]`
      supprimé en silence** quand il portait d'autres clés (`index-url` : la
      mesure se faisait contre un autre index que la production), **mode inconnu
      mesurant la branche « refus » en silence**, **`graphiti-core` dans un groupe
      `dev` étiquetant l'arbre « AVANT la 001-1b »**, **`python3` sans
      `tomllib` produisant un `ImportError` en pleine étape**.
- [x] **Le protocole n'avait aucune couverture.** Huit tests l'exercent
      maintenant en **extrait la vraie fonction du vrai script** — une seconde
      implémentation dériverait, ce qui est précisément ce qu'on veut voir.
      Chaque garde-fou a été neutralisé puis le test rejoué : il échoue bien.
- [x] **Le protocole insérait `graphiti-core` à la marge**, en perdant
      l'indentation. Le pyproject restait valide — `uv` ne protestait pas — mais
      l'arbre mesuré n'était plus l'arbre du dépôt. Visible parce que l'étape 6
      lance la suite sur l'arbre réécrit, invisible autrement.

#### Retenues pour la suite, avec ce qui les déclencherait

- [x] **`posthog` entre par la porte de `graphiti-core`, et la télémétrie est
      active par défaut** — traitée comme une décision, pas comme un détail.
      Voir les notes de complétion.
- [x] **NFR-3 : ma plus forte affirmation n'avait aucun artefact versionné.**
      Les deux sorties sont désormais dans
      [`mesure-001-1b-avant-override.txt`](mesure-001-1b-avant-override.txt) et
      [`mesure-001-1b-apres-override.txt`](mesure-001-1b-apres-override.txt),
      expliquées dans [`mesures-001-1b.md`](mesures-001-1b.md).
      `mesure-001-1.txt` n'est **pas** rafraîchi : c'est la preuve du
      3 octobre, et ses `192 passed` sont ceux de ce jour-là.
- [x] **`epic-001.md` annonçait « atteint »** dans la colonne des critères alors
      que la story est en revue. Le marqueur a reculé dans les notes de la story,
      qui est sa place.
- [x] **`deferred-work.md` se contredisait** : une entrée disait « ni comment on
      le remarquerait », l'autre que le déclencheur est mécanique. La première est
      marquée comme traitée.
- [x] **`sprint-status.yaml` gardait `mis_a_jour: 2026-10-03`** alors que son
      bloc 001-1b décrivait le 4 octobre.
- [x] **`docs/README.md` n'indexe ni l'ADR 0010 ni l'ADR 0011.** Entrée
      différée, préexistante, et ce diff y ajoute des renvois.

#### Différé, avec ce qui le déclencherait

- Le **pin du frontend** : `pnpm install --frozen-lockfile` a une sémantique
  analogue à `--frozen` et n'a pas été testé comme elle. *Ce qui déclencherait :
  une désynchronisation constatée côté Node, ou un ADR de précision sur la
  sémantique des deux drapeaux.*
- **`constraint-dependencies` reste autorisé sur `neo4j`.** Le test refuse un
  levier qui force *un autre paquet* ; il n'interdit pas un second mécanisme sur
  le même, qui n'apporterait rien et compliquerait la lecture. *Ce qui
  déclencherait : son apparition dans `pyproject.toml`.*
- **Les chiffres du diff du lock** (50 lignes ajoutées, 3 supprimées, cinq
  lignes de version) ne sont pas reproductibles depuis un artefact. Ils sont
  exacts pour ce commit, et `git diff 971fbc3..HEAD --stat` les régénère.

## Notes de complétion

### Ce qui a été fait

Le geste est là, dans `backend/pyproject.toml`, et il est exact :

```toml
override-dependencies = ["neo4j>=5.26.0,<6.0.0"]
# version effectivement résolue au lock du 2026-10-03 : neo4j 5.28.6
```

`uv lock` résout 189 paquets : `graphiti-core 0.30.2` et `posthog 7.62.1` et
`tenacity 9.1.4` entrent, `neo4j` passe de 5.23.0 à 5.28.6, **et rien d'autre ne
bouge**. Le diff du lock est de 50 lignes ajoutées et 3 supprimées ; sur les
lignes de version, cinq seulement changent, et `sentence-transformers 3.0.0` et
`torch 2.9.1` n'en font pas partie. C'est la règle 1 de l'ADR 0010 vérifiée par
le lock lui-même, pas par une intention.

`uv sync --locked` réussit dans un venv vierge, et les trois imports passent dans
l'ordre (`oasis`, `neo4j 5.28.6`, `graphiti_core`). **234 tests verts** après la
revue, 204 au premier jet de cette story, 192 avant elle.

**La version résolue est celle de l'ADR 0011.** 5.28.6, sans écart — mais rien ne
l'aurait garanti : `neo4j>=5.26.0,<6.0.0` résout sur la dernière 5.x au jour du
lock. C'est le motif du test `test_resolved_version_comment_matches_the_lock`.

### Le pin de `graphiti-core` — une décision que le plan ne prenait pas

Le plan disait « ajouter `graphiti-core` », sans contrainte. **Ce n'était pas
suffisant** : la forme de la déclaration décide de ce que la story 001-2
testera. On a retenu **`==0.30.2`**, pour trois raisons :

1. c'est la version que la story 001-1 a **mesurée**, et celle que vise l'ADR
   0010 (« la 0.30 ») ;
2. c'est cohérent avec le style déjà présent — `camel-oasis==0.2.5`,
   `zep-cloud==3.25.0` sont pinnés à l'exact ;
3. une borne de mineure laisserait passer une 0.30.x corrige sans qu'on le
   voie, ce qui est précisément le risque que l'ADR 0011 signalait pour le
   driver. On l'accepte ici, on ne l'ajoute pas.

`graphiti-core[sentence-transformers]` aurait fait échouer le lock une seconde
fois : l'extra exige `>=3.2.1`, `camel-oasis` épingle `==3.0.0`, et la sortie se
règle soit en élargissant l'override — donc en tranchant la 001-4 sans le dire —
soit en laissant le lock cassé. La déclaration est donc **sans extra**, et un
test refuse qu'on en ajoute un.

### Le protocole de mesure cassait — pour deux raisons annoncées, et deux trouvées

Les deux raisons prévues étaient réelles : l'assertion
`"graphiti-core" not in text` échoue, et le `>> "$PYPROJECT"` ajoute une seconde
table `[tool.uv]` que TOML refuse. Mais **le compte était faux**. En lançant le
protocole sur l'arbre après override, deux autres défauts sont apparus :

- **le filet de tests du protocole lit le commentaire de version.** Le nouveau
  `test_pyproject_override.py` vérifie que la version consignée à côté de l'override
  est celle du lock ; or la réécriture que fait le protocole ne portait que la
  ligne `override-dependencies`. Résultat : **2 tests en échec** à l'étape 6,
  sur un arbre qui était censé être conforme. Le protocole **écrit désormais** la
  version résolue dans son propre `[tool.uv]`, comme le fait la story. Ce n'est
  pas un détail de forme : c'est ce qui fait de l'arbre mesuré **l'arbre que
  l'override décrit**.
- **les attentes de restauration se lisaient sur un venv fantôme.** Après un
  `git checkout` des deux fichiers, le lock est revenu à 5.23.0 mais le venv
  portait encore `graphiti-core` ; le protocole enregistrait alors un état de
  départ qui n'existait pas, et concluait à une restauration incomplète. Le
  protocole fait désormais `uv sync --frozen` **avant** de relever ses attentes.
  Sans ce correctif, le protocole annonçait « restauration incomplète » sur une
  restauration **exacte** — le pire défaut pour une mesure dont tout l'intérêt
  est d'être crédible.

La solution retenue pour la rejouabilité n'est pas d'accrocher le script à un
état : **le protocole normalise `pyproject.toml` dans l'état qu'il veut mesurer**,
mesure, puis restaure l'octet initial. Il ne suppose donc plus rien de l'arbre.
Il **refuse** en revanche ce qu'il ne sait pas mesurer, avec un message qui
nomme la raison — vérifié sur quatre arbres synthétiques :

| Arbre | Réponse |
|---|---|
| avant la 001-1b (ni `graphiti-core`, ni override) | `AVANT la 001-1b` — mesuré normalement |
| après la 001-1b (les deux) | `APRÈS la 001-1b` — mesuré normalement |
| override élargi à `sentence-transformers` | **refusé** — périmètre ≠ ADR 0010 |
| `graphiti-core` sans override, ou l'inverse | **refusé** — geste à moitié posé |
| deux tables `[tool.uv]` (le bug d'origine) | **refusé** — TOML invalide |

**Le protocole a été lancé sur les deux arbres**, et les deux fois il rapporte
**204 tests verts** sur l'arbre mesuré, puis une restauration identique au
départ : `pyproject.toml` et `uv.lock` au sha de départ, venv au même couple de
versions.

> `mesure-001-1.txt` **n'a pas été rafraîchie** : c'est la sortie datée du
> 3 octobre 2026 sur un arbre sans override, la preuve historique. Ses 192
> `passed` sont ceux de ce jour-là. Les deux sorties de la 001-1b sont dans
> [`mesure-001-1b-avant-override.txt`](mesure-001-1b-avant-override.txt) et
> [`mesure-001-1b-apres-override.txt`](mesure-001-1b-apres-override.txt), et
> [`mesures-001-1b.md`](mesures-001-1b.md) explique ce qu'elles prouvent.

### Réversibilité

`git checkout backend/pyproject.toml backend/uv.lock` ramène à l'état initial :
le lock retrouve son sha `1b41b865…`, celui qu'annonce la story 001-1 — la
preuve que l'état initial est bien celui d'avant la story, pas un état
reconstitué. Le protocole rejoué sur cet arbre **refait reproduire le refus du
résolveur** : c'est la preuve du conflit, pas une restauration du lock. Puis
`uv sync --frozen` remet le venv sur `neo4j 5.23.0` sans `graphiti_core`, et
`git status` ne montre que les fichiers du protocole lui-même.

### `posthog` entre par la porte de `graphiti-core` — et la télémétrie part

`graphiti-core` traîne `posthog 7.62.1` et `tenacity 9.1.4` dans le lock.
Première réaction : une télémétrie de plus, dans un projet dont la thèse est le
local-first. Vérification dans le venv installé :

```python
# graphiti_core/telemetry/telemetry.py:36
env_value = os.environ.get(TELEMETRY_ENV_VAR, 'true').lower()
```

**Activée par défaut**, ciblant `us.i.posthog.com` (`telemetry.py:19`), et
appelée depuis `Graphiti.__init__` (`graphiti.py:248`) — donc dès la
construction du client, avant toute extraction. Le dépôt ne posait la variable
**nulle part**. Je ne l'avais pas vu en posant l'override.

Coupé par défaut, donc, dans `app/config.py` :

```python
GRAPHITI_TELEMETRY_ENABLED = (
    os.environ.get('GRAPHITI_TELEMETRY_ENABLED', 'false').lower() in ('true', '1', 'yes', 'on')
)
# `graphiti-core` lit la variable dans `os.environ` au moment où le client est
# construit, pas via notre Config. La pousser ici est ce qui rend la config
# effective plutôt que décorative.
os.environ['GRAPHITI_TELEMETRY_ENABLED'] = 'true' if GRAPHITI_TELEMETRY_ENABLED else 'false'
```

La seconde ligne est celle qui compte : sans elle, `Config` disait `false` et le
client partait quand même en télémétrie, parce que la bibliothèque lit
`os.environ`. Le test qui le vérifie échoue si on la retire — vérifié en la
retirant. Et un autre test prouve que la bibliothèque **aurait** été active de sa
propre initiative, sans notre config : sans cette preuve, « on est coupé » ne
distingue pas « on a décidé » de « la bibliothèque a changé d'avis ».

Une seule chose nous protégeait avant : `telemetry.py:31` court-circuite sous
pytest. La suite était donc propre, et l'application ne l'était pas.

### Ce que cette story ne prouve toujours pas

Rien à l'exécution. `neo4j 5.28.6` est lockée, importée, et **aucune connexion
n'a été ouverte**. C'est la story 001-2, et c'est elle qui tranche l'ADR 0010 —
par supersession, jamais par réécriture. Un lock valide n'est pas une preuve de
fonctionnement, et cette story ne le prétend pas.

Le coût de l'override — contourner une contrainte déclarée par l'amont, avec un
garde-fou faible — est inchangé. Un point s'améliore : la dérive de version est
désormais **détectée à chaque exécution de la suite**, donc à chaque CI, et non
seulement si quelqu'un relance `uv lock`. C'est consigné dans
[`deferred-work.md`](../../../deferred-work.md), avec le propriétaire proposé de
la revalidation — l'ADR 0010 étant immuable, le nommer demande un ADR de
précision.

## Risques

| Risque | Parade |
|---|---|
| L'override déborde sur `sentence-transformers` et tranche la 001-4 sans le dire | règle 1 de l'ADR 0010 + un test qui refuse un override plus large que `neo4j` |
| La borne résout une autre version à la 001-2 qu'à l'application | version résolue écrite dans `pyproject.toml`, et confrontée à l'ADR 0011 avant de passer en revue |
| `uv.lock` régénéré mais non commité | `uv sync --frozen` est dans la définition de fini ; c'est lui qui échoue dans l'image |
| `mesurer-001-1.sh` devient inutilisable et personne ne s'en aperçoit | rejouabilité dans la définition de fini, **vérifiée en le lançant** — pas en lisant le script |
| L'override tient au lock et casse à l'exécution | ce n'est pas le risque de cette story : c'est celui de la 001-2, et il est assumé dans l'ADR 0010 |
