# État du projet

Une page, mise à jour à chaque changement d'epic. La source de vérité est
[`sprint-status.yaml`](../sprint-status.yaml) — ce fichier en est la **vue
humaine**, pas un second saisie.

> Dernière mise à jour : **3 octobre 2026** · branche `local-first`

---

## Où on en est

Le **cadrage est terminé** : constitution du projet (`AGENTS.md`), audit des
forks communautaires, cinq décisions d'architecture figées, CI qui lance les
tests et le lint. Le **prochain jalon est l'épreuve Graphiti** — mesurer si
le modèle gratuit tient l'extraction structurée, avant d'investir deux à
quatre jours de migration.

## Fait

| Livrable | Où |
|---|---|
| LLM branché sur l'endpoint gratuit, en-têtes de session compris | commit `28c61d0` |
| Travail sécurisé : branche `local-first`, tag de sauvegarde, fork `zohac/MiroFish` | commits `28c61d0`, `50e9826` |
| Analyse Zep : rôle, rayon d'impact, obstacles | `docs/LOCAL-FIRST.md` §3–§6 |
| Audit des 6 forks communautaires | `docs/LOCAL-FIRST.md` §12 |
| 5 ADR — Graphiti, forks, ontologie, LLM, licence | `docs/decisions/` |
| 7 ADR — + Docker-first, structure par story | `docs/decisions/0006`, `0007` |
| 8 ADR — + pnpm (Node), version figée dans `packageManager` | `docs/decisions/0008` |
| Constitution, suivi, CI + lint ruff | `AGENTS.md`, `sprint-status.yaml`, `.github/workflows/ci.yml` |

## En cours

**Epic 001 — Épreuve Graphiti local** (le seul point de rupture du projet).
Plan : [`docs/plans/001-epreuve-graphiti-local/`](plans/001-epreuve-graphiti-local/prd.md)

La story **001-1 est `done`** : le conflit `graphiti-core` / `camel-oasis` est
réel et structurel, la parade est mesurée et rejouable
([`mesurer-001-1.sh`](plans/001-epreuve-graphiti-local/mesurer-001-1.sh)), la
décision est actée par l'ADR 0010 et précisée par l'ADR 0011. Cinq points de sa
revue sont restés différés : [`deferred-work.md`](../deferred-work.md).

La story **001-1b est `review`** : l'`override-dependencies` du driver est posé
dans `backend/pyproject.toml`, avec `graphiti-core==0.30.2` **sans extra**, et le
lock est régénéré et commité. `neo4j 5.28.6` résolue — la version que l'ADR 0011
avait consignée, sans écart. **204 tests verts.**

Le point difficile n'était pas la déclaration : c'est que poser l'override
**cascait le protocole de mesure de la 001-1**. Il ne casse plus — il **normalise**
`pyproject.toml` dans l'état qu'il veut mesurer, puis restaure l'octet initial,
et **refuse** un arbre ambigu au lieu de le deviner. Rejoué sur les deux arbres,
204 tests verts à chaque fois.
[`story-001-1b.md`](plans/001-epreuve-graphiti-local/story-001-1b.md).

## À faire

| Epic | Titre | Dépend de |
|---|---|---|
| 002 | Interface `GraphStore` + `ZepGraphStore` + factory | 001 |
| 003 | `GraphitiGraphStore` : écriture et chemin de lecture | 001, 002 |
| 004 | Construire un graphe sans clé Zep — la preuve finale | 003 |
| 005 | Docker local : Neo4j dans le compose | 003 |
| 006 | Migrer le graphe Zep existant — ou acter qu'on jette | 003 |
| 007 | Ontologie dynamique (v2) | 003 |

---

## Critères de succès de l'épreuve — chiffrés, sinon « ça tient » ne veut rien dire

| # | Critère | Seuil |
|---|---|---|
| C1 | Épisodes extraits sans erreur | **≥ 27 sur 30** chunks (90 %) |
| C2 | Échecs d'authentification (`MissingSessionID`) | **0** |
| C3 | Graphe non vide **et relisible après redémarrage de Neo4j** | ≥ 1 entité, ≥ 1 relation persistées |
| C4 | Temporalité : `valid_at` renseigné | ≥ 1 arête |
| C5 | Rapport de mesure versionné dans le dépôt | 1 fichier |

Échantillon : les 30 premiers chunks du rapport n° 2506 de l'Assemblée
nationale (URL et sha256 dans le PRD de l'epic 001).

**Règle de décision** : si C1 ou C2 échoue, on s'arrête là. Pas de migration
partielle sur une extraction qui ne fonctionne pas. Le repli est alors
l'extraction sur un modèle payant ponctuel, moins cher que des crédits Zep.

## Prochain pas

1. **Story 001-2** — Neo4j 5.26 + APOC en local, avec volumes nommés. C'est le
   **premier test comportemental du driver forcé** : personne n'a encore ouvert
   de connexion sous cet override. La surface est relevée (ADR 0011),
   l'exécution ne l'est pas — et c'est 001-2 qui tranche l'ADR 0010, par
   supersession s'il casse. Elle dispose maintenant de `neo4j 5.28.6` lockée,
   version que l'override a résolue et que `pyproject.toml` consigne.
2. Puis 001-3 (en-tête de session) et 001-4 (embedder) — les deux autres risques
   de l'épreuve. 001-4 reste **bloquée par le même conflit** que le driver
   (`sentence-transformers==3.0.0` contre `>=3.2.1`), avec son propre arbitrage :
   l'ADR 0010 ne couvre que `neo4j`, et un test
   (`backend/tests/test_pyproject_override.py`) refuse qu'on l'élargisse en
   silence.
3. L'épreuve elle-même, et son verdict.

> La 001-1b reste en `review` : le geste est posé, testé et mesuré, mais une
> relecture est due avant de la passer en `done`
> ([`story-001-1b.md`](plans/001-epreuve-graphiti-local/story-001-1b.md)).

## Questions ouvertes

| Question | Effet si la réponse change |
|---|---|
| Le graphe Zep actuel contient-il quelque chose à garder ? | Epic 006 : migration possible ou non |
| ~~`camel-oasis` et `graphiti-core` sont-ils compatibles dans un venv ?~~ | **répondu non** (story 001-1) — parade mesurée et rejouable : override du driver, **actée par l'ADR 0010**, précisée par l'ADR 0011 |
| Le driver `neo4j` forcé à **5.28.6** tient-il **à l'exécution** ? | 001-2 est le premier test ; s'il casse, l'ADR 0010 est supersédé et on bascule sur un venv séparé. La version est lockée et **consignée dans `pyproject.toml`**, donc 001-2 teste bien celle qui sera déployée |
| `sentence-transformers` : même conflit que `neo4j` ? | **oui, mesuré** — bloque la story 001-4, arbitrage propre à faire, l'ADR 0010 ne la couvre pas |
| La politique d'usage de l'endpoint gratuit tient-elle à ce volume ? | extraction sur un modèle payant |
| Le reranker supporte-t-il cet endpoint (logprobs) ? | repli RRF, comme Zep le fait déjà |

## Chiffres de référence

| | |
|---|---|
| Tests | **204**, tous verts, **sans `.env`** (192 avant la story 001-1b ; 183 avant les neuf tests de revue du 3 octobre) |
| Lint | ruff, règles volontairement étroites (amont) |
| Amont | `666ghj/MiroFish` — AGPL-3.0, très actif |
| ADR | 11 acceptés, 0 supersédé |
| Node | pnpm 10.23.0, version figée dans `packageManager`, `package-lock.json` supprimés |
| Environnement de référence | Docker dès que l'epic 005 est fait (ADR 0006) — en attendant, on travaille en local, et c'est dit |
| Fork audités | 6 — 0 adopté |