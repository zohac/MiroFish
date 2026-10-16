# Epic 011 : Preuve par les faits simulés, traçabilité épistémique et intégrité des rapports

> **Statut :** Planifié (Backlog)  
> **Date de formalisation :** 15 octobre 2026  
> **Responsable :** Équipe MiroFish & Antigravity  
> **Dépendances :** Epic 005 (Docker local), Epic 007 (Ontologie dynamique), Epic 008 (Localisation FR), Epic 009 (Éligibilité des acteurs), Epic 010 (Cycle de vie des simulations)  
> **Dossier de plan :** `docs/plans/011-preuve-simulation-et-fiabilite-rapport/`  
> **PRD :** [`prd.md`](prd.md) · **Architecture :** [`architecture.md`](architecture.md) · **Proposition amont :** [`rapport-chatgpt.md`](rapport-chatgpt.md)

---

## 1. Description & Contexte

L'expérimentation empirique menée à travers 5 simulations successives (cas réel Keova Essentiel : 16 agents, 72 heures simulées, 40 rounds, 6 profils cibles aux postures contrastées) a prouvé que MiroFish sait désormais différencier des personas et respecter des règles métier complexes. 

Cependant, l'analyse conjointe du 5ᵉ rapport et des logs d'exécution a mis en lumière une série de faiblesses techniques et méthodologiques qui affaiblissent la crédibilité des conclusions produites :
1. **La régression d'arrêt prématuré (Epic 010)** : En éteignant le processus OASIS immédiatement après le 40ᵉ round (`--no-wait`), le mode d'écoute interactif (`wait_for_commands`) a été détruit, causant l'échec systématique de l'outil `interview_agents` (`0/16 agents interviewés`) lors de la génération du rapport.
2. **Le « burn » d'itérations ReACT par crashs d'outils** : Des appels LLM à `quick_search` avec `params: {}` lèvent une exception de validation stricte qui, répétée, épuise le quota de 5 itérations et force une génération de section précipitée sans données utiles.
3. **L'absence d'interrogation directe des traces d'actions OASIS** : Le `ReportAgent` ne dispose d'aucun outil pour requêter les posts et actions réelles consignées sur disque.
4. **La confusion épistémique des sources** : Des fiches de personas fictifs (`personas-et-cibles-keova.md`) sont indûment présentées dans le rapport comme du « Contexte documentaire historique ».
5. **L'inversion des identités de personas au Round 0** : `SimulationConfigGenerator` attribue les posts initiaux selon des types d'entités génériques plutôt que par correspondance exacte des noms, inversant les rôles d'Émilie, Sylvie et Christine.
6. **L'absence de distinction entre intention et action** : Une déclaration verbale d'intention (« Je vais m'abonner ») est traitée comme un achat effectif sans transaction tracée.
7. **La troncature silencieuse par plafond de tokens** : Des sections coupées en plein milieu de phrase (`[Simulated 72-Hour Events] The`) sont enregistrées telles quelles sans reprise.
8. **Biais de confirmation et métriques fantômes** : Conclusions péremptoires extrapolant au-delà des 72h du run (« churn à 90 jours ») et métriques non étayées (« coût mathématiquement insoutenable »).

L'**Epic 011** résout l'ensemble de ces points pour que les rapports analytiques de MiroFish reposent sur des preuves empiriques irréfutables, vérifiées, complètes et rigoureusement étayées.

---

## 2. Exigences Fonctionnelles (FR)

- **FR-01 : Maintien d'OASIS vivant & interviews directes** :  
  La simulation est signalée achevée pour l'IHM dès la fin des rounds (100%), mais le sous-processus OASIS est maintenu en vie dans sa boucle `wait_for_commands` (sans `--no-wait`). L'outil `interview_agents` dialogue en direct avec les agents actifs. Le processus est proprement clôturé par `send_close_env()` dès la complétion du rapport. Repli transparent en mode hors-ligne en cas de rejeu sur simulation éteinte.
- **FR-02 : Registre d'événements observés (`OasisLogReaderService`) & `EvidencePack`** :  
  Indexation et normalisation des actions réelles (`actions.jsonl` et SQLite) avec `event_id`. Outil `query_simulation_events` exposé au `ReportAgent`. Distinction stricte entre action réelle et intention verbale.
- **FR-03 : Contrat structuré d'affirmation `ReportClaim`** :  
  Chaque assertion événementielle est soumise au contrat `ReportClaim` (`claim_kind`, `origin`, `evidence_refs`, `verification_status`). Validation déterministe serveur : toute action « observée » doit être reliée à un `event_id` authentifié du run.
- **FR-04 : Typage épistémique et étanchéité documentaire** :  
  Les sources portent un type explicite (`CANONICAL_DOCUMENT`, `PERSONA_SPECIFICATION`, `SCENARIO_BRIEF`). Aucun fait issu d'un persona fictif n'est classé sous `[Contexte documentaire historique]`.
- **FR-05 : Bouclier de validation des outils ReACT (`ToolShield`)** :  
  Si `quick_search` ou `panorama_search` est invoqué avec une requête vide ou `params: {}`, le système applique automatiquement le titre de la section en cours comme repli. 0 exception levée, 0 itération gaspillée.
- **FR-06 : Déterminisme d'assignation des posts initiaux (Round 0)** :  
  Les `initial_posts` de `SimulationConfigGenerator` sont attribués par correspondance stricte avec le nom du persona cible.
- **FR-07 : Tableau de couverture de cohorte & anti-biais** :  
  Tableau récapitulatif systématique par persona (rôle, actions observées, objections, statut de décision). Mention explicite `present_no_action` pour les agents silencieux (0 fabrication de faux événements). Section obligatoire d'objections non levées et limites.
- **FR-08 : Respect du temps simulé & anti-métriques fantômes** :  
  Interdiction des extrapolations au-delà de l'horizon (`SimulationBrief.time_horizon`). Interdiction des affirmations quantitatives sans base calculable.
- **FR-09 : Barrière de publication `ReportQualityGate` & `SectionCompletionGuard`** :  
  Vérification de l'intégrité, de la complétude (0 phrase coupée), de la langue et des preuves avant publication. Si défaut insoluble, passage au statut `FAILED_VALIDATION` (aucun faux `COMPLETED`).
- **FR-10 : Dossier d'audit exportable (`simulation_audit/`)** :  
  Archive téléchargeable contenant l'ensemble des 8 artefacts de preuve (`manifest`, `brief`, `actors`, `events`, `claims`, `checks`, `report`).
- **FR-11 : Respect strict de la langue active** :  
  Conformité de l'ensemble des titres, synthèses et corps en français (`locales/fr.json`), avec conservation des citations originales en preuve et traductions signalées.

---

## 3. Exigences Non Fonctionnelles (NFR)

- **NFR-1 : Local-First & Neutralité** : Fonctionnement autonome en local sans dépendance externe propriétaire.
- **NFR-2 : Zéro régression** : Les 1 589 tests collectés et réussis sur l'hôte restent intégralement verts.
- **NFR-3 : Propreté des processus** : Aucun sous-processus OASIS ne subsiste après la fin de la génération du rapport ou l'arrêt manuel par l'utilisateur.
- **NFR-4 : Résilience ReACT** : 100 % des appels d'outils renvoient une réponse textuelle exploitable sans lever d'exception non gérée.
- **NFR-5 : Étanchéité des prompts** : Les faits observés et citations sont injectés comme données passives strictement étanches.

---

## 4. Découpage en Stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 011-1 | Maintien en vie interactif d'OASIS post-rounds, rétablissement d'`interview_agents` et clôture différée | `done` | [`story-011-1.md`](story-011-1.md) |
| 011-2 | Registre d'événements observés (`OasisLogReaderService`, `EvidencePack`), bouclier `ToolShield` et déterminisme Round 0 | `done` | [`story-011-2.md`](story-011-2.md) |
| 011-3 | Contrat structuré `ReportClaim`, typage épistémique des sources et contrôle anti-affabulation | `backlog` | [`story-011-3.md`](story-011-3.md) |
| 011-4 | Tableau de couverture de cohorte, anti-biais de confirmation (section limites) et respect du temps simulé | `backlog` | [`story-011-4.md`](story-011-4.md) |
| 011-5 | Barrière de publication `ReportQualityGate`, anti-troncature de section et dossier d'audit exportable (`simulation_audit/`) | `backlog` | [`story-011-5.md`](story-011-5.md) |
| 011-6 | Banc de qualification de bout en bout multi-domaines et rapport de qualification final de l'Epic 011 | `backlog` | [`story-011-6.md`](story-011-6.md) |

---

## 5. Critères de Sortie de l'Epic (C1 à C11)

1. **C1 : Persistance interactive d'OASIS et réussite d'`interview_agents`** : OASIS reste en écoute IPC (`wait_for_commands`) après les rounds. `interview_agents` réussit à 100 % pendant le rapport. Arrêt propre par `send_close_env()` dès la fin du rapport.
2. **C2 : Accès direct aux traces réelles (`query_simulation_events`)** : `ReportAgent` interroge les actions réelles via `OasisLogReaderService`. En mode rejeu, repli transparent sur les traces disques (0 crash).
3. **C3 : Bouclier `ToolShield` & zéro burn d'itérations** : 0 exception levée lors d'appels `quick_search: {}`. 0 section ne bascule en génération forcée prématurée par épuisement d'itérations dû à un crash d'outil.
4. **C4 : Anti-affabulation et contrat `ReportClaim`** : 100 % des affirmations sous `[Événements simulés]` sont reliées à un `event_id` valide du run. 0 citation verbatim non retrouvée dans les traces. 0 intention qualifiée d'achat réel.
5. **C5 : Étanchéité épistémique des sources** : 0 fait issu d'un document typé `PERSONA_SPECIFICATION` classé sous `[Contexte documentaire historique]`.
6. **C6 : Déterminisme d'assignation Round 0** : 100 % des `initial_posts` dans `SimulationConfigGenerator` sont assignés à l'agent dont le nom correspond exactement au persona (0 permutation sur banc de 10 runs).
7. **C7 : Tableau de couverture et anti-biais** : 100 % des personas demandés figurent au tableau de couverture. Les personas silencieux sont notés `present_no_action` (0 faux événement inventé). Section d'objections non levées présente.
8. **C8 : Respect de l'horizon temporel et anti-métriques fantômes** : 0 événement situé au-delà de l'horizon du run. 0 métrique quantitative non calculable.
9. **C9 : Barrière `ReportQualityGate` et anti-troncature** : 0 section publiée tronquée ou sans ponctuation terminale. Si non résolu, bascule en `FAILED_VALIDATION` (aucun faux `COMPLETED`).
10. **C10 : Export du dossier d'audit complet** : Paquet `simulation_audit/` exportable avec les 8 artefacts requis, vérifiable hors-ligne.
11. **C11 : Validation multi-domaines et non-régression** : Validation du harnais sur 3 domaines distincts (SaaS Keova, politique publique, télécom). Filet global porté à $\ge 1615$ tests verts sur l'hôte.

---

## 6. Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`prd.md`](prd.md) | Exigences fonctionnelles et critères d'acceptation chiffrés. |
| [`architecture.md`](architecture.md) | Cycle de vie vivant, architecture de `ToolShield`, `OasisLogReaderService` et `ReportQualityGate`. |
| [`rapport-chatgpt.md`](rapport-chatgpt.md) | Rapport amont d'analyse des 5 simulations Keova et propositions méthodologiques. |
| [`backend/app/services/simulation_runner.py`](../../backend/app/services/simulation_runner.py) | Supervision active, gestion de `--no-wait` et clôture différée. |
| [`backend/app/services/report_agent.py`](../../backend/app/services/report_agent.py) | Boucle ReACT, anti-troncature et barrière de qualité. |
| [`backend/app/services/simulation_action_verifier.py`](../../backend/app/services/simulation_action_verifier.py) | Vérification verbatim et identifiants d'événements. |
| [`AGENTS.md`](../../AGENTS.md) | Constitution du dépôt (§2.1, §2.2, §2.8). |
