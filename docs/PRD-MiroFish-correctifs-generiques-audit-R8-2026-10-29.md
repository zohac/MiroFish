# MiroFish — Rapport d'audit et PRD correctif générique

**Objet :** fiabiliser la chaîne *agents → interactions/entretiens → rapport → preuves → publication*, sans spécialiser le moteur pour une entreprise, un produit, un métier ou un domaine donné.  
**État :** proposition au développeur, **aucune correction applicative réalisée par ce document**.  
**Date de référence :** 29 octobre 2026.  
**Dépôt consulté :** [`zohac/MiroFish`, branche `local-first`](https://github.com/zohac/MiroFish/tree/local-first), **HEAD analysé `e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894`**.  
**Exécution auditée :** simulation `sim_7a1b02b8c092`, rapport `report_934d3254004b`, fichiers d'audit transmis le 29 octobre 2026.

> **Principe non négociable : Keova est une fixture de qualification, pas une dépendance métier.** Aucune règle, constante, chaîne de caractères, tarif, fonctionnalité, persona ou nom d'entreprise provenant de ce cas ne doit être codé dans les services génériques de MiroFish. Les exemples du cas testé sont utilisés **uniquement dans les données de test**. Les mêmes invariants doivent fonctionner pour la simulation d'une crise de transports, d'une innovation industrielle, d'un lancement de jeu ou d'un débat associatif.

## 1. Résumé exécutif et décision recommandée

Le moteur progresse en génération de scénarios plausibles et a acquis des garde-fous réels : `EvidencePack`, vérificateur de claims, registre, cohorte, manifeste, section de provenance, barrière de publication, mode replay, métriques de consommation et audit de cohérence des profils. **Ne pas recommencer les Epics 011–014.** Corriger leurs points d'intégration et introduire des contrats de données explicites.

Le résultat récent est **non publiable** : `quality_checks(3).json` porte `is_publishable=false`, `final_status=failed`. Il détecte notamment l'absence du titre contractuel « Objections non levées, contradictions et limites », mais le contrôle des actions signale « 0 action simulée » alors que le texte en raconte. **La cause immédiate du blocage n'est pas nécessairement celle de la non-fiabilité du fond.**

**Recommandation :** un petit Epic correctif autonome (nom/numéro à déterminer dans le dépôt), découpé en stories P0 sur la traçabilité, la classification des assertions et les rôles, puis P1 sur la cohérence factuelle et l'observabilité. Ne pas changer de LLM à cette étape. **Ce choix ne modifie pas les décisions de Keova.**

### 1.1 Indicateurs du dossier d'audit

| Mesure | Résultat observé | Signification |
|---|---:|---|
| Acteurs qualifiés | 49 entités : 18 éligibles, 31 inéligibles | Éligibilité *ontologique*, pas pertinence dans le scénario |
| Cohorte exportée | 18/18 actifs | Couverture des agents instanciés ; inclut organisations et rôles non commerciaux |
| Événements `observed_events.jsonl` | 953 | Traces consolidées, **pas** 953 décisions indépendantes |
| Actions de référence annoncées par « Sources & Provenance » | 388 | Population différente, à tracer explicitement par origine |
| Affirmations extraites | 165 | 83 `REPORTED_INTENTION`, 74 `ANALYST_INFERENCE`, 7 `SCENARIO_HYPOTHESIS`, 1 `SPECULATIVE_PROJECTION` |
| Claims `OBSERVED_SOCIAL_ACTION` | **0** | Anomalie : le rapport affirme pourtant des publications, réactions et suivis |
| Claims avec `evidence_refs` | **0/165** | Aucune liaison de preuve |
| Claims avec `provenance_regime` non nul | **0/165** | Attribution de régime inopérante pour le dossier |
| Vérifications `VERIFIED` | **0/165** | N'établit **pas** que 165 faits sont faux, mais interdit une certification |
| Qualité | 3 passés, 1 warning, 1 failed | Rapport rejeté ; warning de preuve insuffisant au vu des affirmations d'actions |
| Entretiens enregistrés | 4 séries ; 63 courts fragments de citations | Pas de réponses complètes, ni d'ID stable par tour/persona |
| Modèle déclaré | `deepseek-v4.1-flash`, raisonnement `high` demandé | `reasoning_effort_effective=unknown` ; pas de conclusion possible sur l'effort effectif |
| Usage | 68 appels, 741 059 tokens déclarés ; 916,7 s murales | Coût indisponible ; plafond monétaire à 2 USD non vérifiable |

Sources : `actors(2).json`, `cohort_coverage(3).json`, `observed_events(2).jsonl`, `report_claims(3).json`, `report_interviews.json`, `quality_checks(3).json`, `run_manifest(2).json`, `usage.json` et `report(2).md`.

**Important — frontière temporelle :** le rapport a été produit avant le dernier commit GitHub consulté (`e02c4ac`, committé le 29 octobre à 12:02:37 UTC). Sa fiche d'exécution indique encore `git_commit: unknown-git-commit`. La story 014-4 est `done` au HEAD, mais ses correctifs les plus récents ne peuvent pas être déclarés testés par cette génération. **Requalifier sur le code actuel avant toute nouvelle story qui ferait doublon.** Le `epic-014.md` affiche encore `review` pour 014-4 : synchroniser les documents de statut, sans interpréter ce décalage comme un bug fonctionnel.

## 2. Diagnostic technique : faits, mécanismes probables, limites

### D01 — Extraction de claims inadaptée à la prose naturelle (P0)

**Symptôme confirmé :** le rapport contient des actions au passé (« publiée », « aime », « suit », « répond », « trois personnes m'ont écrit »), mais le registre recense 0 `OBSERVED_SOCIAL_ACTION`.

**Code :** [`backend/app/services/report_agent.py`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/report_agent.py#L3302-L3658), `extract_claims_from_content()`.

- Le code reconstruit des assertions **ligne par ligne** en partant du Markdown final. Une même ligne peut contenir plusieurs assertions, plusieurs origines et des citations imbriquées.
- La détection des intentions par sous-chaînes (`"va"`, `"veut"`, `"compte"`, `"souhaite"`…) **précède** celle des actions observées. Des mots contenant ces fragments, des tournures négatives ou des changements de temps peuvent biaiser le typage.
- La détection des actions utilise une liste de formulations verbales fermée. Les actions décrites au présent, sous forme nominale, ou dans un tableau peuvent lui échapper.
- `evidence_refs` est essentiellement constitué de chaînes `evt_*` **déjà présentes dans la prose** ou de noms de fichiers mentionnés ; un bon résumé qui ne cite pas explicitement l'ID ne devient donc pas vérifiable automatiquement.
- Le régime de provenance est inféré par recouvrement de **8 mots consécutifs** avec des sorties d'outils (`backend/app/models/provenance_regime.py`, `attribute_provenance_regime()`). Ce mécanisme est fragile pour les paraphrases et les citations assemblées ; les 165 régimes `null` montrent son échec sur ce run. Il reste à vérifier si la collection d'observations d'outils a bien été remplie.

**Conclusion :** améliorer le LLM peut améliorer la prose, **pas** garantir la traçabilité lorsque la preuve est perdue avant le parseur.

### D02 — Les entretiens de rédaction ne constituent pas des événements OASIS (P0)

**Code :** `ReportAgent._execute_tool_impl()` dans [`report_agent.py#L1571-L1612`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/report_agent.py#L1571-L1612), et persistance dans `#L2734-L2746`.

Le module conserve `subject`, `agents`, `mode` et une liste aplatie de `key_quotes`. Il **ne conserve pas l'association vérifiable citation ↔ répondant ↔ réponse complète ↔ tour ↔ identifiant de l'entretien**. Une citation peut provenir d'un entretien LLM réalisé *pendant la rédaction* ; elle prouve alors une réponse **simulée à un entretien**, non une publication du run d'origine. L'Epic 014 a justement introduit cette distinction. Il faut la rendre structurelle et testable, plutôt que fonder l'origine d'un fragment sur une proximité textuelle.

### D03 — Barrière qualité : contrôle structurel littéral, contrôle des actions contourné (P0)

**Code :** [`backend/app/services/report_quality_gate.py#L412-L658`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/report_quality_gate.py#L412-L658).

- La présence d'une section de limites est décidée par **quelques sous-chaînes codées en dur** (FR/EN). Le rapport possède une section « Les verrous réels et les leviers qui fonctionnent (ou pas) » avec de nombreuses limites, mais elle ne satisfait pas l'intitulé contractuel : rejet structurel compréhensible, à rendre prévisible dès le plan.
- Avec `action_claims=[]`, le validateur classe le rapport comme **conceptuel** et renvoie seulement un `warning`, même si le texte relate effectivement des actions. C'est une classification ratée en amont. Ne pas rendre le contrôle permissif ; corriger la source et prévoir une catégorie `UNPARSEABLE_ACTION_CLAIMS`.
- La validation d'adoption cherche des mots comme `souscri`, `abonn`, `pay` dans des claims vérifiés. Le mot-clé n'est **pas** une preuve transactionnelle, et le même rapport peut contenir des verbes niés ou cités.

### D04 — Confusion entre nature, pertinence et rôle commercial des acteurs (P0)

**Code :** [`backend/app/services/actor_classifier.py#L40-L79`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/actor_classifier.py#L40-L79), `ONTOLOGY_ROLE_MAPPING`, et [`backend/app/models/cohort_coverage.py#L421-L455`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/models/cohort_coverage.py#L421-L455).

- `organization` → `eligible` au stade ontologique est légitime **pour certaines simulations**. Ce n'est toutefois pas la preuve que l'organisation doit incarner un compte social dans le scénario courant.
- La qualification laisse figurer des logiciels ou plateformes ayant une étiquette `Organization` (dans ce dossier : Stripe et Wix), une institution (CPAM) et l'entreprise objet de l'étude. L'usage de certaines de ces entités peut être légitime dans d'autres thèmes, mais il doit découler du **brief**, pas seulement du type de nœud.
- Les statuts de plusieurs personnes sont `UNKNOWN` (y compris une praticienne pilote et une formatrice). `CohortCoverageTable.prospect_members` retient **tous les membres non marqués** `NOT_APPLICABLE`, hors quelques rôles exclus. Les `UNKNOWN`, pilotes et formatrices peuvent donc gonfler le dénominateur ; le dossier récent affiche **11** membres au dénominateur alors que la cible commerciale en comprend moins.
- Les états peuvent diverger selon la source : Florence est `HESITANT` dans la cohorte et refuse explicitement dans le rapport ; Émilie est `REJECTED_EXPRESSED` dans la cohorte mais est décrite comme ajournant. On ne sait pas encore si le classifieur de décision ou la synthèse a raison.

### D05 — Cohérence biographique détectée en amont, non garantie dans le rapport (P1)

**Code :** [`backend/app/services/brief_consistency.py`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/brief_consistency.py), `audit_brief_persona_consistency()` ; appel dans [`simulation_manager.py`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/simulation_manager.py#L833-L859).

Le fichier `brief_consistency.json` est `is_consistent: true` avec 0 contradiction. Le rapport introduit néanmoins un historique biographique « installée depuis 17 ans » pour une persona dont la fiche de départ décrit une activité bien plus récente. **Le contrôle actuel porte sur brief ↔ fiches générées et sur des épisodes caractéristiques**, pas sur l'ensemble des faits nouveaux de la prose finale. Ce n'est pas la preuve que la story 014-4 est ratée ; c'est un **autre niveau de contrôle** qui manque.

### D06 — Origine documentaire et horizon restent partiellement implicites (P1)

- `source_manifest(2).json` identifie les fichiers de type `CANONICAL_DOCUMENT` et `PERSONA_SPECIFICATION` : bon socle. Mais les trois portent `role=facts`, `validation_status=unvalidated` et `total_chunks=0`. Ne pas les qualifier automatiquement de « sources vérifiées » ni traiter une fiche fictive comme histoire réelle.
- `simulation_brief(2).json` contient « 72 h » dans `goal` mais laisse `time_horizon`, `rules`, `hypotheses`, `target_audiences` et `excluded_actors` vides. `run_manifest(2).json` contient `simulation.time_horizon=null`. Les 72 heures sont retrouvées ailleurs, mais le contrat machine n'est pas rempli.
- Le dossier d'audit contient `git_commit=unknown-git-commit`. Le modèle a un raisonnement demandé `high`, effectif `unknown` et un coût `null`, ce qui empêche de prouver la reproductibilité exacte et le respect effectif d'un plafond monétaire.

### D07 — « Sources & Provenance » surcertifie encore le rapport (P0)

La section finale de `report(2).md` affirme que « toute affirmation qualifiée d'action observée est reliée à un événement horodaté », tout en affichant **0 assertion portant `evidence_refs`** et **0 `provenance_regime`**. La section est désormais générée *après* le registre dans [`report_agent.py#L2681-L2698`](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/report_agent.py#L2681-L2698), et une partie des chiffres est calculée depuis celui-ci ; **mais il reste un libellé de garantie générale** qui n'est pas conditionné par la qualité des claims. La sortie doit certifier uniquement ce que les références prouvent.

---

## 3. Solution cible : contrats plutôt que mots-clés

### 3.1 Chaîne proposée

```text
Documents + brief structurés
    ↓
Qualification ontologique → sélection contextuelle → rôles du scénario
    ↓
Profils / simulation OASIS
    ↓
EvidenceLedger append-only (actions exécutées, identifiants, horodatages)
    + InterviewLedger séparé (entretiens de rédaction, origin=interview)
    + DocumentaryLedger (documents/faits avec version et statut)
    ↓
ReportAgent : compose des énoncés structurés + preuves explicites
    ↓
ClaimValidator : vérifie actor_id, source_id, type, chronologie, portée
    ↓
ReportRenderer : génère Markdown + sections contractuelles
    ↓
QualityGate (sur le même registre, fail-closed)
    ↓
Export versionné / publication ou failed_validation motivé
```

**Compatibilité :** conserver `report_claims.json`, `observed_events.jsonl` et les API existantes ; enrichir les schémas par version, ou ajouter des index/artefacts sans casser les consommateurs. La migration doit être indépendante des noms des personnages et de la langue.

### 3.2 Contrat minimal de preuve

```json
{
  "claim_id": "clm_...",
  "statement": "L'agent X a commenté la publication Y",
  "claim_type": "OBSERVED_ACTION",
  "origin": "simulation_event",
  "actor_id": "actor_...",
  "evidence_refs": [{"kind": "action", "id": "evt_...", "source_snapshot": "snap_..."}],
  "quote_mode": "paraphrase",
  "verification_status": "VERIFIED",
  "limitations": []
}
```

Pour les interviews, un claim analogue utilise `origin=report_interview` et `interview_id`/`turn_id`. Une réponse d'entretien peut être vérifiée comme **citation de cette réponse**, sans jamais être promue en action du run figé. Les conclusions analytiques peuvent rester `INFERENCE`, avec références de soutien et degré d'incertitude ; leur statut ne doit pas être interprété comme « mensonge » simplement parce qu'elles ne sont pas des actions exécutées.

### 3.3 Deux décisions séparées pour chaque acteur

```text
ontology_role        = person | organization | product | concept | ...
can_act_in_world      = true | false | review
selected_for_scenario = true | false | review
scenario_role         = subject | prospect | founder | existing_user | trainer | observer | ...
conversion_eligible   = true | false | unknown   # uniquement si le scénario étudie une conversion
```

Les **rôles sont déclarés et résolus par le scénario** (avec arbitrage en cas d'ambiguïté), jamais inférés d'un tarif ou d'un nom. Le nombre d'acteurs et la distribution des rôles sont des paramètres, non des valeurs globales. Une institution peut être centrale pour une simulation de politique publique ; un éditeur peut intervenir dans un scénario logiciel. Ne pas les exclure universellement.

---

## 4. Backlog correctif recommandé

### STORY P0-1 — Typage des claims et préservation des preuves

**Objectif :** ne jamais perdre la référence à l'événement ou à l'entretien en convertissant des résultats d'outils en prose.

**Travail :**
1. Découpler l'extraction du registre de l'analyse ligne-par-ligne du Markdown : privilégier un flux d'assertions typées produit à la rédaction (JSON Schema/Pydantic validé) ou un passage d'extraction structuré contrôlé, avant le rendu final.
2. Stocker `evidence_ref` dans l'énoncé lui-même, et non le chercher après coup dans la phrase.
3. Conserver le parseur actuel comme **adaptateur legacy**, avec tests et métriques distinctes ; retirer la logique naïve de préfixes de verbes du chemin critique.
4. Refuser qu'un `UNSUPPORTED` soit considéré comme action observée ; les assertions « compte suivre » et « a suivi » doivent rester distinctes, indépendamment de la langue.
5. Effectuer une vérification des relations acteur–action–cible–instant ; un `event_id` existant mais appartenant à un autre agent ne suffit pas.

**Fichiers :** `report_agent.py`, `models/report_claim.py`, `models/provenance_regime.py`, vérificateur d'actions existant, `tests/test_report_claim_epistemic.py`, `tests/test_report_claims_reconciliation.py`.

**AC :** sur la fixture R8, les actions explicitement rapportées sont classées comme actions ou comme « non vérifiables », mais **jamais 0 par défaut** ; toute action certifiée a un identifiant valide du bon agent ; une même citation ne peut être revendiquée à tort par deux auteurs. Une absence de preuve bloque la certification de l'assertion, pas la persistance du rapport en brouillon.

**Bénéfice :** chaînes de preuve auditables. **Coût :** évolution du schéma et du parcours de rédaction. **Risque :** compatibilité des anciens rapports ; prévoir migration et lecture v1/v2.

### STORY P0-2 — Journal d'entretiens complet et stable

**Objectif :** permettre à un évaluateur de retrouver la phrase exacte, son auteur et son origine sans confondre « l'agent a déclaré en entretien » avec « l'agent a publié pendant la simulation ».

**Travail :** enregistrer chaque réponse comme `interview_id`, `question_id`, `actor_id`, `mode`, `started_at`, `answer_text`, `key_quotes` avec offsets ou spans, `run_snapshot_id`, `model_config` et éventuellement référence à l'entretien archivé si le mode replay l'autorise. Remplacer l'aplatissement de toutes les citations dans une liste commune. Conserver la distinction épistémique de l'Epic 014 (`interview ≠ event`). Éviter de dupliquer secrets et données sensibles dans les exports : minimisation/masquage par politique.

**Fichiers :** `report_agent.py` (`interview_agents`), modèle de résultat d'entretien et service associé, `simulation_audit_service.py`, `evidence_snapshot_service.py`, tests des interviews et snapshots.

**AC :** toute citation verbatim possède un offset qui retrouve exactement le même texte dans une réponse identifiée ; une paraphrase est explicitement rendue sans guillemets ; zéro promotion d'entretien en action OASIS.

**Bénéfice :** citations authentifiables ; **coût :** stockage et adaptation des interfaces ; **risque :** confidentialité/volume, maîtrisés par politique de rétention.

### STORY P0-3 — QualityGate sur affirmations réellement extraites

**Objectif :** empêcher les faux avertissements « rapport conceptuel » et les certifications incohérentes.

**Travail :**
1. Le validateur doit échouer ou demander revue si le document contient des assertions d'actions qui n'ont **pas pu être parsées**, avec une catégorie distincte de `UNSUPPORTED`.
2. `Sources & Provenance` ne doit jamais affirmer une couverture complète si `verified_action_claims < asserted_action_claims` ou si des citations directes sont orphelines.
3. Les preuves d'adoption/transaction sont typées par le **contrat d'action du scénario**, pas déduites d'un mot-clé dans une publication ou d'un clic « suivre ».
4. Refuser toute preuve associée au mauvais `actor_id`, à une source non déclarée ou à un événement hors horizon ; préserver le rapport en brouillon et exposer diagnostics + références absentes.
5. La section « limites » doit être un **`section_id` contractuel** (`limitations`, nom localisé à l'affichage) ; ne pas relâcher le contenu exigé. Le générateur reçoit ce contrat dès le plan, puis le rendu et le QualityGate le vérifient par ID et contenu, pas par une liste de titres littéraux.

**Fichiers :** `report_quality_gate.py`, `report_agent.py` (plan/rendu), `models/report_quality.py`, `tests/test_report_quality_gate_audit.py`.

**AC :** R8 ne passe plus sous le label `conceptual report` avec 0 action ; le rapport échoue pour ses vrais défauts de traçabilité et/ou est régénéré proprement avec `limitations`. Un rapport de théorie pure, sans action affirmée, reste autorisable dans un *autre* scénario prévu comme tel.

**Bénéfice :** certification crédible ; **coût :** règles et tests ; **risque :** plus de `needs_review` au début, souhaitable.

### STORY P0-4 — Sélection contextuelle et rôles explicites

**Objectif :** séparer capacité à agir dans le monde et rôle pertinent dans un scénario donné.

**Travail :**
1. Ajouter un `ScenarioParticipationPolicy` applicable aux acteurs qualifiés : `include`, `exclude`, `review`, fondés sur les audiences, types d'actions, scénario et contraintes, avec possibilité de correction humaine explicite.
2. Ne pas changer la règle générale `organization -> eligible` au niveau ontologique ; n'instancier une organisation que si sa participation est pertinente ou voulue.
3. Résoudre les rôles métier à partir du brief structuré et des profils, puis conserver `UNKNOWN` quand l'information manque (et demander revue si le rôle est essentiel à une métrique).
4. Dans `prospect_members`, exclure **par inclusion positive** tous les acteurs dont `conversion_eligible != true` au lieu d'exclure seulement quelques rôles connus. Émettre `null/not_evaluable` si la population éligible est inconnue ou nulle.
5. Ne pas classer un acteur comme « a adopté » sur la simple présence de sentiments positifs. Distinguer `INTERESTED`, `DEMO_REQUESTED`, `INTENTION_EXPRESSED`, `ADOPTED_VERIFIED`, `NO_DECISION`.

**Fichiers :** `actor_classifier.py`, `models/actor_selection.py`, `simulation_manager.py`, `models/cohort_coverage.py`, `tests/test_cohort_roles_and_decisions.py`, `tests/test_actor_selection.py`.

**AC :** un logiciel ou une société citée seulement comme objet de conversation n'est pas automatiquement incarné ; une organisation **explicitement demandée** reste simulable ; seuls les prospects déclarés entrent dans un taux commercial ; la seule existence d'un avis favorable ne crée aucune transaction.

**Bénéfice :** généricité et cohérence des statistiques ; **coût :** contrat de rôles ; **risque :** cohortes moins nombreuses si le brief est ambigu — afficher l'incertitude au lieu de créer des rôles arbitraires.

### STORY P1-5 — Vérification de cohérence des faits du rapport

**Objectif :** ne pas considérer qu'un audit brief ↔ profils suffit à valider la prose finale.

**Travail :** introduire un `FactLedger` de faits explicitement sourcés et typés (`source_kind`, `subject_id`, `predicate`, `value`, `validity`, `confidence`, `doc_id`, `span`). Contrôler les assertions de faits stables du rapport contre le registre, signaler les conflits (`CONTRADICTED_BY_CANONICAL`, `DOCUMENT_CONFLICT`, `NOT_ESTABLISHED`), sans prétendre démontrer qu'une **opinion** est vraie ou fausse. Inclure un contrat optionnel de factualité pour la parole des représentants d'une organisation, fondé sur les mêmes sources, jamais sur des fonctionnalités codées en dur.

**Fichiers :** `brief_consistency.py`, `models/source_document.py`, `report_agent.py`, nouvelle couche de résolution de faits, tests inter-domaines.

**AC :** une expérience biographique attribuée au mauvais agent et une durée d'expérience contradictoire sont détectées ; les désaccords d'opinion entre agents restent possibles et ne sont pas bloqués.

**Bénéfice :** moins de faits inventés ; **coût :** extraction et stockage de faits ; **risque :** faux positifs sur sources ambiguës, à déclarer et arbitrer.

### STORY P1-6 — Brief, provenance des documents, horloge et reproductibilité

**Objectif :** rendre explicite ce qui est actuellement seulement inféré.

**Travail :** normaliser le brief après extraction (`time_horizon`, `rules`, `target_audiences`, `excluded_actors`, `hypotheses`, `expected_outputs`) en conservant `value`, `origin` et `is_inferred`; validation humaine facultative selon politique. Une durée peut être déduite d'un texte, mais doit être persistée et explicite dans l'export. Les sources sont `declared/unvalidated/validated`, avec leur nature (`canonical`, `persona`, `historical`, `hypothesis`) et priorité ; ne pas qualifier `unvalidated` de « vérifié ». Conserver l'empreinte de chaque source et le SHA du code exécuté si disponible, sinon indiquer clairement `unavailable`. L'absence de tarif de token ne doit pas autoriser à prétendre respecter un plafond USD : rendre la politique de budget vérifiable (`cost_unknown`, `token_cap` ou refus de configuration).

**Fichiers :** `models/simulation_brief.py`, `simulation_audit_service.py`, `evidence_snapshot_service.py`, `models/source_document.py`, `report_usage_tracker.py` et tests associés.

**AC :** dans un nouveau run, l'horizon utilisé par le moteur apparaît identiquement dans brief et manifeste avec son origine ; le SHA représente le commit du code de l'exécution et non celui de l'audit ultérieur ; `reasoning_effort_effective=unknown` et `cost=unknown` restent des incertitudes explicites, jamais des valeurs imputées.

**Bénéfice :** benchmark reproductible ; **coût :** enrichissement des artefacts ; **risque :** migration des runs anciens.

### STORY P1-7 — Tests d'intégration, qualification indépendante et coût

**Objectif :** démontrer les corrections sur des données figées avant de payer une nouvelle simulation OASIS.

**Travail :** relecture du dossier R8, test de compilation et de sauvegarde avec `replay_frozen`; harnais séparant `action`, `interview`, `document`, `inference`; mesure de précision/rappel des types de claims et de la couverture des citations. Scénarios synthétiques autres que le dossier étudié (voir §5). Comparer *à traces identiques* un modèle et deux niveaux de raisonnement seulement après stabilisation des contrôles.

**Bénéfice :** moins d'itérations coûteuses ; **coût :** fixtures/test harness ; **risque :** tests trop spécifiques — corriger avec corpus multi-domaines.

---

## 5. Scénarios de recette obligatoires

Les tests suivants définissent le comportement attendu, pas la solution d'implémentation. Pour chaque test, vérifier `report_claims`, `quality_checks`, rendu Markdown et export.

| ID | Scénario | Résultat attendu |
|---|---|---|
| AT-01 | Texte « A a répondu au post de B », événement présent et lié à A | Claim `OBSERVED_ACTION` + `event_id` + `VERIFIED` |
| AT-02 | Même phrase mais événement absent | `UNSUPPORTED` / `NEEDS_REVIEW` ; aucune certification |
| AT-03 | `event_id` existe mais appartient à C | Référence invalide ; rejet de l'attribution à A |
| AT-04 | Réponse à un entretien de rédaction citée verbatim | `origin=interview`, `interview_id`, `turn_id`, offset exact ; **pas** action OASIS |
| AT-05 | Reformulation d'un entretien entre guillemets, non verbatim | Reformulation sans guillemets ou statut « citation non authentifiée » |
| AT-06 | Persona 0 action nommé comme ayant publié | Rapport non certifié et attribution corrigée/signalée |
| AT-07 | Agent qui « suit » un compte social présenté comme ayant acheté un abonnement | Erreur de type, aucune adoption vérifiée |
| AT-08 | Équipe interne et formateur présents avec des prospects | Dénominateur fondé uniquement sur `conversion_eligible=true` |
| AT-09 | Société de transport attendue comme agent institutionnel dans scénario de grève | Organisation simulée correctement (contre-test à l'exclusion universelle) |
| AT-10 | Société citée comme objet d'une comparaison produit, sans rôle social | Non instanciée à défaut d'inclusion explicite |
| AT-11 | Conclusion contredit un fait biographique source, l'opinion diverge d'une autre opinion | Fait signalé ; opinion autorisée |
| AT-12 | Section limites présente mais intitulé libre | `section_id=limitations` reconnu ; contenu contrôlé |
| AT-13 | Section limites absente malgré objections | Rejet avec diagnostic ciblé |
| AT-14 | 0 claim vérifié mais prose affirmative certifiant « toutes les actions sont prouvées » | Rejet de certification et correction de la section provenance |
| AT-15 | Entretien hors fenêtre de simulation | Explicitement étiqueté post-run, sans être comptabilisé parmi les actions temporelles |
| AT-16 | Brief indique « 72 heures », champ structuré vide | Inférence persistée avec origine ; manifeste cohérent |
| AT-17 | Modèle demandé `high`, effort effectif et coût inconnus | Export honnête, pas de prétention de coût inférieur au plafond |
| AT-18 | Replay du même snapshot, modèle identique | Même jeu de preuves, aucune modification des données figées |
| AT-19 | Simulation d'un débat associatif sans aucune vente | Aucune métrique de conversion artificiellement obligatoire |
| AT-20 | Événement lu deux fois depuis log et EvidencePack | Une seule référence canonique d'action, variantes de source conservées |

**Fixtures :** `R8` réel comme test d'intégration interne **sans données personnelles non nécessaires** ; au moins trois scénarios entièrement synthétiques : vente d'un logiciel, débat d'une association locale, perturbation de transport public. Les valeurs, identités et vocabulaires spécifiques d'une fixture **ne doivent jamais apparaître** dans les classes, règles de validation ou prompts globaux.

## 6. Plan de mise en œuvre, ordre et définition de terminé

1. **Avant tout nouveau développement :** exécuter les tests au HEAD `e02c4ac` ; comparer le comportement attendu aux 4 stories `done` de l'Epic 014. Le nouveau rapport précède le dernier commit. Documenter ce qui est déjà corrigé. Ne pas réouvrir une story clôturée sans reproduire la régression sur ce commit.
2. **P0-1 puis P0-2 :** introduire les références structurées et les transcriptions complètes sans modifier le format des archives existantes.
3. **P0-3 :** faire consommer au QualityGate **le même registre** que le ReportRenderer ; bannir les certifications littérales indépendantes du registre.
4. **P0-4 :** rôles et pertinence contextuelle des acteurs ; recalculer les métriques sans inventer de transactions.
5. **P1-5/6 :** factualité des biographies, sources, horizon, SHA, budget.
6. **P1-7 :** qualification sur replay figé et matrice multi-domaines ; seulement ensuite relancer une simulation complète.

**Definition of Done :**

- Aucune assertion présentée comme *observed* ou *verbatim* sans une référence exacte valide ; sinon le rapport la dégrade/supprime ou reste `failed_validation`.
- Une citation d'entretien n'est jamais comptée comme action OASIS ; une citation d'action n'est jamais attribuée au mauvais acteur.
- L'index d'identités est injecté et contrôlé à chaque frontière (profil, simulation, audit, rapport).
- Une section requise est liée à un `section_id`, non à un titre français particulier.
- `is_publishable=true` signifie que tous les contrôles **critiques** applicables au type de scénario passent ; les rapports conceptuels et les scénarios sans adoption restent pris en charge.
- `report_claims.json`, `quality_checks.json` et `Sources & Provenance` racontent **la même situation**, avec références et compteurs cohérents.
- Le rapport conserve le maximum de contenu utile lorsque des claims sont unsupported, mais n'en transforme pas l'incertitude en fait.
- Suite de tests backend existante verte + tests d'intégration multi-domaines + vérification de l'export/empreintes.
- Aucun code métier Keova, tarif, fonction commerciale ou nom de persona en production dans MiroFish.

## 7. Risques et arbitrages techniques

| Option | Bénéfice | Coût/risque | Recommandation |
|---|---|---|---|
| Ajouter des regex au parseur Markdown | Rapide sur un exemple | Fragile en langue, syntaxe, négation et paraphrase | **Non** comme solution principale |
| Rendre le QualityGate permissif | Plus de rapports affichés « publiables » | Certificats mensongers | **Non** |
| Passer directement à un gros LLM | Peut améliorer l'analyse | Coûts élevés ; aucune correction des IDs manquants | **Différer** jusqu'au replay contrôlé |
| Énoncés typés + preuve dès la création | Traçabilité déterministe et indépendante du fournisseur | Modifications de contrats, migration legacy | **Oui, P0** |
| Identifier les agents par nom libre | Implémentation simple | Homonymes, variations de nom, rôles mal attribués | **Non** ; `actor_id` stable |
| Exclure toutes les organisations | Corrige une fixture particulière | Casse les simulations institutionnelles | **Non** ; sélection selon le scénario |

## 8. Liens de code et références internes

* [`report_agent.py` — collecte des entretiens, extraction des claims, ordre audit → provenance → qualité](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/report_agent.py)
* [`report_quality_gate.py` — présence des limites, typage/ratio des actions, adoptions](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/report_quality_gate.py)
* [`cohort_coverage.py` — résolution d'identité, rôles, dénominateur](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/models/cohort_coverage.py)
* [`actor_classifier.py` — mapping ontologique organisation/personne](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/actor_classifier.py)
* [`provenance_regime.py` — rapprochement textuel à 8 mots](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/models/provenance_regime.py)
* [`simulation_manager.py` et `brief_consistency.py` — contrôle biographies, en amont](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/simulation_manager.py)
* [`simulation_audit_service.py` — package d'audit/manifeste](https://github.com/zohac/MiroFish/blob/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/backend/app/services/simulation_audit_service.py)
* [`Epic 014 — Intégrité des preuves de rédaction`](https://github.com/zohac/MiroFish/tree/e02c4ac251aeb16dfc81d7f03b594f7f9d1b5894/docs/plans/014-integrite-preuves-redaction)

### Clarification finale

Le dossier soumis teste un lancement B2B, mais les corrections sont **des invariants de simulation** : « un énoncé est justifié par une source », « un acteur possède un rôle », « une citation a un auteur », « une action n'est pas une intention », « un contrôle ne certifie pas ce qu'il n'a pas vérifié ». Le code doit rester utilisable sur **n'importe quel sujet et n'importe quelle simulation**.
