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

1. **Story 001-1** — le conflit `graphiti-core` vs `camel-oasis`. C'est le
   prochain vrai risque : chez `tt-a1i`, ce point avait imposé un second venv
   *et* un sous-processus. Fichier prêt : [`story-001-1.yaml`](plans/001-epreuve-graphiti-local/story-001-1.yaml).
2. Puis 001-2 (Neo4j) et 001-3 (en-tête de session) — les deux autres risks
   de l'épreuve.
3. L'épreuve elle-même, et son verdict.

## Questions ouvertes

| Question | Effet si la réponse change |
|---|---|
| Le graphe Zep actuel contient-il quelque chose à garder ? | Epic 006 : migration possible ou non |
| `camel-oasis` et `graphiti-core` sont-ils compatibles dans un venv ? | venv séparé, ou changement d'architecture |
| La politique d'usage de l'endpoint gratuit tient-elle à ce volume ? | extraction sur un modèle payant |
| Le reranker supporte-t-il cet endpoint (logprobs) ? | repli RRF, comme Zep le fait déjà |

## Chiffres de référence

| | |
|---|---|
| Tests | 154, tous verts, **sans `.env`** |
| Lint | ruff, règles volontairement étroites (amont) |
| Amont | `666ghj/MiroFish` — AGPL-3.0, très actif |
| ADR | 8 acceptés, 0 supersédé |
| Node | pnpm 10.23.0, version figée dans `packageManager`, `package-lock.json` supprimés |
| Environnement de référence | Docker dès que l'epic 005 est fait (ADR 0006) — en attendant, on travaille en local, et c'est dit |
| Fork audités | 6 — 0 adopté |