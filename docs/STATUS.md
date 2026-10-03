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
| C1 | Épisodes extraits sans erreur | **≥ 9 sur 10** chunks |
| C2 | Échecs d'authentification (`MissingSessionID`) | **0** |
| C3 | Graphe non vide **et relisible après redémarrage de Neo4j** | ≥ 1 entité, ≥ 1 relation persistées |
| C4 | Temporality : `valid_at` renseigné | ≥ 1 arête |
| C5 | Rapport de mesure versionné dans le dépôt | 1 fichier |

**Règle de décision** : si C1 ou C2 échoue, on s'arrête là. Pas de migration
partielle sur une extraction qui ne fonctionne pas. Le repli est alors
l'extraction sur un modèle payant ponctuel, moins cher que des crédits Zep.

## Prochain pas

1. **Migrer l'epic 001 vers la nouvelle structure** (ADR 0007) : `epic-001.md`
   (FR / NFR / UX, index des stories, documents à consulter), un
   `story-001-<n>.yaml` par story démarrée, et le script de validation branché
   en CI. Le constitution l'exige, l'epic ne peut pas démarrer avant.
2. Vérifier le conflit `graphiti-core` vs `camel-oasis` (story 001-1) — s'il
   existe, il change le périmètre (venv séparé ou service isolé).
3. Document de test : **à fournir**. Un PDF ou un texte réel d'au moins 10
   chunks de 500 mots. C'est le seul élément bloquant côté entrée.

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
| ADR | 7 acceptés, 0 supersédé |
| Environnement de référence | Docker dès que l'epic 005 est fait (ADR 0006) — en attendant, on travaille en local, et c'est dit |
| Fork audités | 6 — 0 adopté |