---
id: "001-1b"
epic: "001"
titre: "Poser l'override-dependencies du driver neo4j"
statut: in-progress
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

- [ ] `override-dependencies = ["neo4j>=5.26.0,<6.0.0"]` est dans `backend/pyproject.toml`, avec la **version effectivement résolue** écrite dans un commentaire juste à côté — ADR 0011
- [ ] `graphiti-core` est une dépendance **produit**, **sans extra**
- [ ] **L'override ne couvre que `neo4j`** : `sentence-transformers` et `torch` sont inchangés dans le lock — règle 1 de l'ADR 0010, qui ne concerne pas la 001-4
- [ ] `uv lock` résout et `uv sync --frozen` réussit — c'est ce que fait l'image Docker (AGENTS.md §2.5, §6)
- [ ] `oasis`, puis `neo4j`, puis `graphiti_core` s'importent **dans cet ordre**, dans le même interpréteur
- [ ] La version résolue est confrontée à celle consignée dans l'ADR 0011 ; si elle diffère, l'écart est **écrit quelque part de visible**, pas laissé dans un lock
- [ ] Le filet de tests est vert et ne rétrécit pas (192 au départ), et **un test nouveau** garde le périmètre de l'override — sans quoi la règle 1 de l'ADR 0010 n'est gardée par rien
- [ ] `mesurer-001-1.sh` **reste rejouable** sur l'arbre après override, et c'est vérifié en le lançant
- [ ] Réversibilité vérifiée : `git checkout backend/pyproject.toml backend/uv.lock` ramène à l'état initial, et `uv lock` **échoue** sans l'override — c'est la preuve du conflit, pas une restauration du lock
- [ ] `ruff`, `validate_plans.py` et `pytest` verts ; `uv.lock` régénéré **et commité**
- [ ] La version résolue et le propriétaire de la revalidation sont consignés dans [`deferred-work.md`](../../../deferred-work.md) — l'override promet une compatibilité que rien ne surveille

## Tâches

- [ ] 1. Ajouter `graphiti-core` aux dépendances produit de `backend/pyproject.toml` — **pas** `graphiti-core[sentence-transformers]`
- [ ] 2. Ajouter la table `[tool.uv]` avec `override-dependencies = ["neo4j>=5.26.0,<6.0.0"]`, en fin de fichier, et laisser un commentaire pour la version résolue
- [ ] 3. `uv lock` puis `uv sync`, puis **commiter `uv.lock`** : l'image fait `uv sync --frozen` et échoue sur un lock désynchronisé (AGENTS.md §2.5)
- [ ] 4. Vérifier `uv sync --frozen` dans un venv propre, et `uv tree --invert --package neo4j` pour documenter qui tire quoi
- [ ] 5. Vérifier les imports dans l'ordre, et que `sentence-transformers` / `torch` n'ont pas bougé d'une version
- [ ] 6. Relever la version résolue, la confronter à l'ADR 0011, l'écrire dans le commentaire de `pyproject.toml`
- [ ] 7. Rendre `mesurer-001-1.sh` rejouable **sur l'arbre après override** — voir les notes de développement, le script casse pour deux raisons
- [ ] 8. Ajouter le test qui garde le périmètre de l'override, puis relancer la suite entière

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

Suivis éventuels : _aucun pour l'instant._

## Notes de complétion

_À remplir à la fin : ce qui a divergé du plan, et pourquoi._

## Risques

| Risque | Parade |
|---|---|
| L'override déborde sur `sentence-transformers` et tranche la 001-4 sans le dire | règle 1 de l'ADR 0010 + un test qui refuse un override plus large que `neo4j` |
| La borne résout une autre version à la 001-2 qu'à l'application | version résolue écrite dans `pyproject.toml`, et confrontée à l'ADR 0011 avant de passer en revue |
| `uv.lock` régénéré mais non commité | `uv sync --frozen` est dans la définition de fini ; c'est lui qui échoue dans l'image |
| `mesurer-001-1.sh` devient inutilisable et personne ne s'en aperçoit | rejouabilité dans la définition de fini, **vérifiée en le lançant** — pas en lisant le script |
| L'override tient au lock et casse à l'exécution | ce n'est pas le risque de cette story : c'est celui de la 001-2, et il est assumé dans l'ADR 0010 |
