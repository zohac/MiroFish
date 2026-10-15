# PRD — Epic 011 : Preuve par les faits simulés, traçabilité épistémique et intégrité des rapports

> **Statut :** Planifié (Backlog)  
> **Date de rédaction :** 15 octobre 2026  
> **Auteur :** Antigravity & Équipe MiroFish  
> **Référence amont :** Proposition PRD issue du retour d'expérience des 5 runs Keova ([`rapport-chatgpt.md`](rapport-chatgpt.md)).  
> **Périmètre :** Backend (`simulation_runner.py`, `report_agent.py`, `zep_tools.py`, `oasis_log_reader.py`, `simulation_config_generator.py`, `simulation_action_verifier.py`, `locale.py`), Modèles (`report_claim.py`, `evidence_pack.py`, `source_document.py`, `simulation_brief.py`), Frontend (`ReportView.vue`).

---

## 1. Contexte & Synthèse du Problème

L'expérimentation empirique menée à travers 5 simulations successives d'une offre commerciale complexe (cas réel Keova Essentiel : 16 agents, 72 heures simulées, 40 rounds, 6 profils cibles aux postures antagonistes) a mis en évidence des avancées notables (diversité des personas, prise en compte des objections, respect des 72h) mais aussi des faiblesses bloquantes pour une utilisation décisionnelle.

L'analyse conjointe du cinquième rapport et des journaux console révèle deux catégories de défaillances :

### A. Défaillances techniques d'exécution (Runtime & Outillage)
1. **Régression d'arrêt prématuré (Epic 010) : Destruction d'`interview_agents`** :
   - Pour débloquer l'IHM en fin de simulation, l'Epic 010 a injecté `--no-wait` et une terminaison forcée du sous-processus OASIS dès le 40ᵉ round.
   - **Conséquence** : Le mode interactif `wait_for_commands` a été détruit. Lorsque `ReportAgent` tourne et invoque `interview_agents`, l'appel IPC échoue systématiquement dans chaque section :  
     `WARNING: Interview API call failed (env not running?): 模拟环境未运行或已关闭`. Résultat : 0/16 agents interviewés, l'outil natif est paralysé.
2. **Burn d'itérations ReACT par exception `quick_search` vide** :
   - Le LLM appelle parfois `quick_search: {}`. Le store Graphiti lève `GraphValidationError("Le texte de recherche query est requis")`.
   - Cet échec répété suivi de l'échec d'interview consomme le plafond de 5 itérations ReACT, forçant une génération précipitée (`reached max iterations, forcing generation`).
3. **Inversion des identités de personas au Round 0** :
   - `SimulationConfigGenerator` assigne les posts initiaux par type générique plutôt que par nom exact : Émilie, Christine et Sylvie se sont vu attribuer des déclarations initiales inversées.
4. **Troncature silencieuse de sections du rapport** :
   - En atteignant `max_tokens=4096`, le LLM s'interrompt en pleine phrase (`[Simulated 72-Hour Events] The`). `ReportAgent` persiste le texte tronqué sans demander de continuation.

### B. Défaillances méthodologiques & épistémiques (Fiabilité analytique)
1. **Événements simulés non prouvés** : Le rapport affirme des causalités et des faits (« raréfaction des créneaux de Simon à 48h ») qui n'existent dans aucune trace du run.
2. **Confusion des statuts de sources** : Des fiches de personas fictifs (`personas-et-cibles-keova.md`, ex. perte de 1 500 € d'Émilie) sont étiquetées comme `[Contexte documentaire historique]`.
3. **Hypothèses fabriquées a posteriori** : Le rapport invente une attente initiale de paiement sous 6 heures non formulée dans le brief, puis prétend la réfuter.
4. **Extrapolations temporelles et métriques non étayées** : Affirmations de « churn à 90 jours » sur un run de 72h, ou qualification d'un coût comme « mathématiquement insoutenable » sans formule ni chiffres réels.
5. **Absence d'étanchéité entre intention et action** : Une déclaration d'un persona disant « Je vais m'abonner » est comptabilisée comme une souscription acquise sans transaction réelle tracée par OASIS.
6. **Biais de confirmation et absence de tableau de couverture** : La synthèse exécutive gomme les refus constatés dans le corps du texte et omet les agents silencieux.

---

## 2. Objectifs Produit

1. **Cycle de vie interactif complet** : Maintenir OASIS vivant en mode `wait_for_commands` après la fin des rounds pour permettre 100 % des interviews en direct, puis clôturer proprement le processus à la fin du rapport.
2. **Preuve par les faits et contrat `ReportClaim`** : Chaque assertion événementielle doit être reliée à un `event_id` authentifié dans les traces du run. Distinguer strictement action réelle, intention verbale et inférence.
3. **Étanchéité épistémique des sources** : Distinguer le fait canonique (`canonical_fact`), le persona fictif (`fictional_persona`), la prémisse de scénario (`scenario_premise`) et l'événement simulé (`simulation_event`).
4. **Tableau de couverture systématique de cohorte** : Récapituler l'état de chaque persona (rôle, actions, objections, statut de décision, silence éventuel sans fabrication de faux faits).
5. **Respect strict du temps simulé et bannissement des métriques fantômes** : Aucune projection présentée comme observation hors de l'horizon ; aucun chiffre sans base calculable.
6. **Barrière de publication `ReportQualityGate`** : Vérifier intégrité, langue, couverture et preuves avant statut `COMPLETED`. Basculer en `FAILED_VALIDATION` avec diagnostic transparent en cas de défaut non résolu.
7. **Dossier d'audit exportable (`simulation_audit/`)** : Paquet téléchargeable documentant l'ensemble de la chaîne de preuve.

---

## 3. Exigences Fonctionnelles (FR)

| Réf. | Intitulé | Description détaillée |
|---|---|---|
| **FR-01** | **Maintien d'OASIS vivant & interviews directes** | La simulation passe à l'état `COMPLETED` pour l'IHM dès la fin des rounds (100 %) sans `--no-wait`. Le sous-processus OASIS reste vivant en écoute IPC (`wait_for_commands`). `interview_agents` réussit à 100 %. La fermeture propre (`send_close_env`) intervient dès la sauvegarde du rapport. En mode rejeu sur simulation close, bascule transparente sur repli hors-ligne sans crash. |
| **FR-02** | **Registre des événements observés (`EvidencePack`)** | `OasisLogReaderService` normalise et indexe les actions réelles issues de `twitter/actions.jsonl`, `reddit/actions.jsonl` et SQLite avec `event_id`. Exposition de l'outil `query_simulation_events` au `ReportAgent`. Distinction stricte entre action réelle et intention textuelle. |
| **FR-03** | **Contrat structuré `ReportClaim`** | Modèle intermédiaire `ReportClaim` : `claim_id`, `text`, `claim_kind` (`source_fact`, `scenario_hypothesis`, `observed_social_action`, `reported_intention`, `analyst_inference`, `speculative_projection`), `evidence`, `verification_status` (`verified`, `unsupported`, `contradicted`). Validateur déterministe côté serveur. |
| **FR-04** | **Typage épistémique et étanchéité des sources** | Qualification au niveau document et fragment : `canonical_fact`, `historical_case`, `fictional_persona`, `scenario_premise`. 0 persona fictif promu en fait historique documentaire. |
| **FR-05** | **Bouclier de validation d'outils (`ToolShield`)** | Gestion défensive des paramètres vides dans `_execute_tool` : si `quick_search` ou `panorama_search` reçoit `params: {}` ou `query=""`, injection automatique du titre de section en cours. 0 exception non gérée, 0 burn d'itérations ReACT. |
| **FR-06** | **Déterminisme d'assignation des personas (Round 0)** | `SimulationConfigGenerator` assigne les posts initiaux par correspondance stricte et insensible à la casse avec le nom du persona (`entity_name` / `name`), interdisant toute permutation d'identités. |
| **FR-07** | **Tableau de couverture de la cohorte & anti-biais** | Génération d'un tableau récapitulatif par persona : rôle dans le scénario, actions observées, objections exprimées, statut de décision. Signalement honnête des agents silencieux (`present_no_action`). Rubrique obligatoire « Objections non levées, contradictions et limites ». |
| **FR-08** | **Respect du temps simulé & anti-métriques inventées** | Interdiction des extrapolations hors horizon (`SimulationBrief.time_horizon`) présentées comme des observations. Interdiction des formulations quantitatives (« taux de 83 % », « coût insoutenable ») sans dénominateur ni formule explicite. |
| **FR-09** | **Barrière de publication `ReportQualityGate`** | Contrôle serveur avant `ReportStatus.COMPLETED` : complétude des sections, absence de phrases coupées, 0 affirmation critique `unsupported`, conformité linguistique. Si défaut corrigible : jusqu'à 2 cycles de continuation/réparation ciblée (`SectionCompletionGuard`). Si échec persistant : statut `FAILED_VALIDATION` avec motif explicite. |
| **FR-10** | **Dossier d'audit exportable (`simulation_audit/`)** | Endpoint API et bouton IHM pour télécharger le paquet d'audit : `run_manifest.json`, `simulation_brief.json`, `actors.json`, `source_manifest.json`, `observed_events.jsonl`, `report_claims.json`, `quality_checks.json`, `report.md`. |
| **FR-11** | **Conformité linguistique native** | Respect de la locale demandée (`fr`) sur les titres, résumés, corps et sous-sections. Préservation des citations originales en preuve avec traduction signalée. |

---

## 4. Exigences Non Fonctionnelles (NFR)

| Réf. | Intitulé | Exigence |
|---|---|---|
| **NFR-01** | **Local-First & Neutralité** | Zéro dépendance vers des services cloud propriétaires. Fonctionne entièrement avec le LLM configuré (OpenCode Go space-bunny) et les traces locales. |
| **NFR-02** | **Zéro régression** | Le filet complet existant (1 589 tests sur l'hôte) reste 100 % vert. |
| **NFR-03** | **Propreté des processus** | Aucun processus zombie ou orphelin OASIS après la fin du cycle ou l'arrêt forcé. |
| **NFR-04** | **Résilience ReACT** | 100 % des appels d'outils renvoient un texte exploitable sans bloquer le moteur. |
| **NFR-05** | **Étanchéité des prompts (Anti-injection)** | Les données d'événements et citations sont encapsulées comme données passives étanches, jamais comme instructions exécutables. |

---

## 5. Critères de Sortie Chiffrés (C1 à C11)

| Réf. | Critère mesurable | Seuil de succès |
|---|---|---|
| **C1** | **Persistance interactive d'OASIS et réussite d'`interview_agents`** | À l'issue des rounds (100%), OASIS reste en écoute IPC. `interview_agents` réussit à 100 % pendant la génération du rapport sans avertissement `env not running`. Arrêt propre par `send_close_env()` dès la fin du rapport. |
| **C2** | **Accès direct aux traces réelles (`query_simulation_events`)** | `ReportAgent` interroge les actions réelles via `OasisLogReaderService`. En mode rejeu, repli transparent sur les traces disques (0 crash). |
| **C3** | **Bouclier `ToolShield` & zéro burn d'itérations** | 0 exception levée lors d'appels `quick_search: {}`. 0 section ne bascule en génération forcée prématurée par épuisement d'itérations dû à un crash d'outil. |
| **C4** | **Anti-affabulation et contrat `ReportClaim`** | 100 % des affirmations sous `[Événements simulés]` sont reliées à un `event_id` valide du run. 0 citation verbatim non retrouvée dans les traces. 0 intention qualifiée d'achat réel. |
| **C5** | **Étanchéité épistémique des sources** | 0 fait issu d'un document typé `PERSONA_SPECIFICATION` classé sous `[Contexte documentaire historique]`. |
| **C6** | **Déterminisme d'assignation Round 0** | 100 % des `initial_posts` dans `SimulationConfigGenerator` sont assignés à l'agent dont le nom correspond exactement au persona (0 permutation sur banc de 10 runs). |
| **C7** | **Tableau de couverture et anti-biais** | 100 % des personas demandés figurent au tableau de couverture. Les personas silencieux sont notés `present_no_action` (0 faux événement inventé). Section d'objections non levées présente. |
| **C8** | **Respect de l'horizon temporel et anti-métriques fantômes** | 0 événement situé au-delà de l'horizon du run. 0 métrique quantitative non calculable. |
| **C9** | **Barrière `ReportQualityGate` et anti-troncature** | 0 section publiée tronquée ou sans ponctuation terminale. Si non résolu, bascule en `FAILED_VALIDATION` (aucun faux `COMPLETED`). |
| **C10** | **Export du dossier d'audit complet** | Paquet `simulation_audit/` exportable avec les 8 artefacts requis, vérifiable hors-ligne. |
| **C11** | **Validation multi-domaines et non-régression** | Validation du harnais sur 3 domaines distincts (SaaS Keova, politique publique, télécom). Filet global porté à $\ge 1615$ tests verts sur l'hôte. |
