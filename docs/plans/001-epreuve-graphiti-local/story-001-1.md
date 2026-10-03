---
id: "001-1"
epic: "001"
titre: "Vérifier le conflit graphiti-core vs camel-oasis"
statut: done
auteur: agent
format: "2"
---

# Story 001-1 — Vérifier le conflit `graphiti-core` vs `camel-oasis`

## Pourquoi cette story

Avant d'ajouter `graphiti-core` au projet, il faut savoir s'il peut vivre dans
le même environnement que `camel-oasis`. Le fork de référence a dû séparer les
deux — second venv *et* sous-processus (`simulation_runner._get_simulation_python`).
Notre venv est plus récent : c'est à vérifier, pas à supposer.

Si le conflit existe, il change le périmètre de l'épreuve (venv séparé, ou
service Graphiti isolé). C'est le seul obstacle de cette story.

## Définition de prêt

- [x] Critères Given/When/Then écrits et mesurables
- [x] Aucune dépendance externe non résolue
- [x] Stratégie de test identifiée
- [x] Documents à consulter lus — [`epic-001.md`](../epic-001.md), [ADR 0006](../../../decisions/0006-docker-first.md), `backend/pyproject.toml`

## Définition de fini

Le premier critère est celui qu'on s'était donné avant de commencer. Il **n'est
pas satisfait** : le verdict mesuré est qu'il ne peut pas l'être. Il est barré
plutôt que supprimé, pour qu'un tiers voie ce qu'on avait promis et ce qu'on a
trouvé — c'est tout l'objet de la story.

- [x] ~~`graphiti-core` est résolu sans conflit dans `backend/.venv`~~ — **non satisfiable** : le conflit est structurel et aucune combinaison publiée ne résout. Mesuré, consigné, et arbitré par l'ADR 0010 (voir Notes de complétion)
- [x] ~~`camel-oasis` et le driver `neo4j` sont importables dans le même interpréteur, dans cet ordre~~ — **atteint sous `override-dependencies` uniquement** ; l'override n'est pas dans l'arbre, il sera posé par la story 001-1b
- [x] Les 154 tests sont toujours verts — **183** (le filet a grandi depuis l'écriture de cette DoD)
- [x] Le résultat est consigné dans les notes de complétion ci-dessous — **y compris si c'est un échec**
- [x] Si un conflit existe : options documentées (venv séparé, service isolé) et décision proposée — **arbitrée depuis par l'ADR 0010**, qui décide sans encore l'appliquer
- [x] Aucune trace laissée dans l'arbre : lock au sha256 d'origine, venv restauré

## Tâches

- [x] 1. Ajouter `graphiti-core` aux dépendances produit de `backend/pyproject.toml`
- [x] 2. Régénérer le lock (`uv lock`) — **échec, voir les notes de complétion**
- [x] 3. `uv sync`, puis vérifier qu'aucun conflit de version n'apparaît — **conflit confirmé**
- [x] 4. Importer `camel-oasis` puis `neo4j` dans le même interpréteur — fait sous override
- [x] 5. Lancer `pytest tests/ -q` — 183 passed (et non 154 : le filet a grandi depuis l'écriture)

## Notes de développement

**Architecture.** On ajoute `graphiti-core` pour mesurer, pas pour livrer. Si le
lock casse, on revert la dépendance : l'epic 001 doit pouvoir être annulé sans
laisser de trace dans le dépôt.

**Stratégie de test.** Test de cohabitation dans un seul interpréteur — c'est le
seul point qui peut échouer ici. Aucun appel réseau, aucun Neo4j : c'est un
contrôle d'import, pas un test fonctionnel.

**Documents de référence.**

- [`epic-001.md`](../epic-001.md) — le contrat de l'epic
- [`docs/LOCAL-FIRST.md` §11](../../../LOCAL-FIRST.md) — le même obstacle, vu par l'amont
- [ADR 0006](../../../decisions/0006-docker-first.md) — un seul environnement de référence

## Revue

### Review Findings — 3 octobre 2026

Revue des commits `c1e17e0` + `0cdf1c0` (`ad4ef4c..HEAD`, 12 fichiers,
+352/-69), quatre couches de relecture indépendantes : un chasseur aveugle, un
chasseur de cas limites, un vérificateur de couverture de tests et un auditeur
d'acceptation. Chaque affirmation a été revérifiée dans l'arbre avant d'être
retenue.

**Ce qui est vérifié et conforme, et qui ne bouge pas.** La mesure elle-même
est juste : les 183 tests passent, `ruff` est propre, `backend/uv.lock` porte
bien le sha256 `1b41b865…` annoncé, ni `uv.lock` ni `pyproject.toml` ne sont
touchés par ce diff, et ni `graphiti-core` ni l'`override` ne sont dans l'arbre.
« Cette story mesure, elle ne décide pas » a été respectée.

**Ce que la revue a trouvé.** Le diff corrigeait une information fausse — le
« second conflit » `sentence-transformers` et l'attribution `camel-ai` de
`architecture.md` §3 — tout en introduisant trois faits nouveaux faux ou
périmés : un inventaire d'API dans l'ADR 0010 dont l'un des deux symboles
n'existe pas, une réécriture d'un ADR accepté assortie d'une note qui affirme le
contraire de ce que fait le hunk, et une Définition de fini réécrite après
l'échec. Les deux premiers sont dans des documents destinés à fonder des
décisions futures ; le troisième est ce qui fait passer la story en revue.

> **Pourquoi ces findings sont sous `## Revue` et non sous `## Tâches`.**
> `validate_plans.py:180-188` refuse toute case ouverte dans `## Tâches` pour
> une story en `review` ou `done`. Écrire les findings actionnables là-dedans
> ferait échouer la CI que ce diff vient d'entretenir. `## Revue` est la seule
> section que le validateur ne scanne pas — et c'est de toute façon le bon
> endroit pour le compte rendu d'une revue.

**Bilan : 9 décisions requises, 20 patches, 5 différés, 5 rejets.** Les 9
décisions ont été tranchées et les 20 patches appliqués dans le même mouvement
que cette section.

#### Tranchées puis appliquées — 9

- [x] [Review][Decision] **ADR 0009 (accepté) réécrit, et le hunk affirme le contraire de ce qu'il fait** → **retour en arrière intégral** : `git checkout c1e17e0 -- 0009-format-des-stories.md`. Illustration anglaise, Contexte, Note d'implémentation et puce Négatives sont revenues à leur état d'origine. La seule édition conservée est une note exacte : cet ADR est immuable, son illustration est caduque, l'ADR 0011 porte la décision. `AGENTS.md` §2.10 pointe 0011 et reconnaît que la règle est outillée.
- [x] [Review][Decision] **L'inventaire d'API qui fonde l'override est faux** → **[ADR 0011](../../../decisions/0011-inventaire-driver-et-format-de-story.md)** créé : il relève la surface réelle (`GraphDatabase.driver`, `Query`, quatre types d'exceptions ; `neo4j.Version` **retiré**, 0 occurrence) et consigne la version résolue. L'ADR 0010 le pointe et signale par un encadré que sa règle 2 est remplacée. Indexé dans `decisions/README.md`, `AGENTS.md` §9, `epic-001.md`.
- [x] [Review][Decision] **Renommer `STORY_SECTIONS` sans version de format** → **marqueur `format: "2"`** dans l'en-tête, avec sortie anticipée avant les contrôles de sections : un fichier au format 1 produit **un** message nommant le format, la raison et le remède, au lieu de sept identiques. Trois tests couvrent le cas.
- [x] [Review][Decision] **La DoD réécrite après l'échec, et le saut `backlog → review`** → les six critères d'origine sont restaurés, **le premier barré et annoté « non satisfiable »** plutôt que supprimé. Statut conservé. La formulation barrée est celle du dépôt (`LOCAL-FIRST.md` §11 point 4, §Risques plus bas) : elle préserve l'échec sans laisser de case ouverte, ce que le validateur renforcé par la décision D8 refuse.
- [x] [Review][Decision] **ADR 0010 « à acter » dans cinq fichiers, 001-1b dans un index sur trois** → les cinq occurrences corrigées (`AGENTS.md` §1, `sprint-status.yaml`, `docs/LOCAL-FIRST.md`, `docs/STATUS.md`, `architecture.md`). `AGENTS.md` §1 désigne **001-1b** comme la tâche du moment ; `STATUS.md` nomme la story et porte la forme canonique de la constante. L'ordre 001-1b → 001-2 est explicite des deux côtés.
- [x] [Review][Decision] **NFR-3 citée à contresens, et la mesure non rejouable** → [`mesurer-001-1.sh`](mesurer-001-1.sh) écrit et **exécuté** : il mesure, remet `pyproject.toml`, `uv.lock` et le venv à leur état initial — vérifié, sha256 `1b41b865…`, `neo4j` 5.23.0, `graphiti_core` absent — et sa sortie est versionnée dans [`mesure-001-1.txt`](mesure-001-1.txt). La sortie du résolveur y est verbatim, avec les trois exigences lues dans les `METADATA` installés. La « Limite de la mesure » ne prétend plus que le PRD exclut Neo4j : elle dit ce que l'epic n'a pas encore fourni.
- [x] [Review][Decision] **Plage non épinglée : 001-2 ne teste pas ce qui sera déployé** → la version résolue (**`neo4j 5.28.6`**, relevée par le protocole) est écrite dans l'ADR 0010 et dans l'ADR 0011. Les trois écritures de la constante (`ADR 0010`, `STATUS.md`, cette story) sont identiques : `neo4j>=5.26.0,<6.0.0`.
- [x] [Review][Decision] **Le validateur n'impose pas les invariants qu'AGENTS.md §2.8 lui attribue** → `AGENTS.md` §2.8 n'énumère plus que ce qui est réellement appliqué et signale que « jamais de saut » n'est outillé par rien. `validate_plans.py` gagne : scan des cases des deux définitions pour une story en `review`/`done`, citation dans le hub par frontières de mot, présence du fichier derrière une ligne de hub `in-progress`, forme de l'`id`. L'ordre des états part en [`deferred-work.md`](../../../deferred-work.md) : il faudrait l'historique git.
- [x] [Review][Decision] **`001-1b` hors convention `story-<epic>-<n>.md`** → la convention est documentée dans `AGENTS.md` §2.8 : suffixe alphabétique facultatif pour une story dérivée d'un critère qu'une story précédente n'a pas pu tenir. `validate_plans.py` valide la forme et refuse un `id` mal formé.

#### Patch — 11

- [x] [Review][Patch] Le contrat « sections en français » n'a aucun test négatif → `test_english_section_titles_are_reported` écrit. **Vérifié** : il échouerait si le matcher était élargi aux titres anglais. `test_pre_rename_format_is_reported_once` et `test_uppercase_checkbox_counts_as_done` l'accompagnent.
- [x] [Review][Patch] Les deux invariants non appliqués du hub → `test_sibling_story_id_does_not_satisfy_citation` (avec une story `001-1b` en présence), `test_started_hub_row_without_file_is_reported`, `test_backlog_hub_row_without_file_is_allowed`, `test_malformed_story_id_is_reported`, `test_derived_story_id_suffix_is_accepted`.
- [x] [Review][Patch] Chiffre faux : « plus de 90 % de son historique » → **106 publications sur 194 (54,6 %)**, ou 19 séries mineures sur 31 (61 %). La note distingue maintenant pin exact et plancher, et rappelle qu'abaisser `graphiti-core` à la 0.11.6 reste ouvert — c'est le coût, pas l'impossibilité, qui l'a fait rejeter.
- [x] [Review][Patch] Le PRD garde comme parade l'option rejetée → `prd.md` renvoie à l'ADR 0010 et à la story 001-1b.
- [x] [Review][Patch] `LOCAL-FIRST.md` porte l'attribution périmée → §« Le cas de l'embedder » réécrit ; le point 3 de §12.6 marque la 001-4 bloquée, le point 4 tranché.
- [x] [Review][Patch] « Deux épinglages exacts » → corrigé dans `AGENTS.md` §6 et §10, `sprint-status.yaml`, `architecture.md` et les deux ADR.
- [x] [Review][Patch] Critère de 001-1b inatteignable → réécrit : la réversibilité passe par `git checkout backend/pyproject.toml backend/uv.lock`, et le critère dit que `uv lock` **échoue à nouveau** sans l'override — c'est la preuve du conflit, pas une restauration du lock.
- [x] [Review][Patch] `154` contre `183`, « 9 ADR » périmé → `epic-001.md` (NFR-5 et checklist) et `docs/STATUS.md` passés à **192** tests et **11 ADR**. Les deux occurrences historiques de `154` dans `LOCAL-FIRST.md` et `ADR 0001` sont laissées : elles décrivent un état passé.
- [x] [Review][Patch] `- [X]` compté comme case ouverte → `done.lower() != "x"`.
- [x] [Review][Patch] `drowned` et `stories.yaml` → docstring francisée et réécrite pour dire ce que le script ne contrôle pas ; en-tête de `sprint-status.yaml` corrigé.
- [x] [Review][Patch] « Les Les » dupliqué et sauts de ligne finaux → corrigés sur l'ADR 0010, l'ADR 0011 et cette story. Au passage : « et donc Indirectement cet ADR. » dans l'ADR 0010.

#### Rejetées — 5

- Ordre et doublon de section non détectés — `low`, le correctif (détection de doublon) dépasse une correction directe et deux `## Tâches` dans un même fichier est peu probable en usage courant.
- Cases à cocher situées dans un bloc ``` comptées comme des tâches ouvertes — `low`, même motif ; aucune story ne cite l'illustration d'ADR 0009.
- §2.10 « un terme technique établi où la traduction serait moins claire » sans critère d'arbitrage — aucun mauvais résultat démontré ; l'échappatoire est délibéré, borné, et assorti d'exemples.
- Traçabilité de l'ajout de la ligne 001-1b dans `epic-001.md` — aucun écart : AGENTS.md §2.8 autorise une story `backlog` qui n'existe que dans l'index de l'epic, et ses critères résumés sont bien présents.
- ADR 0010 ne référence ni ADR 0004 ni `story-001-4` — `low`, la référence à `story-001-4` est déjà explicite dans la Décision règle 1 ; ADR 0004 est le risque de l'epic 001-3, hors du sujet de cet ADR.

## Notes de complétion

### Verdict : le conflit existe, et il est réel — pas une rumeur de fork

`graphiti-core` **ne peut pas** cohabiter avec `camel-oasis` dans un même venv
avec les versions de l'amont. Les épinglages sont mutuellement exclusifs :

| Paquet | Exigence | Origine |
|---|---|---|
| `camel-oasis==0.2.5` | `neo4j==5.23.0` (pin exact) | amont, `pyproject.toml:24` |
| `graphiti-core==0.30.2` | `neo4j>=5.26.0` | Graphiti |

Écarté par le résolveur, sans l'ombre d'une ambiguïté :

```
Because camel-oasis==0.2.5 depends on neo4j==5.23.0 and
graphiti-core==0.30.2 depends on neo4j>=5.26.0, we can conclude that
camel-oasis==0.2.5 and graphiti-core==0.30.2 are incompatible.
```

Ce n'est pas un accident de version : **camel-oasis n'a jamais piné autre chose
que `neo4j==5.23.0`**, sur ses 9 versions publiées (0.0.1 → 0.2.5, la dernière
datant de décembre 2025). De son côté, `graphiti-core` exige `neo4j>=5.26.0`
**depuis la 0.12.0** (publiée le 13 juin 2025) — soit 106 de ses 194
publications sur PyPI (54,6 %), ou 19 de ses 31 séries de version mineures
(61 %).

Les deux côtés ne sont pas de même nature, et la distinction est celle qui
ouvre des solutions : `camel-oasis` impose un **pin exact**, qu'aucune version
publiée ne desserre ; `graphiti-core` impose un **plancher**, qu'une version
plus ancienne côté Graphiti suffit à satisfaire. Il n'existe donc **aucune
combinaison des deux paquets publiés où les deux exigences tiennent
simultanément** — ce n'est pas notre lock qu'il faut défaire, c'est une
contrainte structurelle de l'amont. Le corollaire est qu'abaisser
`graphiti-core` jusqu'à la 0.11.6 reste une voie ouverte : elle est rejetée par
l'ADR 0010 pour son coût, pas parce qu'elle serait impossible.

Le pin `==5.23.0` de camel-oasis vient d'ailleurs de `oasis` resserrant pour son
stockage graphe interne : `camel-ai[rag]` accepte large (`neo4j>=5.18,<6`), et
aucune source ne documente ce resserrement comme un choix délibéré.

### Deuxième conflit, trouvé en chemin : l'embedder de la story 001-4

Il ne faut pas découvrir celui-là en plein milieu de la mesure :

| Paquet | Exigence |
|---|---|
| `camel-oasis==0.2.5` | `sentence-transformers==3.0.0` (pin exact) |
| `graphiti-core[sentence-transformers]` | `sentence-transformers>=3.2.1` |

Même forme, même cause. `architecture.md` §3 affirme que
`sentence-transformers==3.0.0` est « déjà dans le venv » et en déduit que
l'embedder local est gratuit — c'est vrai, mais cet extra de Graphiti est
**ininstallable** sans arbitrage. **La story 001-4 est donc bloquée par le même
mécanisme**, et devra être arbitrée avec le même geste.

### Ce qui a été tenté, et ce que ça donne

Le plan disait « si le lock casse, on revert ». Reverté, oui — mais **après
avoir mesuré l'échec**, parce que « ça ne marche pas » ne dit pas *quoi* faire.

**Option A — forcer le driver (`uv` `override-dependencies`).** Forcer
`neo4j>=5.26.0,<6.0.0` pour satisfaire les deux : le lock résout, `camel-oasis`,
`neo4j` et `graphiti_core` s'importent **dans cet ordre** sans erreur, et les
**183 tests restent verts**. C'est l'override qui rend le pin exact et le
plancher satisfiables en même temps. La forme exacte de la constante est celle
de l'ADR 0010, confirmée par l'ADR 0011 — `docs/STATUS.md` et ce fichier
reprennent cette écriture, pas une variante.

**Option B — venv séparé pour Graphiti.** C'est ce qu'a fait `tt-a1i`, et ce
que `LOCAL-FIRST.md` §11 décrit. Ça marche, mais c'est exactement le
second environnement que l'ADR 0006 interdit, plus le sous-processus
`simulation_runner._get_simulation_python` à maintenir. Coût permanent pour un
problème d'une ligne.

**Option C — faire évoluer camel-oasis.** Impossible à court terme : l'épinglage
vient de l'amont et il n'existe aucune version plus récente qui le desserre.

**Décision proposée : Option A.** Elle tient un seul environnement (ADR 0006
respecté), le lock reste reproductible, et les tests le confirment. Son coût :
on contourne délibérément une contrainte déclarée par l'amont — il faut donc que
ce soit **acté dans un ADR**, pas un `override` oublié dans un `pyproject.toml`.
→ **Arbitré par l'ADR 0010**, qui décide sans encore l'appliquer, et précisé par
l'ADR 0011 qui corrige l'inventaire d'API sur lequel la décision reposait. Le
geste sera posé par la story 001-1b, après revalidation.

### Limite de la mesure — à lire avant de foncer

L'override prouve la **coexistence au niveau de l'import et du lock**. Il ne
prouve pas le comportement **à l'exécution contre un vrai Neo4j** : aucun test
de cette story n'ouvre de connexion.

Cette limite ne vient pas d'une exclusion de périmètre, mais de ce que l'epic
n'a pas encore fourni : Neo4j n'existe pas (c'est la story 001-2) et le PRD
n'exclut rien de ce côté — son critère **C3** exige au contraire un graphe
« relisible après redémarrage de Neo4j », et sa table « Hors périmètre »
(`prd.md`) vise GraphStore, ontologie, Docker et le code de production. NFR-3
ne dit rien du périmètre : elle exige qu'une mesure soit rejouable et sa sortie
capturée. C'est ce second point qui a été corrigé — voir ci-dessous.

Si l'override est retenu, le premier vrai test de comportement arrive à la
**story 001-2**, quand Neo4j existera — et c'est là, pas ici, qu'un problème de
driver se verrait. C'est le seul écart notable avec le périmètre annoncé.

### Rejouabilité — la sortie de la mesure, capturée

La mesure ci-dessus a d'abord été rapportée en prose : quatre lignes de sortie
de résolveur recopiées et un sha256 tronqué. C'est exactement ce que NFR-3
qualifie de non valuable. Le protocole est donc rejouable et sa sortie est
versionnée :

- [`mesurer-001-1.sh`](mesurer-001-1.sh) — le protocole, commenté, à lancer
  depuis `backend/`. Il part d'une copie de sauvegarde de `pyproject.toml` et
  `uv.lock` et les restaure en sortie, y compris en cas d'échec.
- [`mesure-001-1.txt`](mesure-001-1.txt) — sa sortie, versionnée.

Relire `mesure-001-1.txt` suffit à reconstituer ce qui a été mesuré, sans avoir
à le refaire.

### Trace

`pyproject.toml`, `uv.lock` et le venv sont revenus à l'état initial — le lock
a le même sha256 qu'avant l'expérience (`1b41b865…`), et `uv sync` +
`pytest` confirment 183 passed / ruff propre. L'override n'est **pas** dans
l'arbre : cette story mesure, elle ne décide pas. L'ADR 0010 l'a tranché le
3 octobre 2026, et l'ADR 0011 l'a précisé — il sera appliqué par une story
dédiée, la 001-1b.

## Risques

| Risque | Parade |
|---|---|
| Le conflit réapparaît et impose une autre architecture | ~~documenter les options et proposer une décision, sans l'appliquer dans cette story~~ → **il réapparaît** ; options mesurées dans les notes de complétion, décision arbitrée par l'ADR 0010 |
| L'override passerait l'import mais casser à l'exécution | aucun test ici n'ouvre de connexion ; le premier test comportemental est la story 001-2, avec un vrai Neo4j |
| Le conflit `sentence-transformers` de la 001-4 est découvert trop tard | déjà mesuré et consigné ici ; la 001-4 est bloquée par le même mécanisme |
