# 0013 — Sémantique des sources : statut de validation, conflits et budget de contexte

- **Statut** : accepté
- **Date** : 2026-10-11
- **Complète** : [ADR 0012](0012-contrat-de-provenance-graphstore.md), qui traite l'écriture et la lecture de la provenance
- **Préalable à** : [story 009-2](../plans/009-eligibilite-acteurs-et-sources/story-009-2.md)
- **Traite** : arbitrage 3 et R19 de la [revue de reprise](../plans/009-eligibilite-acteurs-et-sources/revue-coherence-2026-10-10.md), A03, A06, A08 de la [matrice de couverture](../plans/009-eligibilite-acteurs-et-sources/couverture-rapport-audit.md)

## Contexte

Le [rapport d'audit](../plans/009-eligibilite-acteurs-et-sources/rapport-audit-mirofish-local-first.md)
demande trois choses que le plan ne savait pas encore où mettre : un **statut de
validation** par document, une **conservation des sources contradictoires**, et
la **visibilité des troncatures** de contexte. L'[architecture](../plans/009-eligibilite-acteurs-et-sources/architecture.md)
§2.2 laissait `validation_status` en `Optional[str]` avec la mention « valeurs et
transitions à spécifier », et §9 disait du mécanisme de conflit et de la politique
de budget « à définir dans cette story ».

Trois faits du code contraignent ces décisions :

- `OntologyGenerator` échantillonne les documents longs
  (`MAX_TEXT_LENGTH_FOR_LLM = 50000`, `MAX_LONG_TEXT_CHUNKS = 60`) sans restituer
  nulle part **quels** fragments ont été retenus. Un document peut donc être
  absent d'un prompt sans que personne ne le sache.
- `SimulationConfigGenerator._build_context` tronque le texte documentaire à
  `MAX_CONTEXT_LENGTH - 500` et ajoute `...(文档已截断)` — un marqueur dans le
  texte du prompt, invisible de la programmatic.
- `additional_context` est lu par l'API, passé à l'ontologie, puis **perdu** :
  `Project` ne le persiste pas et aucune étape de simulation ne le reçoit.

Et une contrainte transverse, rappelée par NFR-5 : un contenu documentaire reste
une **donnée**. Il ne devient jamais un message système, ni une correction
d'éligibilité.

## Décision

**On fige trois sémantiques : le statut de validation est déclaratif et sans
effet d'ingestion, le conflit conserve ses deux sources et ne se résout que par
règle déclarée, et le budget de contexte est explicite avec un refus plutôt
qu'une troncature silencieuse.**

### 1. Statut de validation documentaire

Trois valeurs, dans `DocumentValidationStatus` :

| Valeur | Sens | Effet sur l'ingestion |
|---|---|---|
| `unvalidated` | **défaut**, y compris en mode simple | aucun |
| `validated` | revu par un humain | aucun |
| `conflicted` | porte une affirmation contredite | aucun |

**Aucun de ces statuts ne modifie ce qui est ingéré, ni le graphe, ni
l'éligibilité d'un acteur.** C'est le point central, et il est contre-intuitif :
un statut de validation qui filtrerait l'ingestion produirait un graphe
silencieusement amputé, ce qui est exactement le défaut que cet epic combat.

Transitions autorisées :

```
unvalidated ──▶ validated
unvalidated ──▶ conflicted
conflicted   ──▶ validated
conflicted   ──▶ unvalidated      (la contradiction a été levée)
validated    ──▶ unvalidated      (la validation a été retirée)
```

`saved_filename`, `priority`, `date`, `author`, `source` **ne changent rien** au
statut : aucun chemin de code n'en déduit une validité. Un fichier nommé
`official.pdf`, `canonical_v3.pdf` ou `source_of_truth.docx` obtient exactement
le même traitement que `notes.txt`. La fonction qui crée un `SourceDocument`
n'accepte pas de nom de fichier en entrée du tout — c'est la seule façon que
l'absence d'autorité soit structurelle plutôt que promise.

Le mode simple est le mode par défaut et reste le mode par défaut **après** cette
story : `role=facts`, `priority=1`, `date=None`, `validation_status=unvalidated`,
`author=None`, `source=None`. Aucun champ avancé n'est obligatoire.

### 2. Conflits de sources : conservation et règle déclarée

**Stockage.** Un `SourceConflict` porte :

| Champ | Sens |
|---|---|
| `conflict_id` | identifiant stable |
| `claim` | l'affirmation, en une chaîne |
| `source_references` | **les deux sources**, chacune avec `document_id`, `filename`, `role`, `priority`, `date`, `validation_status`, `chunk_index`, `char_start`, `char_end` |
| `resolution_rule` | `None`, ou l'identifiant de la règle effectivement appliquée |
| `resolution` | `None` (= « à confirmer »), ou le `document_id` retenu |
| `status` | `open` · `resolved` |

Les deux sources **coexistent toujours**. Une résolution qui n'en garderait
qu'une détruirait l'information ; `resolve_conflict` prend une règle en
argument, l'enregistre, et **conserve les deux sources**.

**Règles déclarées.** Trois règles, nommées, exposées dans le code et
listées dans la documentation — et rien d'autre :

| Règle | Effet |
|---|---|
| `validation_status` | le document `validated` l'emporte ; à égalité, « à confirmer » |
| `priority` | le `priority` le plus bas l'emporte ; à égalité, « à confirmer » |
| `recency` | la `date` la plus récente l'emporte ; à égalité ou date absente, « à confirmer » |

Trois propriétés qui les rendent déterministes et non silencieuses :

1. une règle qui ne départage pas (égalité, dates absentes) **laisse le conflit
   ouvert** avec `resolution=None` ;
2. `resolution_rule` est écrit **avec** la décision, donc une décision sans
   règle nommée est impossible à produire par l'API de ce modèle ;
3. **aucune** règle implicite n'existe. Résoudre sans passer par
   `resolve_conflict` n'est pas offert.

**Détection bornée.** `detect_conflicts` ne prétend pas être un détecteur
universel de contradictions — aucun n'est fourni par Graphiti, et la revue le
constate. Il est **borné et explicite** : il ne compare que les affirmations
qu'on lui donne, à l'intérieur d'une fenêtre de fragments proche, sur des
signaux lexicaux de polarité (`ne … pas`, `aucun`, `interdit`, `aucune
obligation`, et leurs formes anglaises). Au-delà de `max_comparisons`, il
s'arrête et **retourne le nombre de comparaisons non faites** dans
`truncated_at`. Un détecteur qui rendrait une couverture exhaustive qu'il n'a
pas serait pire que pas de détecteur.

L'affichage et l'arbitrage humain sont hors de ce lot : ils appartiennent à
[009-3](story-009-3.md), et la contradiction visible dans le rapport à
[009-4](story-009-4.md). Ici, le modèle **stocke** et **ne fusionne pas**.

### 3. Budget de contexte par étape

Un `ContextBudget` explicite, par étape, avec trois champs observables :

| Champ | Sens |
|---|---|
| `max_chars` | le plafond de l'étape |
| `used_chars` | ce qui a réellement été placé dans le prompt |
| `documents_included` | `document_id` effectivement présents |
| `documents_omitted` | `document_id` **exclus**, avec le motif |
| `chunks_sampled` / `chunks_total` | l'échantillonnage, quand il y en a eu |
| `truncated` | `True` si une partie du texte a été coupée |

**Le brief est protégé.** L'ordre de construction est : `brief`, puis entités,
puis documents documentaires. Un document ne prend jamais la place du brief. Si
le **brief lui-même** dépasse le budget de l'étape, l'étape **refuse** :

```
SimulationContextError : le brief de simulation dépasse à lui seul le budget
de l'étape « configuration » (61 203 > 50 000 caractères) ; aucun document
n'a été retiré pour le faire tenir, car retirer une consigne explicite serait
une perte silencieuse.
```

Ce refus est une exception, pas un avertissement journalisé. Un avertissement
dans un log ne change rien pour l'utilisateur ; une exception arrête l'étape
avant qu'elle ne produise une configuration à laquelle il manquait une consigne.

**Aucune troncature muette.** Les deux reduceurs existants
(`SimulationConfigGenerator._build_context`, `OntologyGenerator._excerpt_text`)
cessent d'être des réductions invisibles : chacun rend un `ContextBudget`, et
l'appelant peut donc dire *ce qui* manque. Les marqueurs in-prompt
(`...(文档已截断)`) restent, mais ils ne sont plus la seule trace.

### 4. Séparation consignes / sources

Une règle structurelle, pas une promesse :

- le texte documentaire n'entre que dans des zones de **données** des messages
  (jamais `role: "system"`), et il est présenté sous une étiquette qui énonce
  qu'il ne doit pas être exécuté ;
- les règles du `SimulationBrief` entrent dans une zone distincte, explicitement
  étiquetée « consignes », et **jamais** mélangée au texte documentaire ;
- aucune valeur extraite d'un document ne devient une règle de classification
  d'acteur. Le classifieur reçoit le brief (qui est une consigne de
  l'utilisateur) et les attributs de l'entité ; il ne reçoit pas le texte des
  sources comme consigne.

Ce que cela ne prouve pas est écrit dans le test : un test de construction de
messages vérifie la **structure**, pas l'immunité d'un LLM à une instruction
malveillante cachée dans un PDF.

## Conséquences

**Positives**

- Un nom de fichier.flatteur ne change plus rien : la structure du code l'interdit,
  pas une convention.
- Une contradiction entre deux documents est **conservée** et attend un humain ;
  elle n'est ni résolue par la date du fichier, ni fondue en une phrase moyenne.
- Un cas long produit un diagnostic nommant les documents omis, au lieu d'un
  prompt silencieusement amputé.
- `additional_context` survit enfin à l'ontologie.

**Négatives**

- Un brief de plus de 50 000 caractères **fait échouer** la génération de
  configuration là où elle aboutissait auparavant. C'est le comportement demandé,
  et c'est un changement de comportement visible : quelqu'un qui collait un
  méga-brief verra une erreur au lieu d'une configuration incomplète.
- `detect_conflicts` est lexical et borné. Il ne trouvera pas une contradiction
  exprimée autrement, et **le dit** (`truncated_at`) au lieu de laisser croire à
  une couverture.
- Trois valeurs de statut et trois transitions sous contrôle humain ne forment pas
  un système de gestion documentaire ; c'est juste assez pour 009-3 et 009-4,
  sans leur laisser deviner.

## Alternatives rejetées

**Faire du `validation_status` un filtre d'ingestion.** Un document `unvalidated`
exclu du graphe donne un graphe partiel sans trace : l'utilisateur voit des
résultats et ne sait pas ce qui manque. Le statut est déclaratif.

**Laisser la priorité ou la date trancher un conflit silencieusement.** C'est
précisément la demande A06 : priorité/date ne résolvent **que si une règle
déclarée s'applique**, et la décision cite cette règle. Trancher sans règle
produirait un rapport qui affirme une chose et cache pourquoi.

**Écrire un détecteur de contradiction universel.** Aucun n'existe dans
Graphiti, et un détecteur de contradiction par LLM coûterait un appel par paire
de faits. La version bornée et explicite dit ce qu'elle ne couvre pas.

**Rendre le refus de brief long optionnel.** Une option que personne ne coche
est un avertissement de plus. L'erreur est la seule forme qui empêche vraiment
de produire une configuration amputée.

**Réutiliser `additional_context` comme brief.** `additional_context` est une
seule chaîne libre ; le brief a douze champs versionnés. Les confondre ferait
perdre la structure, et le champ perdu reviendrait par un autre chemin.

## Références

- [`story-009-2.md`](../plans/009-eligibilite-acteurs-et-sources/story-009-2.md) — la story qui implémente cet ADR
- [`architecture.md`](../plans/009-eligibilite-acteurs-et-sources/architecture.md) §2.2 et §9 — les sections que cet ADR fige
- [ADR 0012](0012-contrat-de-provenance-graphstore.md) — le contrat d'écriture et de lecture de la provenance
- [revue de reprise](../plans/009-eligibilite-acteurs-et-sources/revue-coherence-2026-10-10.md) — R19, arbitrage 3
- `backend/app/services/simulation_config_generator.py`, `backend/app/services/ontology_generator.py` — les deux reduceurs dont les limites deviennent visibles