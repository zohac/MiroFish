# 0007 — Une story = un fichier, et l'état vit avec la story

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

Le premier découpage de l'epic 001 plaçait l'état et les critères de toutes les
stories dans un `stories.yaml` agrégé. Deux problèmes sont apparus :

1. **Fichier partagé** — avancer sur une story imposait d'éditer le même
   fichier que les autres : les commits se mélangent, l'historique ne dit plus
   quelle story a avancé.
2. **État dupliqué** — le statut d'une story aurait existé à la fois dans son
   contenu et dans le suivi global. Deux sources de vérité pour le même
   fait : c'est l'état qui finit par mentir.

Et rien ne garantissait que l'index d'un epic et ses fichiers de story restent
cohérents.

## Décision

**Une story = un fichier** `story-<epic>-<n>.yaml`, qui porte tout son cycle de
vie :

| Section | Contenu |
|---|---|
| `definition_of_ready` | ce qui doit être vrai **avant** de commencer |
| `definition_of_done` | ce qui doit être vrai **avant** de finir |
| `tasks` | liste de tâches avec cases à cocher |
| `notes_dev` | architecture, stratégie de test, documents de référence |
| `review.follow_ups` | points de suivi issus des revues |
| `completion_notes` | ce qui a divergé du plan, et pourquoi |

`epic-<NNN>.md` est le hub **lu en premier** : FR, NFR, UX (section qui peut
valoir « sans objet »), index des stories, liste des documents à consulter.

`sprint-status.yaml` ne porte plus que l'**agrégat par epic** : l'état d'une
story ne vit que dans son fichier.

La cohérence est **outillée** : `backend/scripts/validate_plans.py` vérifie
que l'index et les fichiers correspondent, que les champs obligatoires
existent, que les états sont connus et les `id` uniques. Il tourne en CI.

## Conséquences

**Positives**

- Un commit par story, atomique et lisible : l'historique dit *pourquoi*.
- Le contexte complet d'une story (architecture, stratégie de test, documents)
  voyage avec elle.
- La dérive entre index et fichiers est **détectée automatiquement** au lieu
  d'être découverte trois mois plus tard.

**Négatives**

- Un fichier par story **réellement démarrée** — pas imaginée, sinon la
  formalisation devient du bruit.
- Deux endroits à mettre à jour par story (son fichier et l'index de l'epic) :
  c'est précisément ce que le script de validation amortit.

## Alternatives rejetées

- **`stories.yaml` agrégé** — fichier partagé, commits mélangés, dérive.
- **Statut uniquement dans `sprint-status.yaml`** — le contenu de travail est
  séparé de son état, ce qui est contre-intuitif à relire six mois plus tard.
- **GitHub Projects comme source d'état** — boîte noire externe, double
  saisie, et aucune trace versionnée avec le code. Une liste ne remplace pas
  un plan ; au mieux elle en est une vue générée.
- **Écrire la story dans le ticket / l'issue** — même problème, hors du dépôt,
  et invisible à une session qui travaille hors ligne.