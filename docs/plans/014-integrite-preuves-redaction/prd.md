# PRD — Epic 014 : Intégrité des preuves de rédaction

> **Statut** : Rédigé le 21 octobre 2026, à partir des constats de la revue
> aveugle de la campagne de benchmark `benchmark-013-20261020-203040`.
> **Dossier de plan** : `docs/plans/014-integrite-preuves-redaction/`
> **Épic amont** : 013 (clos le 21 octobre 2026) — la campagne A/B a produit
> l'appareil de mesure ; cet epic corrige ce que la mesure a révélé.

---

## 1. Résumé de décision

La campagne de benchmark de l'Epic 013 a établi deux choses, et une seule
importe pour la suite.

**Ce qui est établi.** Les deux variantes du `ReportAgent` (`flash-medium` et
`flash-high`) ont été générées sur le même jeu de preuves figées, avec un
verdict de **comparaison contrôlée**. La revue aveugle — versée puis confirmée
par un évaluateur externe indépendant — les note **2/5 chacune**, avec des
erreurs matérielles **communes aux deux** : un persona non admis reçoit un
refus, des citations et une section ; les citations présentées comme verbatim
ne le sont pas ; des souscriptions affirmées sont contredites par le tableau de
cohorte du rapport lui-même ; la section « Sources & Provenance » certifie une
traçabilité que le registre d'affirmations nie.

**Ce qui en découle.** Le banc a fait son travail : il a montré que l'écart
entre `medium` et `high` ne porte pas sur la qualité de rédaction, et que le
vrai sujet est ailleurs. Ce sujet est **le régime de preuve du rapport** :
aujourd'hui, un rapport peut affirmer comme « événement simulé réel » une
parole fabriquée par le LLM pendant la rédaction, ou certifier une traçabilité
qu'il n'a pas vérifiée. Ces défauts sont **communs aux deux efforts de
raisonnement**, donc indépendants du modèle : les corriger change la nature
de l'artefact produit, pas sa qualité rédactionnelle.

**Décision.** Ouvrir un epic dédié à l'**intégrité des preuves de rédaction**,
avec quatre chantiers : le régime de preuve des entretiens de rédaction, la
vérité de la section « Sources & Provenance », la remontée de la règle de
silence jusqu'à la prose, et l'hygiène du brief et des fiches persona.

## 2. Contexte vérifié

Tous les faits ci-dessous sont **mesurés dans le code et sur les artefacts de
la campagne** ; les emplacements sont vérifiés, pas supposés.

### 2.1 Les entretiens de rédaction n'ont aucun régime de preuve

| Fait | Emplacement |
|---|---|
| `interview_agents` renvoie un **texte libre** : aucun `event_id`, aucune provenance, aucun typage d'origine | `report_agent.py:1577` → `zep_tools.py:437-460` (`InterviewResult.to_text()`) |
| En `replay_frozen`, les réponses sont **fabriquées par le LLM du rapport pendant la rédaction**, à partir de `actions.jsonl` et des fiches persona | `zep_tools.py:1736-1835` (`_synthesize_offline_interviews`), appel LLM à `:1779-1798` |
| Ces réponses viennent de matériaux **hors du paquet scellé** : `actions.jsonl` et les fiches persona ne figurent pas dans `CANONICAL_AUDIT_FILES` | `evidence_snapshot_service.py:49-56` |
| `InformationOrigin` n'a que 5 valeurs, **aucune ne qualifie un entretien de rédaction** ; l'extracteur n'en produit que 4 | `source_document.py:101-116` ; `report_agent.py:3271-3297` |
| Le label `[Événements simulés réels]` **n'est produit par aucun code** : c'est une invention du LLM, et l'extracteur l'avale comme un nom d'agent | `backend/tests/fixtures/qualification_epic_012/r6_bundle/report_claims.json:1046` → `agent_name: "Événements"` |
| La seule trace d'attribution est `agent_log.jsonl` (`details.tool_name` + `details.result`) — et **elle n'est pas dans l'archive d'audit** | `report_agent.py:213-234` ; `simulation_audit_service.py:228-378` |
| `interviews_archive.json` est prévu dans le paquet scellé, mais **aucun code ne l'écrit** | `evidence_snapshot_service.py:51`, `:181-188` (lecture seule) |

**Mesuré sur la campagne** (21 octobre 2026, rattachement par 8-grammes
normalisés entre les citations longues du rapport et les `tool_result` de
`agent_log.jsonl`) :

| Variante | citations longues | depuis `interview_agents` | depuis `insight_forge` | d'aucun outil |
|---|---|---|---|---|
| A (`flash-medium`, `report_108186c7524b`) | 17 | **16** | 0 | 1 |
| B (`flash-high`, `report_ccf28321dcb8`) | 31 | **24** | 4 | 3 |

**40 des 48 citations longues du corpus** — donc **83 %** — viennent d'un
entretien tenu pendant la rédaction, et **4 seulement** d'un outil graphe. Ce
sont ces 40 passages que le rapport présente comme des « événements simulés
réels ».

### 2.2 « Sources & Provenance » certifie ce qu'elle ne peut pas prouver

| Fait | Emplacement |
|---|---|
| La section est construite et concaténée **avant** l'écriture du registre d'affirmations : elle ne peut donc pas le lire | section `report_agent.py:2910-3064`, insertion `:2591-2597`, registre `:2618-2625` |
| « Toute affirmation qualifiée d'action observée est reliée à un événement horodaté du run » est un **littéral non calculé** | `report_agent.py:2987` |
| « Aucune divergence intention vs action non résolue détectée » est un littéral conditionné à `intentions == []` : il signifie « aucun post n'a matché les motifs d'intention », pas « aucune divergence » — **confusion de dénominateurs** | `report_agent.py:2998` ; `simulation_action_verifier.py:452-518` |
| Deux populations coexistent sans être confrontées : **216** actions (`actions.jsonl`) et **737** événements (`EvidencePack`) | `simulation_action_verifier.py:291-398` ; `oasis_log_reader.py` |
| La contradiction du registre n'est **pas** critique pour la barrière : le Fail-Closed ne compte que les `CONTRADICTED` de kind `OBSERVED_SOCIAL_ACTION`, or la règle de silence reclasse en `SPECULATIVE_PROJECTION` | `report_quality_gate.py:464-493` ; `simulation_action_verifier.py:953` |

**Mesuré sur la campagne** (21 octobre 2026, `report_claims.json` des deux
rapports) :

| Variante | affirmations | avec `evidence_refs` | `CONTRADICTED` | `failed_checks` |
|---|---|---|---|---|
| A (`flash-medium`) | **159** | **0** | **7** | **0** |
| B (`flash-high`) | **178** | **1** | **8** | **0** |

Les 15 `CONTRADICTED` portent **toutes** sur le même persona silencieux
(« Émilie »). La barrière de publication ne relève donc **aucun** échec : ces
contradictions sont émises comme avertissements. La section « Sources &
Provenance » affirme pourtant que toute action observée affirmée est reliée à
un événement horodaté — alors qu'**aucune** affirmation de la variante A n'en
porte la référence.

### 2.3 La règle de silence n'agit que sur le registre

| Fait | Emplacement |
|---|---|
| **Une seule** implémentation de la règle, dans `verify_report_claim` | `simulation_action_verifier.py:939-961` |
| Elle est conditionnée à `cohort_table is not None` **et** `claim.agent_name is not None` | `simulation_action_verifier.py:942` |
| Elle ne réécrit que le `ReportClaim` : **le markdown reste inchangé** | `simulation_action_verifier.py:953` (reclassement) |
| Les fiches persona entrent dans le contexte de rédaction par **quatre chemins non filtrés** | brief `report_agent.py:688` et `:1886` ; outils graphe `:1516-1552` ; `interview_agents` `zep_tools.py:1483` ; `query_simulation_events` `zep_tools.py:2071` |
| Un acteur `review` n'est **jamais filtré** : seuls les `ineligible` le sont | `cohort_coverage.py:83-86` et `:622-625` |
| `check_executive_summary_bias` est du **code mort** : appelé par les tests seulement | `simulation_action_verifier.py:1343-1398` |

**Mesuré sur R7.** `actors.json` : 41 entités, dont 17 `eligible`, **1 `review`**
(le persona « Émilie », `confidence: 0.0`, « Qualification sûre en review faute
de décision fiable »), 23 `ineligible`. Le persona n'existe ni dans
`simulation_config.json` (17 agents), ni dans `reddit_profiles.json` (17
profils), ni dans les 737 événements. Il est pourtant membre de la cohorte
(`is_silent: true`, `action_count: 0`) **et nommé dans le brief** — donc présent
dans le contexte du LLM avant tout outil.

### 2.4 Le brief confond les biographies de départ

**Mesuré.** L'épisode « 1 500 € / WordPress » appartient à la fiche du persona
« Émilie » ; il est repris par « Nathalie » dans les traces de R7, et les deux
rapports l'attribuent à Nathalie. La confusion précède donc le rapport : elle
est dans le brief (`simulation_requirement`, 6 384 caractères, projet
`proj_cc8bc57b87fe`).

### 2.5 Un projet voisin corrompu fait mentir toutes les provenances

| Fait | Emplacement |
|---|---|
| `ProjectManager.get_project` fait `json.load` **sans garde** | `project.py:307-325` |
| `list_projects` parcourt tout le répertoire des projets | `project.py:337-348` |
| Un `project.json` corrompu fait donc lever `find_projects_by_graph_id` | `project.py:352-359` |
| L'exception est avalée par `_resolve_project` → le projet résolu est `None` | `report_agent.py:1414-1424` |
| La section affiche alors « Aucun document source structuré rattaché au projet » — **pour R7, qui en a 3** | `report_agent.py:2979` |

**Mesuré.** `backend/uploads/projects/proj_d850cdad31ee/project.json` est
tronqué (619 octets, coupé dans `source_documents`) → `JSONDecodeError`. Un
seul fichier corrompu, dans un répertoire voisin, prive **tous** les rapports de
la pile de leur section de sources.

## 3. Objectifs et non-objectifs

### Objectifs

1. Qu'aucun passage fabriqué **pendant** la rédaction ne puisse être présenté
   comme un événement du jeu de preuves figé.
2. Que la section « Sources & Provenance » ne certifie **que** ce qu'elle peut
   vérifier, et qu'elle s'abstienne explicitement du reste.
3. Que la règle de silence atteigne la **prose** et la **barrière
   Fail-Closed**, pas seulement le registre.
4. Que le brief et les fiches persona ne puissent plus faire diverger deux
   biographies de départ.

### Non-objectifs

- Améliorer la **qualité rédactionnelle** du rapport : c'est l'affaire du
  modèle, et la campagne a montré que l'effort de raisonnement n'y change
  rien de mesurable.
- Réécrire le `ReportAgent` : l'epic corrige des **régimes de preuve**, pas
  la rédaction.
- Toucher à l'interface : aucun écran n'est en cause.
- Rouvrir les Epics 011 et 012 : leurs barrières sont le **vérificateur** de
  cet epic, pas sa cible.

## 4. Exigences Fonctionnelles (FR)

| ID | Exigence | Priorité |
|---|---|---|
| FR-01 | Un entretien de rédaction est un **régime de preuve distinct**, typé, étiqueté dans le rapport et **exclu** du paquet de preuves figé | P0 |
| FR-02 | Le rapport **ne peut pas** présenter comme « événement simulé réel » un passage sans identifiant d'événement vérifiable | P0 |
| FR-03 | La section « Sources & Provenance » **lit** le registre d'affirmations, ou **s'abstient** explicitement de certifier la traçabilité | P0 |
| FR-04 | Les deux populations d'événements (actions du run / `EvidencePack`) sont **confrontées** et le rapport énonce laquelle il utilise | P0 |
| FR-05 | La règle de silence **interdit** à un persona silencieux ou non admis de se voir attribuer une parole, une décision ou une section, dans la prose comme dans le registre | P0 |
| FR-06 | La contradiction « persona silence ↔ action affirmée » est **critique** pour la barrière de publication | P0 |
| FR-07 | Le brief et les fiches persona ne peuvent pas faire diverger deux biographies de départ ; les fiches des personas non admis ne sont pas dans le contexte de rédaction | P0 |
| FR-08 | Un `project.json` corrompu **n'affecte que** le projet concerné | P1 |
| FR-09 | L'archive d'audit exportable permet à un tiers d'**établir** d'où vient chaque passage cité | P1 |

## 5. Exigences Non Fonctionnelles (NFR)

| ID | Exigence |
|---|---|
| NFR-1 | **Zéro régression** : le filet de tests ne rétrécit pas, et le Fail-Closed reste Fail-Closed |
| NFR-2 | **Généricité** : aucun nom de simulation, de persona ou de projet en dur dans le code |
| NFR-3 | **Déterminisme** : à jeu de preuves identique, le régime de preuve d'un passage est le même d'une génération à l'autre |
| NFR-4 | **Zéro fuite de secret** : les régimes de preuve ne transportent ni clé, ni URL de passerelle, ni prompt |
| NFR-5 | **Honnêteté** : une donnée absente s'affiche « indisponible » ou « non établi », jamais `0` ni une certification |
| NFR-6 | **Traçabilité** : toute correction de ce récit est versionnée, mesurée et rejouable |

## 6. Critères de sortie de l'epic

| C | Critère |
|---|---|
| C1 | **Aucun** passage d'entretien de rédaction n'est étiqueté comme un événement du jeu figé ; 100 % des passages d'entretien portent leur régime |
| C2 | La section « Sources & Provenance » ne contient plus d'affirmation de traçabilité non calculée, et elle est vérifiée par un test sur le registre |
| C3 | Un persona silencieux ou non admis ne peut recevoir ni parole, ni décision, ni section — en prose comme au registre |
| C4 | La contradiction « persona silence ↔ action affirmée » déclenche un **échec** de la barrière de publication |
| C5 | Le brief et les fiches persona ne font plus diverger deux biographies de départ, et les fiches non admises sont hors du contexte de rédaction |
| C6 | Un `project.json` corrompu n'affecte que son propre projet |
| C7 | Un tiers recevant l'archive d'audit peut établir l'origine de chaque passage cité |
| C8 | Filet de tests non régressé, et une campagne de re-qualification sur R7 produisant un rapport **sans** certification mensongère |

## 7. Documents à consulter

| Document | Rôle |
|---|---|
| `docs/plans/013-benchmark-llm-report-replay/rapport-qualification-epic-013.md` | la campagne et ses mesures |
| `docs/plans/013-benchmark-llm-report-replay/benchmark-013-20261020-203040/grille-aveugle.md` | la revue aveugle, erreurs matérielles chiffrées |
| `docs/plans/013-benchmark-llm-report-replay/benchmark-013-20261020-203040/revue-aveugle-independante.md` | la confirmation indépendante |
| `docs/plans/013-benchmark-llm-report-replay/architecture.md` | l'architecture de l'Epic 013, dont hérite celui-ci |
| `backend/app/services/report_agent.py` | le producteur du rapport et de ses sections |
| `backend/app/services/zep_tools.py` | les outils du rapport, dont `interview_agents` |
| `backend/app/services/simulation_action_verifier.py` | le vérificateur d'affirmations et la règle de silence |
| `backend/app/models/source_document.py` | `InformationOrigin`, les cinq origines |
| `backend/app/models/cohort_coverage.py` | l'invariant de silence et la table de cohorte |
| `backend/app/models/project.py` | la persistance des projets |
| `backend/app/services/simulation_audit_service.py` | l'archive d'audit exportable |
| `AGENTS.md` | la constitution du dépôt |
