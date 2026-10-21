# Grille de revue aveugle — campagne `benchmark-013-20261020-203040`

> Campagne : `sim_80a54d7bbd7b` · Variantes notables : A, B
> Grille de score du banc : version `1.1.0`.

## Qui a jugé, et ce que cela vaut

**Évaluateur : un agent de la session de développement** (OpenCode), et non un
évaluateur humain indépendant. Deux lectures parallèles, une par variante, ont
confronté chaque rapport aux preuves du jeu figé (registre d'affirmations,
contrôles de publication, couverture de cohorte, `actors.json`,
`simulation_config.json`, journaux d'actions des deux plateformes).

**Limite à énoncer franchement** : l'agent évaluateur avait déjà **lu la
correspondance** (`correspondance.json`) pendant la vérification de la
campagne. La notation ci-dessous a donc été derivée de la **lecture des
rapports et de la confrontation aux preuves**, pas d'une ignorance de
l'identité technique — mais **ce n'est pas une revue aveugle indépendante** au
sens du PRD source (§8, §12.5).

**Conséquence** : cette grille **informe** la décision de changement de modèle ;
elle ne l'**autorise** pas. L'évaluation indépendante — un évaluateur humain, ou
une session distincte qui n'a jamais vu la correspondance — reste requise
avant de basculer la configuration par défaut. La consigne à transmettre est
dans `consigne-revue-aveugle.md`.

---

## 1. Notes par critère

| # | Critère | Note A | Note B | Commentaire |
|---|---|---|---|---|
| 1 | Exactitude factuelle vérifiable | 1 | 1 | Les deux registres sont à ~0 % de vérification (A : 0/159 vérifiée ; B : 1/178). Aucune citation entre guillemets n'est verbatim du corpus. Les deux attribuent à **Émilie** un arc qu'elle n'a pas (0 action observée). |
| 2 | Couverture de la cohorte | 2 | 2 | Le tableau des 18 membres est exact dans les deux cas. Mais la prose **omet Marie-Claude** (24 actions, seul récit d'adoption réussi du run) et **contredit son propre tableau** sur les souscriptions. |
| 3 | Explicitation des limites et objections | 3 | 3 | Section présente et structurée dans les deux cas, avec des objections réelles. Aucune des deux ne dit la limite la plus grave : 0 adoption constatée et publication non certified. |
| 4 | Lisibilité et structure | 3 | 3 | Français correct, progression claire, sections obligatoires présentes. Défauts : redondance, étiquetage épistémique appliqué parcialmente, citations dupliquées. |
| 5 | Respect des contraintes de publication | 3 | 2 | Prix, sous-domaine, rôles réels/pilotes, absence de promesse inventée : respectés dans les deux. B applique en revanche `[Événements simulés réels]` à des entretiens menés **pendant** la rédaction, et pose une question d'entretien qui **présuppose la conversion** (règle C du brief). |

**Note globale : A = 2/5, B = 2/5.** Aucune réduction claire des erreurs
matérielles en `high`.

## 2. Erreurs matérielles communes aux deux variantes

1. **L'arc « Émilie » est fabriqué dans les deux rapports.** Émilie a
   **0 action observée** et le statut `present_no_action` ; son dossier porte
   `eligibility_status: review`. Les deux rapports lui attribuent un refus
   catégorique, des citations, une section entière, et l'un des deux l'oppose
   explicitement à Hélène. Limite inscrite au registre : « *Règle de silence C7 :
   aucune action ne peut lui être imputée.* »
2. **Les citations « verbatim » ne le sont pas.** A : 17 citations, aucune
   verbatim (dont deux formulations sans aucune source, attribuées à Hélène et
   Sylvie). B : 31 citations, aucune verbatim (dont trois sans aucune source,
   dont deux attribuées à des personas qui n'ont pas été interrogées).
3. **Les deux rapports affirment des souscriptions que leur propre tableau de
   cohorte contredit.** `adoption_rate = 0.0`, `adoption_denominator = 12`,
   11 rejets exprimés — et le tableau affiche `Rejected` pour les personas que
   la prose déclare adoptants.
4. **La section « Sources & Provenance » certifie une traçabilité que le
   registre du même rapport nie.** « Toute affirmation d'action observée est
   reliée à un événement horodaté » — alors que **0 affirmation sur 159 (A) et
   178 (B) ne porte d'`evidence_refs`**, et que 7 (A) / 8 (B) sont
   `CONTRADICTED`.
5. **Marie-Claude n'apparaît qu'une fois**, dans le tableau, alors qu'elle
   porte 24 actions et le seul adoptant du run.
6. **Le thème « absence d'essai gratuit »** (A) et les chiffres « 8 à 15
   consultations », « 300 à 400 € de chiffre d'affaires » (B) ne sont pas dans
   le corpus : ce sont des prémisses du **brief** présentées comme des faits
   observés.

## 3. Erreurs propres à chaque variante

**Variante A**
- Projection hors horizon temporel (« à 30 ou 60 jours », l. 260) —
  interdit par la règle A du brief.
- Ancre « 48 premières heures » (l. 115) non attestée : le run observé
  s'arrête à 40 h.
- Brieffé par le graphe : le rapport tranche en faveur d'une arête de graphe
  (« Simon accompagne Émilie ») alors qu'Émilie n'a aucune action, sans
  signaler que le graphe n'est pas dans l'empreinte.

**Variante B**
- **24 de ses 31 citations** proviennent d'entretiens menés **pendant la
  rédaction** du rapport : hors du jeu de preuves figé, et présentées comme
  `[Événements simulés réels]`. C'est la faute méthodologique la plus lourde
  des deux campagnes.
- Une **question d'entretien présuppose la conversion** (« À quel moment
  précis ce double soutien humain a déclenché le passage à l'action ? ») —
  violation directe de la règle C du brief (« aucune conversion supposée
  acquise »), et le rapport rapporte la présupposition comme un résultat.
- « Aucun document source structuré rattaché au projet » est **faux** : le
  manifeste en compte 3.
- Incohérence arithmétique interne : 75 €/séance dans une section, 190 €/séance
  dans une autre du même rapport.

## 4. Points propres, à créditer

- Prix et clauses conformes au brief dans les deux rapports (29 € TTC/mois,
  sans engagement, 0 % de commission hors Stripe, Essentiel = sous-domaine,
  Premium = domaine propre), et **absence** de promesse inventée (« export 1
  clic », « 48 h »).
- Simon (fondateur) et Sophie Jouan (pilote) ne sont jamais traités comme des
  prospects dans la prose ; Menopulse / Ma Ménopause & Moi ne sont jamais
  fusionnées.
- Le tableau de couverture de cohorte reproduit fidèlement
  `cohort_coverage.json` dans les deux cas.
- Le chiffre « 216 actions » est exact dans les deux rapports.
- La section « Objections non levées » est la partie la plus solide des deux.

## 5. Ce que l'évaluation n'a pas pu trancher

- Une part des 152 / 169 affirmations `UNSUPPORTED` correspond probablement à
  des **reformulations fidèles** de messages observés, sanctionnées par le
  registre pour absence de verbatim, non pour fausseté. Faute de trace
  `event_id ↔ affirmation`, la frontière entre reformulation et invention
  n'est pas mesurable.
- La duplication inter-comptes du corpus (10 textes publiés sous 3 à 10
  comptes) dégrade la fiabilité de toute attribution nominale — y compris
  dans les deux variantes. Sa cause est hors de portée.
- Le contenu réel du graphe Neo4j n'a pas été vérifié : les faits issus des
  outils graphe ne sont pas dans l'empreinte figée.

## 6. Validation de la procédure

- Grille remplie le : **21 octobre 2026** — agent de la session de
  développement (cf. « Qui a jugé » : la correspondance avait déjà été lue,
  la revue n'est donc **pas indépendante**).
- Correspondance ouverte le : **21 octobre 2026**, après remplissage —
  variante A = `flash-medium` (`gemini-3.8-flash`, effort `medium`) ;
  variante B = `flash-high` (`gemini-3.8-flash`, effort `high`).

### Confirmation indépendante

Une **seconde revue, indépendante**, a été conduite le 21 octobre 2026 par
ChatGPT (session neuve, sans accès à la correspondance) : voir
[`revue-aveugle-independante.md`](revue-aveugle-independante.md).

Ses notes : A = 1/2/3/4/1, B = 0/2/2/4/1 — soit **2,2/5** et **1,8/5**.
Les deux revues **convergent** : même note globale (2/5 par variante), mêmes
erreurs matérielles jugées décisives, et `high` **jamais supérieure** à
`medium` (inférieure sur l'exactitude et sur les limites). Le verdict de la
section 7 — *la configuration par défaut reste `medium`* — est donc confirmé
par un évaluateur qui n'avait pas la correspondance.

**Réserve** : les pièces de preuve jointes à cette seconde revue étaient
erronées (elles portaient `simulation_id: sim_ea4f3cfe1028`, l'exécution R6,
au lieu de `sim_80a54d7bbd7b`), ce qui rend **provisoires** ses notes des
critères 1 et 5. Les critères 2, 3 et 4, ainsi que le verdict global et la
comparaison A/B, reposent sur des faits vérifiables dans les textes mêmes des
rapports : ils sont exploitables. La consigne a été durcie en conséquence
(vérification du `simulation_id` des pièces jointes avant l'envoi).


## 7. Lecture après ouverture de la correspondance

La comparaison des deux grilles **ne fait apparaître aucune réduction claire
des erreurs matérielles** en `high` : les deux variantes sont à 2/5, et les
erreurs communes (arc Émilie, citations non verbatim, souscriptions contredites
par le tableau, provenance sur-certifiée, Marie-Claude omise) sont présentes
dans les deux. `high` ajoute des erreurs qui lui sont propres (citations
d'entretiens de rédaction présentées comme des événements observés, question
d'entretien présupposant la conversion, chiffres inventés, incohérence
arithmétique) là où `medium` ajoute les siennes (projection hors horizon,
ancre « 48 h » non attestée).

**Conséquence pour la décision (PRD source §8)** : le critère de décision —
« *choisir `high` si la revue aveugle montre une réduction claire des erreurs
matérielles et des citations non fondées, sans dépassement du budget ni baisse
de couverture* » — **n'est pas rempli**. La bascule de la configuration par
défaut vers `high` **n'est donc pas justifiée** par cette campagne.

**Ce que la campagne démontre en revanche, et qui ne concerne pas le
modèle** : la faiblesse est **systématique et pipeline**, pas liée à l'effort
de raisonnement. Deux défauts reproductibles sont à corriger dans le
`ReportAgent` avant toute conclusion sur la qualité d'un modèle :
(1) les citations issues d'`interview_agents` — qui interroge les agents
**pendant** la rédaction — sont présentées comme des événements observés du
jeu figé ; (2) la section « Sources & Provenance » certifie une traçabilité
que le registre d'affirmations du même rapport contredit. Un troisième point
est propre au `ReportAgent` et à la règle de silence : la fiction de scénario
d'Émilie (non admise dans la simulation) fuit dans les affirmations
« observées ».
