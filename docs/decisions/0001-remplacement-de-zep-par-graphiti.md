# 0001 — Remplacer Zep par Graphiti + Neo4j derrière une interface

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

Zep Cloud est le **graphe de connaissances temporel** du projet : il extrait
les entités et relations des documents, alimente la configuration de
simulation, enrichit les personas, enregistre les événements des tours de
simulation, et alimente les outils du rapport (`docs/LOCAL-FIRST.md` §3).

C'est le seul poste payant du projet, et il est proportionnel au volume
d'épisodes envoyés. Zep Community Edition (auto-hébergé) est **déprécié**
depuis avril 2025 et son dépôt est archivé. La voie OSS est **Graphiti**, le
moteur qui fait tourner Zep Cloud lui-même, sous licence Apache-2.0, et qui
gère la temporalité nativement (`valid_at`, `invalid_at`, `expired_at`).

Le coût du graphe n'est pas le même que celui des crédits Zep : l'extraction
devient **un travail de LLM que nous payons nous-mêmes**. Avec un LLM gratuit,
l'échange reste net.

## Décision

On remplace Zep par **Graphiti + Neo4j en local**, derrière une interface à
deux implémentations (`ZepGraphStore` et `GraphitiGraphStore`), sélectionnées
par une variable d'environnement (`ZEP_BACKEND`).

**Zep reste pleinement fonctionnel** pendant toute la validation du chemin
local. Pas de bascule big-bang.

## Conséquences

**Positives**

- Zéro crédit Zep, et des données qui ne quittent pas la machine.
- Temporalité native : c'est le différenciant du projet (§3), un graphe sans
  temporalité ne peut pas répondre à « qui était PDG, et jusqu'à quand ».
- Les 154 tests existants servent de filet : ils décrivent le contrat Zep et
  doivent rester verts des deux côtés.

**Négatives / coût**

- L'extraction d'entités passe à notre charge : latence, et CPU pour l'embedder
  et le reranker.
- Neo4j est une brique à opérer (2–4 Go de RAM, un service de plus).
- Le domaine Zep fuite dans **10 fichiers** ; il faut le faire disparaître
  progressivement derrière l'interface, sans jamais le disséminer davantage.

**Point ouvert**

- Le conflit potentiel de version du driver Neo4j entre `camel-oasis` et
  `graphiti-core` doit être vérifié avant d'ajouter la dépendance
  (`docs/LOCAL-FIRST.md` §11, point 4).

## Alternatives rejetées

- **Zep Community Edition auto-hébergé** — déprécié, dépôt archivé. Impossible
  de construire une base dessus.
- **Remplacer Zep par des fichiers JSON** (PR #634, fermée non mergée le
  3 octobre 2026) — supprime la recherche sémantique au profit d'une recherche
  par mots-clés. Régression fonctionnelle sur le cœur du produit.
- **Garder Zep** — coût par épisode, données chez un tiers, et le quota
  gratuit est plafonné.
- **Une base Neo4j par simulation** plutôt qu'un partitionnement par
  `group_id` — une base par simulation complique le partage et l'outillage ; le
  partitionnement suffit, et c'est ce que le fork de référence retenait.