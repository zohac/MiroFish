# PRD — Epic 012 : Fiabilité des acteurs, intégrité des preuves et publication stricte

> **Statut :** Validé — En cours  
> **Date de création :** 17 octobre 2026  
> **Auteur :** Antigravity & Équipe MiroFish  
> **Branche de travail :** `local-first`  
> **Contexte empirique :** Audit réel de la sixième simulation (`sim_ea4f3cfe1028`, rapport `report_77d96ea4c1c9`, dossier `docs/retour-essai-6/`)  
> **Dépendances :** Epic 005 (Docker local), Epic 007 (Ontologie dynamique), Epic 008 (Localisation FR), Epic 009 (Éligibilité des acteurs), Epic 010 (Cycle de vie des simulations), Epic 011 (Preuve par les faits simulés)  
> **Portée :** Architecture et qualité génériques du moteur de simulation MiroFish (0 comportement spécifique codé en dur).

---

## 1. Contexte & Problématique

L'Epic 011 a introduit les mécanismes fondamentaux de traçabilité et de preuve : journalisation des événements réels d'OASIS (`observed_events.jsonl`, SQLite), extraction de revendications vérifiables (`report_claims.json`), tableau de couverture de cohorte (`cohort_coverage.json`), garde-fou d'horizon temporel, et barrière de publication (`quality_checks.json`, archive d'audit scellée SHA-256).

Cependant, l'épreuve réelle menée sur la sixième simulation complète (cas réel Keova : 16 agents instanciés, 72 heures simulées, 40 rounds, 44 entités dans le catalogue de graphe) et son audit contradictoire approfondi ont révélé des écarts critiques entre la **présence** de ces outils et leur **efficacité de contrôle effectif** :

1. **Collision d'identités d'agents (`COVERAGE_ALIAS_COLLISION`)** : Dans `CohortCoverageTable.build_from_simulation`, le rapprochement par sous-chaîne (`key in ev_agent_lower or ev_agent_lower in key`) provoque la fusion accidentelle des 23 événements de l'agent `Agent_1` dans le profil de l'agent `Agent_16` !
2. **Confusion de population et dédoublement (`DUPLICATE_COHORT_VIEW`)** : Le tableau de cohorte itère sans distinction sur les 44 entités du graphe sans filtrer sur l'éligibilité (`eligibility_status == "eligible"`), y ajoutant des identifiants techniques `Agent_X` en doublon des personas nommés, ce qui gonfle la cohorte à 63 membres et introduit des entités inéligibles (organisations tierces, outils de paiement) dans les décomptes de prospects.
3. **Attribution naïve des rôles et statuts d'adoption (`SCENARIO_ROLE_INVALID` & `ADOPTION_NONPROSPECT`)** : `ScenarioRole.from_actor_role` classe toute entité de type `PERSON` comme `PROSPECT` (y compris les fondateurs et pilotes), tandis que l'absence d'objection textuelle explicite suffit actuellement à qualifier un agent actif en `ADOPTED`, créant de faux taux d'adoption commerciale sans aucune transaction réelle sous-jacente.
4. **Déconnexion complète claims ↔ traces réelles (`ZERO_VERIFIED_CLAIMS`)** : Sur 258 claims extraits dans `report_claims.json`, **0 claim est vérifié (`0 VERIFIED`)**, 241 sont `UNSUPPORTED` et 17 `CONTRADICTED`. Le parseur heuristique de `ReportAgent` capture des mots génériques (« Si », « Dès ») comme noms d'agents et attend des identifiants littéraux `evt_*` dans le texte Markdown, absents des rédactions en langage naturel.
5. **Barrière de publication laxiste (« Fail-Open »)** : `ReportQualityGate` attribue `is_publishable=true` avec statut `warning`, alors même que le ratio d'assertions événementielles vérifiées est de **0,0 %** et qu'aucune action alléguée n'est corrélée à une trace réelle.

L'**Epic 012** résout ces anomalies pour garantir que la cohorte est sans collision, que les décisions sont déterministes et étayées, que les claims sont réconciliés de manière robuste avec l'`EvidencePack`, et que la publication applique une barrière stricte en mode « Fail-Closed ».

---

## 2. Objectifs Chiffrés & Critères de Sortie (C1 à C8)

| Critère | Description | Cible |
|---|---|---|
| **C1** | **Zéro collision d'identités** : Rapprochement exact par identifiant d'instance OASIS stable (`agent_id` int) et égalité stricte normalisée des noms. 0 événement de `Agent_1` comptabilisé chez `Agent_16`. | **0 collision (0 % d'erreur d'attribution)** |
| **C2** | **Cohorte d'intérêt filtrée et dédoublonnée** : Distinction nette entre `actor_catalog` (entités du graphe), `simulation_participants` (agents lancés) et `target_cohort` (profils d'intérêt). Exclusion stricte des entités inéligibles. 0 alias technique `Agent_X` en doublon d'un persona nommé. | **Parité exacte avec les participants et profils éligibles réels** |
| **C3** | **Rôles de scénario fidèles et statut d'adoption étayé** : Rôles issus des profils effectifs ou du brief (`FOUNDER`, `EXISTING_USER`, `PROSPECT`, etc., avec repli `UNKNOWN` sans préjuger du rôle). Statut `ADOPTED` strictement réservé aux actions métier vérifiées ; sinon `NO_DECISION` / `INTERESTED` / `DEMO_REQUESTED`, et `NOT_APPLICABLE` pour les fondateurs et organisations. | **0 faux statut `ADOPTED` déduit de la seule absence d'objection** |
| **C4** | **Réconciliation robuste des claims avec l'`EvidencePack`** : Rapprochement déterministe des assertions d'actions réelles avec les traces d'événements observés (par persona, round et action), filtrage strict des faux noms d'agents (« Si », « Dès »). | **$\ge 80\ %$ de claims d'actions effectivement observées vérifiés sur un run nominal** |
| **C5** | **Barrière de publication Fail-Closed** : Statuts explicites `draft` / `needs_review` / `verified_publishable` / `failed_validation`. Rejet strict de la publication certifiée (`is_publishable=false` ou `needs_review`) si 0 claim événementiel n'est vérifié ou en présence de contradictions critiques. | **0 rapport certifié « vérifié » avec 0 claim vérifié** |
| **C6** | **Détection des conflits de provenance et brief structuré** : Priorité absolue du type épistémique (`PERSONA_SPECIFICATION` prévaut sur `role=facts`), détection explicite des lacunes de brief (horizon temporel, règles, audiences). | **0 classification historique erronée de documents de personas** |
| **C7** | **Fixture de régression du run réel R6** : Intégration d'une fixture de test basée sur les anomalies de R6 prouvant l'invalidation propre de l'ancien export erroné et la validation des exports conformes. | **100 % de conformité sur le jeu R6** |
| **C8** | **Non-régression globale** : Intégralité des 1 761 tests backend existants au vert + nouvelle suite de tests hermétiques. | **$\ge 1785$ tests verts sur l'hôte**, 0 échec |

---

## 3. Exigences Fonctionnelles (FR)

- **FR-01 : Table de résolution d'identités sans collision (`AgentIdentityResolver`)** :
  Associer chaque événement d'action OASIS à son émetteur via `agent_id` (identifiant entier) ou égalité stricte normalisée. Interdiction formelle du matching par inclusion partielle (`key in text`).
- **FR-02 : Filtrage de la cohorte et séparation des populations** :
  Filtrer `actor_selection.actors` sur le statut d'éligibilité (`eligibility_status == "eligible"`). Éliminer les identifiants techniques doublons lorsqu'un persona nommé est associé à l'agent.
- **FR-03 : Qualification honnête des décisions et des rôles de scénario** :
  Ne jamais déduire `ADOPTED` d'un sentiment positif ou de l'absence d'objections. Définir des statuts nuancés (`NO_DECISION`, `INTERESTED`, `DEMO_REQUESTED`, `REJECTED_EXPRESSED`, `ADOPTED_VERIFIED`). Attribuer `NOT_APPLICABLE` pour les fondateurs et entités non clientes.
- **FR-04 : Extraction et réconciliation robuste des claims** :
  Valider les noms d'agents contre le catalogue réel des personas. Rapprocher les affirmations d'actions observées avec l'`EvidencePack` sans dépendre d'IDs textuels `evt_*` dans le corps rédigé.
- **FR-05 : Barrière de publication stricte (« Fail-Closed »)** :
  Introduire les statuts de publication `draft`, `needs_review`, `verified_publishable`, `failed_validation`. Bloquer la certification si le ratio de claims vérifiés est insuffisant ou nul.
- **FR-06 : Traçabilité et diagnostic de provenance** :
  Signaler les conflits entre `epistemic_kind` et `role`. Assurer la complétude du manifeste d'exécution (`git_commit`, `completed_at`, horizon temporel).

---

## 4. Exigences Non Fonctionnelles (NFR)

- **NFR-1 : Généricité absolue (Zéro hardcoding)** : Aucune règle ne doit contenir de termes propres au domaine Keova. Tous les mécanismes doivent être universellement applicables à n'importe quel sujet (politique publique, télécom, RH, etc.).
- **NFR-2 : Herméticité et déterminisme** : Les calculs de cohorte, d'identités, de statuts et de claims doivent être déterministes à 100 % pour un jeu d'entrées donné.
- **NFR-3 : Rétrocompatibilité des formats** : Capacité de relire sans crash les anciens fichiers `cohort_coverage.json` et `report_claims.json` produits lors des runs antérieurs.
- **NFR-4 : Préservation de la réactivité** : Aucun impact mesurable sur le temps de calcul lors de la génération de rapport (< 100 ms pour l'audit de cohorte et de claims).
