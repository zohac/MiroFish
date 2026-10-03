---
id: "001-1"
epic: "001"
titre: "Vérifier le conflit graphiti-core vs camel-oasis"
statut: backlog
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

- `graphiti-core` est résolu sans conflit dans `backend/.venv`
- `camel-oasis` et le driver `neo4j` sont importables dans le même interpréteur, **dans cet ordre**
- Les 154 tests sont toujours verts
- Le résultat est consigné dans les completion notes ci-dessous — **y compris si c'est un échec**
- Si un conflit existe : options documentées (venv séparé, service isolé) et décision proposée

## Tasks

- [ ] 1. Ajouter `graphiti-core` aux dépendances produit de `backend/pyproject.toml`
- [ ] 2. Régénérer le lock (`uv lock`) — le Dockerfile utilise `--frozen`
- [ ] 3. `uv sync`, puis vérifier qu'aucun conflit de version n'apparaît
- [ ] 4. Importer `camel-oasis` puis `neo4j` dans le même interpréteur
- [ ] 5. Lancer `pytest tests/ -q` et confirmer 154 passed

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

_À remplir à la fin : ce qui a divergé du plan, et pourquoi._

## Risques

| Risque | Parade |
|---|---|
| Le conflit réapparaît et impose une autre architecture | documenter les options (venv séparé, service isolé) et proposer une décision, sans l'appliquer dans cette story |