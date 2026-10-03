# 0009 — Les fichiers de story sont du markdown, pas du YAML

- **Statut** : accepté
- **Date** : 2026-10-03

> Précise l'ADR 0007, qui reste valable : une story = un fichier, et l'état
> vit avec elle. Seule la **forme du fichier** change. La mention `.yaml` dans
> l'ADR 0007 est caduque ; la décision qu'elle portait, elle, tient.

## Contexte

La première version des fichiers de story était en YAML. En rédigeant la
story 001-1, le coût est apparu immédiatement : une Definition of Ready, une
stratégie de test, des notes d'architecture, des risks, des completion notes —
tout ça est de la prose. En YAML, chaque paragraphe devenait un bloc `>-` à
échapper, chaque task une liste de deux clés, et le diff d'une phrase
réécrite était illisible.

Le pire : le fichier n'était plus lisible dans l'interface de GitHub sans une
extension, alors que c'est là qu'on le relit.

## Décision

`story-<epic>-<n>.md` : **du markdown**, avec un petit en-tête
machine-readable en tête.

```markdown
---
id: "001-1"
epic: "001"
titre: "…"
statut: backlog
auteur: agent
---

# Story 001-1 — …

## Definition of Ready
- [x] …

## Tasks
- [ ] 1. …

## Completion notes
_…_
```

> **Périmètre de cet ADR.** L'illustration ci-dessus est celle de la décision
> d'origine, et elle n'a pas été retouchée depuis : cet ADR est immuable
> (AGENTS.md §2.3). Les six sections y portent donc encore les titres anglais.
> C'est [`AGENTS.md` §2.10](../../../AGENTS.md) qui fait foi pour les titres en
> français, et [`ADR 0011`](0011-titres-de-sections-en-francais.md) qui explique
> pourquoi le validateur les exige désormais — et comment un fichier écrit avant
> cette décision est diagnosed. **Ne pas recopier cette illustration telle
> quelle** dans un fichier de story.

L'en-tête ne contient que ce qui doit être **lu par une machine** :
l'identité, l'epic, l'état, l'auteur. Tout le reste est de la prose, des cases
à cocher et des tableaux — lisibles, diffables, commentables.

## Conséquences

**Positives**

- Une story s'écrit et se relit comme une note. Les cases à cocher sont
  natives (`- [ ]` / `- [x]`), donc le suivi est lisible par un humain sans
  outillage.
- Le diff reste lisible : réécrire une phrase ne touche qu'une ligne.
- L'en-tête minuscule ne coûte rien à écrire et garde le strict nécessaire
  automatisable.

**Négatives**

- Le parseur de story (`validate_plans.py`) dépend maintenant d'un front
  matter plus de sections. Il les vérifie une par une, et **échoue** si l'une
  manque — pas de dégradation silencieuse.
- Une section mal orthographiée (`Completion notes` écrit `Completion
  Note`) passe inaperçue tant qu'elle n'est pas obligatoire pour l'état
  courant. Acceptable : les six sections sont vérifiées à chaque run.

**Note d'implémentation.** Le contrôle des tâches se fait sur les cases à
cocher de la section `Tasks` : une story en `review` ou `done` ne doit plus
avoir de case ouverte. Et une story `done` dont les completion notes
contiennent encore « à remplir » est refusée — c'est le moyen le plus simple
d'empêcher un `done` qui n'a rien documenté.

## Alternatives rejetées

- **YAML pur** — l'état initial. Illisible en prose, diff illisible, pas
  lisible sur GitHub sans extension.
- **Markdown pur, statut dans le corps** — aurait supprimé le front matter,
  mais il aurait alors fallu lire l'état au regex dans une ligne de prose.
  Une ligne de métadonnées est plus sûre qu'une convention de relecture.
- **Markdown avec une table de métadonnées** — lisible, mais pas
  machine-readable sans parsing d'une table, donc retour au regex.
- **Un outil de ticket tracker** (GitHub Issues en fichier) — même
  problème qu'une liste : hors du dépôt, invisible hors ligne, et double
  saisie avec le code.