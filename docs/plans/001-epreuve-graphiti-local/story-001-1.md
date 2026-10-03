---
id: "001-1"
epic: "001"
titre: "Vérifier le conflit graphiti-core vs camel-oasis"
statut: review
auteur: agent
---

# Story 001-1 — Vérifier le conflit `graphiti-core` vs `camel-oasis`

## Pourquoi cette story

Avant d'ajouter `graphiti-core` au projet, il faut savoir s'il peut vivre dans
le même environnement que `camel-oasis`. Le fork de référence a dû séparer les
deux — second venv *et* sous-processus (`simulation_runner._get_simulation_python`).
Notre venv est plus récent : c'est à vérifier, pas à supposer.

Si le conflit existe, il change le périmètre de l'épreuve (venv séparé, ou
service Graphiti isolé). C'est le seul obstacle de cette story.

## Definition of Ready

- [x] Critères Given/When/Then écrits et mesurables
- [x] Aucune dépendance externe non résolue
- [x] Stratégie de test identifiée
- [x] Documents à consulte lus — [`epic-001.md`](../epic-001.md), [ADR 0006](../../../decisions/0006-docker-first.md), `backend/pyproject.toml`

## Definition of Done

- [x] Le conflit est établi par le résolveur, pas supposé — **il existe**, et il est structurel
- [x] `camel-oasis` puis `neo4j` importables dans le même interpréteur, **dans cet ordre** (sous override)
- [x] Les tests sont toujours verts — 183 (le plan en annonçait 154 : le filet a grandi)
- [x] Le résultat est consigné dans les completion notes ci-dessous — **y compris le second conflit** (`sentence-transformers`, qui bloque la 001-4)
- [x] Options documentées et décision proposée — sans l'appliquer
- [x] Aucune trace laissée dans l'arbre : lock au sha256 d'origine, venv restauré

## Tasks

- [x] 1. Ajouter `graphiti-core` aux dépendances produit de `backend/pyproject.toml`
- [x] 2. Régénérer le lock (`uv lock`) — **échec, voir completion notes**
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

Suivis éventuels : _aucun pour l'instant._

## Completion notes

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
**depuis la 0.12.0** (juin 2025) — soit plus de 90 % de son historique. Les
deUX côtés sont des épinglages exacts, sur des versions qui ne se recouvrent
pas. Il n'existe donc **aucune combinaison des deux paquets published qui
résout** : ce n'est pas notre lock qu'il faut défaire, c'est une contrainte
structurelle de l'amont.

Le pin `==5.23.0` de camel-oasis est d'ailleurs un choix délibéré, pas un
hasard : le projet camels l'utilise pour son stockage graphe
(`camel-ai[rag]` exige `neo4j>=5.18,<6`, une borne large que 5.26 respecte —
c'est oasis qui resserre à l'exact).

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
mécanisme**, et devra être arbitrée avec le même gesture.

### Ce qui a été tenté, et ce que ça donne

Le plan disait « si le lock casse, on revert ». Reverté, oui — mais **après
avoir mesuré l'échec**, parce que « ça ne marche pas » ne dit pas *quoi* faire.

**Option A — forcer le driver (`uv` `override-dependencies`).** Forcer
`neo4j>=5.26,<6` pour satisfy les deux : le lock résout, `camel-oasis`,
`neo4j` et `graphiti_core` s'importent **dans cet ordre** sans erreur, et les
**183 tests restent verts**. C'est l'override qui rend les deux pins exacts
satisfiables en même temps.

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

### Limite de la mesure — à lire avant de foncer

L'override prouve la **coexistence au niveau de l'import et du lock**. Il ne
prouve pas le comportement **à l'exécution contre un vrai Neo4j** : aucun test
de cette story n'ouvre de connexion (hors périmètre, NFR-3, et le PRD l'exclut
explicitement). Si l'override est retenu, le premier vrai test de comportement
arrive à la **story 001-2**, quand Neo4j existera — et c'est là, pas ici, qu'un
problème de driver se verrait. C'est le seul écart notable avec le périmètre
annoncé.

### Trace

`pyproject.toml`, `uv.lock` et le venv sont revenus à l'état initial — le lock
a le même sha256 qu'avant l'expérience (`1b41b865…`), et `uv sync` +
`pytest` confirment 183 passed / ruff propre. L'override n'est **pas** dans
l'arbre : cette story mesure, elle ne décide pas.

## Risques

| Risque | Parade |
|---|---|
| Le conflit réapparaît et impose une autre architecture | ~~documenter les options et proposer une décision, sans l'appliquer dans cette story~~ → **il réapparaît** ; options mesurées en completion notes, décision proposée (override), à acter dans un ADR |
| L'override passerait l'import mais casser à l'exécution | aucun test ici n'ouvre de connexion ; le premier test comportemental est la story 001-2, avec un vrai Neo4j |
| Le conflit `sentence-transformers` de la 001-4 est découvert trop tard | déjà mesuré et consigné ici ; la 001-4 est bloquée par le même mécanisme |