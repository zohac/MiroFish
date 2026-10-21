# Revue aveugle indépendante — campagne `benchmark-013-20261020-203040`

> **Évaluateur** : ChatGPT (OpenAI), session neuve, contexte sans accès à la
> correspondance.
> **Date** : 21 octobre 2026.
> **Verdict global** : *« aucune des deux variantes ne peut être considérée
> comme factuellement validée »* ; *« la variante A est un peu plus prudente sur
> les limites de la simulation »*, *« la variante B développe davantage
> certaines trajectoires, au prix d'affirmations de souscription
> particulièrement problématiques »*.

Cette revue est **distincte** de celle versée dans `grille-aveugle.md`, qui
avait été produite par un agent de la session de développement ayant déjà lu
la correspondance. Elle en constitue la ** confirmation indépendante**.

---

## 1. Réserve de méthode — les pièces jointes étaient en partie erronées

L'évaluateur a constaté que les **fichiers de preuve transmis ne
correspondaient pas aux deux variantes** : ils portaient
`simulation_id: sim_ea4f3cfe1028` et 258 affirmations, c'est-à-dire l'exécution
**R6** (`backend/tests/fixtures/qualification_epic_012/r6_bundle/` et
`backend/uploads/reports/report_77d96ea4c1c9/`), et non la campagne courante.

Les fichiers corrects portent `simulation_id: sim_80a54d7bbd7b`, 159
affirmations (variante A) et 178 (variante B) :

| Pièce | `simulation_id` | `total_claims` | Statut |
|---|---|---|---|
| `report_108186c7524b/report_claims.json` (A) | `sim_80a54d7bbd7b` | 159 | `needs_review`, `is_publishable: false` |
| `report_ccf28321dcb8/report_claims.json` (B) | `sim_80a54d7bbd7b` | 178 | `needs_review`, `is_publishable: false` |

**Conséquence, énoncée par l'évaluateur** : les `claim_id` et les statuts de
publication des variantes n'ont pas pu être confrontés, donc les notes des
critères **1 (exactitude factuelle)** et **5 (contraintes de publication)** sont
**provisoires**. Les critères 2, 3 et 4 reposent sur les rapports eux-mêmes et
sur le tableau de cohorte qu'ils publient : ils sont **exploitables**.

**Ce que la réserve ne touche pas** : le verdict global et la comparaison
A/B reposent sur des faits vérifiables dans les textes mêmes des rapports
(arc d'Émilie attribué malgré 0 action, souscriptions contredites par le
tableau de cohorte du rapport, section « Sources & Provenance » sur-certifiée,
garanties produit non établies). Tous sont dans le périmètre que
l'évaluateur a pu traiter.

## 2. Notes par critère

| # | Critère | Note A | Note B |
|---|---|---|---|
| 1 | Exactitude factuelle vérifiable | 1 | 0 |
| 2 | Couverture de la cohorte | 2 | 2 |
| 3 | Explicitation des limites et objections | 3 | 2 |
| 4 | Lisibilité et structure | 4 | 4 |
| 5 | Respect des contraintes de publication | 1 | 1 |

À comparer avec la revue versée dans `grille-aveugle.md` (A : 1/2/3/3/3 ;
B : 1/2/3/3/2). Les deux revues **convergent** sur le fond :

- même note globale (2/5 pour chaque variante) ;
- B **jamais supérieure** à A, et **inférieure** sur l'exactitude (0 contre 1)
  et sur les limites (2 contre 3) ;
- mêmes erreurs matérielles jugées décisives.

Les écarts de notation portent sur des critères de **forme** plus que de
fond : la lisibilité (4/5 pour l'évaluateur externe, 3/5 pour l'agent) et les
contraintes de publication (1/5 pour l'évaluateur externe, plus indulgent pour
l'agent sur la conformité des clauses produit). L'évaluateur externe a été
plus sévère sur les **garanties produit non établies** (« exportation
intégrale des fiches au format CSV », « paiement Stripe désactivable par
prestation », « parcours à trois clics »), que l'agent avait créditées au
contraire.

## 3. Erreurs matérielles relevées par l'évaluateur indépendant

**Communes aux deux variantes** (10 pour A, 12 pour B) :

- des **souscriptions non démontrées** que le rapport contredit lui-même par
  son tableau de cohorte (A : adoption de Nathalie et Sylvie ; B : adhésion
  payante de Nathalie, souscription de Christine) ;
- l'**arc d'Émilie attribué** (0 action, `present_no_action`) : « décision non
  observée », « parole présentée comme observée malgré 0 action » ;
- des **citations longues non authentifiées** (0 sur 17 en A, 0 sur 31 en B
  retrouvées dans les actions accessibles) ;
- des **garanties produit non établies** : export CSV intégral, désactivation
  du paiement Stripe par prestation, « trois clics » ;
- une **catégorie de provenance erronée** : la perte de 1 500 € d'Émilie — un
  persona fictif — est placée sous `[Contexte documentaire historique]` ;
- la **certification de traçabilité non démontrée** : « toute affirmation
  qualifiée d'action observée est reliée à un événement horodaté », sans
  `event_id` dans le texte.

**Propres à B** : la souscription explicite de Christine (B-02, jugée « l'erreur
matérielle la plus grave des deux variantes ») et une **contradiction interne**
(B-11) — des objections persistantes sur le paiement obligatoires, après avoir
affirmé qu'elle avait souscrit grâce à sa désactivation.

**Propres à A** : l'ajournement attribué à Christine, alors que les preuves
montrent une résolution.

## 4. Point nouveau — une confusion **amont** des biographies de départ

L'évaluateur a relevé que l'épisode « 1 500 € / WordPress » — qui appartient à
la fiche de départ d'**Émilie** — est repris par **Nathalie** dans les traces
de R7, et qu'A comme B l'attribuent à Nathalie. La confusion précède donc le
rapport : elle est dans le **brief** lui-même. *À traiter avec les trois
défauts de pipeline déjà consignés dans `docs/deferred-work.md`.*

## 5. Ce que l'évaluateur n'a pas pu vérifier

1. Les `claim_id` et les statuts de publication propres à chaque variante
   (pièces erronées).
2. L'authentification des citations d'entretiens (les traces de `interview_agents`
   ne sont pas dans le journal social).
3. La chronologie exacte des changements d'avis.
4. La réalité des souscriptions et paiements : *« aucune preuve transactionnelle
   n'a été fournie pour les conversions affirmées »*.
5. La conformité complète du processus de génération.

## 6. Ce que cette revue change — et ce qu'elle ne change pas

**Elle ne change pas la décision.** Le critère du PRD source §8 — *« choisir
`high` si la revue aveugle montre une réduction claire des erreurs
matérielles et des citations non fondées »* — n'est **pas** rempli : les deux
variantes sont à 2/5, les erreurs majeures sont communes, et la variante `high`
est **jamais** supérieure à `medium` (inférieure sur deux critères dans les
deux revues). **La configuration par défaut reste `medium`.**

**Elle change la confiance qu'on peut accorder aux notes 1 et 5**, qui
restent provisoires tant que les pièces n'ont pas été corrigées. La
procédure a donc été durcie : `consigne-revue-aveugle.md` exige désormais de
**vérifier le `simulation_id` des pièces jointes** avant l'envoi, et de
n joindre que la liste de fichiers qu'il énumère.
