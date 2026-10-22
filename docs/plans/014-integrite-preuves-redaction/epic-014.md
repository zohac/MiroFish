# Epic 014 : Intégrité des preuves de rédaction

> **Statut** : Rédigé le 21 octobre 2026.
> **Dossier de plan** : `docs/plans/014-integrite-preuves-redaction/`
> **PRD** : [`prd.md`](prd.md) · **Architecture** : [`architecture.md`](architecture.md)
> **Épic amont** : 013 (clos) — la campagne A/B a produit l'appareil de mesure ;
> cet epic corrige ce que la mesure a révélé.

---

## 1. Description & Contexte

La campagne de benchmark de l'Epic 013 a comparé deux variantes de rédaction
du `ReportAgent` — effort `medium` et effort `high` — sur le **même** jeu de
preuves figées de la simulation R7 (`sim_80a54d7bbd7b`). Verdict de la
campagne : **comparaison contrôlée**. Verdict de la revue aveugle, versée puis
confirmée par un évaluateur externe indépendant : **2/5 pour chaque variante**,
avec des erreurs matérielles **communes aux deux**.

La conclusion de l'Epic 013 est donc double : l'effort de raisonnement ne
change rien de mesurable dans la qualité du rapport (pour ~13 % de tokens de
plus), et le rapport se contredit lui-même. Le second point n'est pas un
problème de modèle : c'est un **problème de régime de preuve**.

Quatre défauts, mesurés dans le code et sur les artefacts :

1. Les citations d'`interview_agents` — des entretiens menés **pendant** la
   rédaction, hors du paquet figé — sont présentées comme des « événements
   simulés réels » (24 sur 31 citations longues en variante B). Rien dans le
   code ne les distingue d'un fait du graphe.
2. La section « Sources & Provenance » certifie une traçabilité que son propre
   registre d'affirmations nie : elle est construite **avant** le registre, et
   ses deux affirmations clés sont des **littéraux non calculés**.
3. La règle de silence (un persona sans action ne peut se voir attribuer
   d'action) n'agit que sur le registre, jamais sur la prose, et sa
   contradiction n'est **pas** critique pour la barrière de publication.
4. Le brief confond deux biographies de départ, et les fiches des personas non
   admis arrivent dans le contexte de rédaction sans filtrage.

S'y ajoute un cinquième défaut, trouvé en relevant le code : **un seul
`project.json` corrompu** dans le répertoire des projets suffit à priver
*tous* les rapports de la pile de leur section de sources.

## 2. Exigences Fonctionnelles (FR)

| ID | Exigence |
|---|---|
| FR-01 | Un entretien de rédaction est un **régime de preuve distinct**, typé, étiqueté dans le rapport et **exclu** du paquet de preuves figé |
| FR-02 | Le rapport **ne peut pas** présenter comme « événement simulé réel » un passage sans identifiant d'événement vérifiable |
| FR-03 | La section « Sources & Provenance » **lit** le registre d'affirmations, ou **s'abstient** explicitement de certifier la traçabilité |
| FR-04 | Les deux populations d'événements (actions du run / `EvidencePack`) sont **confrontées** et le rapport énonce laquelle il utilise |
| FR-05 | La règle de silence **interdit** à un persona silencieux ou non admis de se voir attribuer une parole, une décision ou une section, dans la prose comme dans le registre |
| FR-06 | La contradiction « persona silence ↔ action affirmée » est **critique** pour la barrière de publication |
| FR-07 | Le brief et les fiches persona ne peuvent pas faire diverger deux biographies de départ ; les fiches des personas non admis ne sont pas dans le contexte de rédaction |
| FR-08 | Un `project.json` corrompu **n'affecte que** le projet concerné |
| FR-09 | L'archive d'audit exportable permet à un tiers d'**établir** d'où vient chaque passage cité |

## 3. Exigences Non Fonctionnelles (NFR)

| ID | Exigence |
|---|---|
| NFR-1 | **Zéro régression** : le filet de tests ne rétrécit pas, et le Fail-Closed reste Fail-Closed |
| NFR-2 | **Généricité** : aucun nom de simulation, de persona ou de projet en dur dans le code |
| NFR-3 | **Déterminisme** : à jeu de preuves identique, le régime de preuve d'un passage est le même d'une génération à l'autre |
| NFR-4 | **Zéro fuite de secret** : les régimes de preuve ne transportent ni clé, ni URL de passerelle, ni prompt |
| NFR-5 | **Honnêteté** : une donnée absente s'affiche « indisponible » ou « non établi », jamais `0` ni une certification |
| NFR-6 | **Traçabilité** : toute correction de ce récit est versionnée, mesurée et rejouable |

## 4. Découpage en Stories

Les quatre stories sont listées ici avec leurs critères résumés. **Le fichier
de story n'est créé qu'au démarrage de la story** (AGENTS.md §2.8 : un fichier
par story réellement démarrée, pas imaginée). La 014-1 est démarrée : son
fichier est [`story-014-1.md`](story-014-1.md), avec 11 critères d'acceptation
falsifiables.

| Story | Titre | Statut | Contenu |
|---|---|---|---|
| 014-1 | [Régime de preuve des entretiens de rédaction](story-014-1.md) | `done` | Un entretien de rédaction devient un régime typé et distinct ; son contenu sort du paquet de preuves figé ; le rapport l'étiquette ; l'étiquette `[Événements simulés réels]` cesse d'être une invention du LLM. **Critère central** : 100 % des passages issus d'un entretien portent leur régime, et aucun ne peut être compté comme un événement observé. |
| 014-2 | La section « Sources & Provenance » ne certifie que ce qu'elle prouve | `done` | La section est produite après le registre, ou par un second passage ; les deux littéraux litigieux deviennent calculés ; les deux populations d'événements sont confrontées et nommées ; un `project.json` corrompu n'affecte que son projet ; l'archive d'audit porte l'index d'attribution. **Critère central** : la section ne contient plus d'affirmation de traçabilité non calculée, et un test le prouve sur un registre réel. |
| 014-3 | La règle de silence monte jusqu'à la prose et jusqu'à la barrière | `review` | Un persona silencieux ou non admis ne peut se voir attribuer ni parole, ni décision, ni section ; ses fiches sont hors du contexte de rédaction ; la contradiction « silence ↔ action affirmée » devient un **échec** de la barrière, et non un avertissement. **Critère central** : une campagne sur R7 ne produit plus de contradiction `CONTRADICTED` sur un persona silencieux qui n'ait pas d'action. |
| 014-4 | Le brief et les fiches persona ne font plus diverger deux biographies | `backlog` | La construction du brief **échoue** quand deux fiches se contredisent au lieu de propager la contradiction ; l'épisode « 1 500 € / WordPress » n'est plus attribué à deux personas ; les fiches des personas non admis sont retirées du contexte et des artefacts. **Critère central** : la contradiction du brief est détectée à la construction, et aucun persona non admis n'apparaît dans le contexte de rédaction. |

### 4.1 Dépendances

```
014-1 ──┐
        ├──▶ 014-2 (la section doit lire un registre dont l'origine est fiable)
014-3 ──┘
014-4 (indépendant : il agit sur la construction des briefs et des fiches)
```

## 5. Critères de Sortie de l'Epic (C1 à C8)

1. **C1** : **Aucun** passage d'entretien de rédaction n'est étiqueté comme un
   événement du jeu figé ; 100 % des passages d'entretien portent leur régime.
2. **C2** : La section « Sources & Provenance » ne contient plus d'affirmation
   de traçabilité non calculée, et un test le prouve sur un registre réel.
3. **C3** : Un persona silencieux ou non admis ne peut recevoir ni parole, ni
   décision, ni section — en prose comme au registre.
4. **C4** : La contradiction « persona silence ↔ action affirmée » déclenche un
   **échec** de la barrière de publication.
5. **C5** : Le brief et les fiches persona ne font plus diverger deux
   biographies de départ, et les fiches non admises sont hors du contexte de
   rédaction.
6. **C6** : Un `project.json` corrompu n'affecte que son propre projet.
7. **C7** : Un tiers recevant l'archive d'audit peut établir l'origine de
   chaque passage cité.
8. **C8** : Filet de tests non régressé, et une campagne de re-qualification
   sur R7 produisant un rapport **sans** certification mensongère.

## 6. Preuve de l'état de départ

Tous les constats de ce dossier sont **rejouables** sur la simulation R7 :

| Constat | Comment le reproduire |
|---|---|
| 24 citations d'entretien sur 31 en variante B, 16 sur 17 en variante A | `backend/uploads/reports/report_ccf28321dcb8/full_report.md` et `report_108186c7524b/full_report.md`, comparer aux entrées `tool_result` de `agent_log.jsonl` |
| 0 `evidence_refs` sur 159 affirmations (A) et 1 sur 178 (B) | `backend/uploads/reports/report_108186c7524b/report_claims.json`, `…/report_ccf28321dcb8/report_claims.json` |
| 7 `CONTRADICTED` (A) et 8 (B), toutes sur le même persona silencieux, avec `failed_checks: 0` | idem + `quality_checks.json` |
| La section certifie une traçabilité non calculée | `report_agent.py:2987` et `:2998` |
| Le label `[Événements simulés réels]` avalé comme un nom d'agent | `backend/tests/fixtures/qualification_epic_012/r6_bundle/report_claims.json:1046` |
| Un `project.json` corrompu casse la résolution | `backend/uploads/projects/proj_d850cdad31ee/project.json` (tronqué) |
| 216 actions contre 737 événements | `actions.jsonl` contre `EvidencePack` |

## 7. Documents à consulter

| Document | Rôle |
|---|---|
| [`prd.md`](prd.md) | le problème, les faits mesurés, les FR/NFR, les critères de sortie |
| [`architecture.md`](architecture.md) | le modèle de preuve, la chronologie de production, les choix de conception |
| `docs/plans/013-benchmark-llm-report-replay/rapport-qualification-epic-013.md` | la campagne de référence |
| `docs/plans/013-benchmark-llm-report-replay/benchmark-013-20261020-203040/grille-aveugle.md` | les erreurs matérielles chiffrées |
| `docs/plans/013-benchmark-llm-report-replay/benchmark-013-20261020-203040/revue-aveugle-independante.md` | la confirmation indépendante |
| `backend/app/services/report_agent.py` | le producteur du rapport |
| `backend/app/services/zep_tools.py` | les outils du rapport |
| `backend/app/services/simulation_action_verifier.py` | le vérificateur et la règle de silence |
| `backend/app/models/source_document.py` | `InformationOrigin` et les origines |
| `backend/app/models/cohort_coverage.py` | l'invariant de silence |
| `backend/app/models/project.py` | la persistance des projets |
| `backend/app/services/simulation_audit_service.py` | l'archive d'audit |
| `AGENTS.md` | la constitution du dépôt |
