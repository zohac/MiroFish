---
id: "012-3"
epic: "012"
titre: "Extraction d'assertions assainie et réconciliation déterministe avec l'EvidencePack"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 012-3 — Extraction d'assertions assainie et réconciliation déterministe avec l'EvidencePack

Lot B, priorité **P0**. En tant qu'analyste et utilisateur de MiroFish, je veux que les affirmations extraites du rapport de simulation soient fiables, exemptes d'agents fantômes (« Si », « Dès », titres de section), et que les affirmations prétendant relater des actions d'acteurs soient réconciliées de manière déterministe et sémantiquement probante avec les traces réelles de l'`EvidencePack` (sans exiger que le texte Markdown contienne des identifiants techniques `evt_*` écrits en dur), afin d'atteindre un taux de vérification authentique d'au moins 80 % sur les actions observées réelles.

Cette story répond directement à l'exigence fonctionnelle **FR-04** (extraction et réconciliation robuste des claims) et valide le critère de sortie **C4** (réconciliation déterministe des claims avec l'`EvidencePack` : $\ge 80\ \%$ d'actions observées vérifiées sur un run nominal, 0 faux agent) de l'Epic 012.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  - Assainir `ReportAgent.extract_claims_from_content` : éliminer catégoriquement l'extraction de faux agents (« Si », « Dès », mots courants, conjonctions) en validant systématiquement les candidats contre le catalogue des participants réels (`AgentIdentityResolver` / `ActorSelection`).
  - Exclure formellement les titres Markdown (`#`, `##`, `###`) de la détection de claims factuels.
  - Découpler la réconciliation de l'exigence d'identifiants `evt_*` littéraux dans le texte rédigé du rapport : permettre l'appariement déterministe entre l'affirmation rédigée et les événements réels de l'`EvidencePack` (par persona, round/temps et contenu/action).
  - Dans `SimulationActionVerifier.verify_report_claim`, remplacer le matching par sous-chaîne `in` par la résolution univoque via `AgentIdentityResolver`.
  - Durcir le contrôle sémantique : vérifier que le contenu de l'action correspond réellement à la teneur de l'affirmation (contrôle verbatim des citations, interdiction d'assimiler un post social à une souscription ou un achat métier).
  - Attribuer automatiquement les `event_id` correspondants dans `evidence_refs` et documenter les motifs d'échec dans `limitations` pour les claims `UNSUPPORTED`.
- [x] **Documents consultés** :
  - [PRD Epic 012](prd.md) : §2 (Critère C4), §3 (FR-04), §4 (NFR-1, NFR-2, NFR-3, NFR-4).
  - [Architecture Epic 012](architecture.md) : §1 (Flux global), §2.3 (Réconciliation Robuste Claims $\leftrightarrow$ EvidencePack).
  - [Hub Epic 012](epic-012.md) : FR-04, critère C4.
  - [Audit R6](../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md) : anomalie critique `ZERO_VERIFIED_CLAIMS` (241 claims `UNSUPPORTED` sur 258, mots génériques « Si », « Dès » pris pour des agents).
  - `backend/app/services/report_agent.py` : `extract_claims_from_content` (l. 2605-2700), `audit_and_save_report_claims` (l. 2746-2806).
  - `backend/app/services/simulation_action_verifier.py` : `verify_report_claim` (l. 790-970).
  - `backend/app/models/report_claim.py` : dataclasses `ReportClaim`, `ReportClaimRegistry`, enums `ClaimKind`, `VerificationStatus`.
  - `backend/app/models/evidence_pack.py` : `EvidencePack`, `ObservedEvent`.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (herméticité des tests), §2.8 (gestion des plans).
- [x] **Dépendances résolues** :
  - Stories 012-1 et 012-2 validées et closes (résolution univoque d'identités `AgentIdentityResolver`, rôles et statuts déterministes).
  - Filet de tests au démarrage : **1 785 tests réussis sur l'hôte**, 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Validation nominative stricte des sujets d'assertions** :
     - Pour être retenu comme `agent_name` d'un claim, le nom candidat extrait par regex doit être validé contre les personas réels (`resolver.get_known_names()` ou `actor_selection.get_eligible_names()`).
     - Liste noire absolue des mots français/anglais courants en tête de phrase (« Si », « Dès », « Tout », « En », « Selon », « Après », « Par », « Or », « Donc », « Plus », « Tous », « Alors », « Bien », « Ces », « Dans », « Pour », « If », « As », « When », « Then ») et filtrage des titres Markdown.
  2. **Extraction sans dépendance d'identifiants techniques en dur** :
     - L'extraction textuelle identifie l'acteur, le round éventuel, et extrait le verbatim entre guillemets (« ... » ou " ... ") ou la description d'action.
     - Les `evidence_refs` peuvent être pré-remplis si un `evt_*` est présent, mais leur absence n'empêche nullement la réconciliation par `SimulationActionVerifier`.
  3. **Réconciliation déterministe avec l'`EvidencePack`** :
     - Filtrage des événements de l'acteur via `AgentIdentityResolver` (par `agent_id` int ou égalité stricte normalisée).
     - Rapprochement temporel : si un round est mentionné, priorité aux événements de ce round.
     - Rapprochement sémantique et textuel : correspondance verbatim (normalisée) de citation, ou présence de termes clés de l'action dans le contenu de l'événement (`action_args["content"]` ou `result`).
     - Si une correspondance probante est établie : injection de l'`event_id` dans `evidence_refs`, statut `VerificationStatus.VERIFIED`.
  4. **Principe anti-affabulation et étanchéité des faits** :
     - Rejet strict de la qualification d'action transactionnelle (achat, souscription) à partir de simples posts de réseaux sociaux sans événement applicatif dédié.
     - Tout claim non réconcilié est documenté avec un diagnostic explicite dans `limitations`.
- [x] **Stratégie de tests identifiée** :
  - Test d'extraction vérifiant que des phrases débutant par « Si Simon... » ou « Dès le Round 2... » n'inventent pas d'agents « Si » ou « Dès ».
  - Test validant le rejet des titres Markdown `# Conclusions et Recommandations`.
  - Test de réconciliation réussie d'une action rédigée en langage naturel sans ID `evt_*` avec un événement de l'`EvidencePack` (statut `VERIFIED` + `evidence_refs`).
  - Test de déclassement en `UNSUPPORTED` avec justification diagnostique en cas d'absence d'événement correspondant.
  - Test d'interdiction de conversion d'un simple post social en transaction d'achat.
  - Test de non-régression sur le chargement et la sauvegarde de `report_claims.json`.

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Zéro faux agent extrait (anti-mots parasites)** : Les sujets des affirmations extraites (`claim.agent_name`) sont strictement validés contre les participants réels de la simulation. Les mots de liaison ou débuts de phrase (« Si », « Dès », « Or », « Donc », « Selon », « Après », etc.) ne sont jamais extraits comme noms d'agents. | Test unitaire injectant un corpus Markdown avec phrases complexes et vérifiant qu'aucun mot parasite n'apparaît dans `agent_name`. |
| **AC2** | **Exclusion des titres et en-têtes Markdown** : Les lignes de titres (`#`, `##`, `###`, etc.) ne sont jamais transformées en assertions de faits (`ReportClaim`). Seules les phrases et puces décrivant des observations réelles sont retenues. | Test unitaire confirmant qu'aucun titre de section n'apparaît dans le registre des claims. |
| **AC3** | **Extraction d'actions sans dépendance d'identifiants `evt_*`** : Les phrases décrivant une action sociale ou un comportement simulé sont correctement typées `OBSERVED_SOCIAL_ACTION` même en l'absence totale d'identifiants techniques `evt_*` dans le corps rédigé. | Test unitaire extrayant des affirmations d'actions rédigées naturellement sans `evt_*`. |
| **AC4** | **Réconciliation déterministe avec l'`EvidencePack`** : Pour tout claim d'action observée d'un persona réel, `SimulationActionVerifier` recherche les traces réelles via `AgentIdentityResolver` (sans collision), corrèle le contenu ou la citation, et injecte les `event_id` correspondants dans `evidence_refs` en attribuant `VERIFIED`. | Test d'intégration unitaire réconciliant un claim textuel naturel avec un événement de l'`EvidencePack` avec succès. |
| **AC5** | **Contrôle anti-affabulation et diagnostic transparent** : Une action sans trace réelle ou une prétention d'achat basée sur un simple tweet est déclassée en `REPORTED_INTENTION` ou `UNSUPPORTED` avec motif explicite consigné dans `limitations`. | Test unitaire vérifiant le déclassement motivé et l'enrichissement du champ `limitations`. |
| **AC6** | **Rétrocompatibilité et suite hermétique** : Les exports `report_claims.json` existants restent lisibles via `from_dict`. Filet complet $\ge 1 785$ tests au vert sur l'hôte, 0 régression. | Exécution complète de `pytest` (0 échec, 0 régression). |

---

## Définition de fini

- [ ] Critères d'acceptation **AC1 à AC6** satisfaits et vérifiés par des tests automatisés passants.
- [ ] Parseur de claims `extract_claims_from_content` assaini avec validation des noms contre les personas réels et exclusion des titres Markdown.
- [ ] Réconciliation déterministe sémantique et temporelle dans `SimulationActionVerifier.verify_report_claim` sans recours aux sous-chaînes `in`.
- [ ] Élimination définitive de l'obligation d'avoir des IDs `evt_*` écrits en dur dans le rapport pour vérifier les actions.
- [ ] Suite de tests hermétiques dédiée créée dans `backend/tests/test_report_claims_reconciliation.py`.
- [ ] Non-régression totale sur les suites existantes (`test_report_claim_epistemic.py`, `test_simulation_action_verifier.py`).
- [ ] Filet complet de tests au vert sur l'hôte (filet $\ge 1 795$ tests) et CI conforme.
- [ ] Revue contradictoire BMAD à 4 couches réalisée, findings résolus.
- [ ] Documents de suivi synchronisés (`epic-012.md`, `sprint-status.yaml`, `AGENTS.md`).

---

## Tâches

- [ ] **T1 — Validation des entités et assainissement de l'extraction (`ReportAgent`)** :
  - Injecter le catalogue des participants ou l'`AgentIdentityResolver` dans `extract_claims_from_content`.
  - Ignorer systématiquement les titres Markdown (`startswith("#")`).
  - Filtrer les candidats `agent_name` contre les participants réels et éliminer la liste noire des faux noms (« Si », « Dès », etc.).
- [ ] **T2 — Détection d'actions observées sans IDs techniques `evt_*`** :
  - Extraire les descriptions d'actions, verbatims entre guillemets et références temporelles (rounds) depuis le texte naturel.
  - Qualifier judicieusement le `ClaimKind` (`OBSERVED_SOCIAL_ACTION`, `REPORTED_INTENTION`, `SOURCE_FACT`, etc.).
- [ ] **T3 — Algorithme de réconciliation déterministe dans `SimulationActionVerifier`** :
  - Remplacer le matching d'agent par inclusion de sous-chaîne par la résolution univoque `AgentIdentityResolver`.
  - Implémenter l'appariement sémantique/verbatim entre le claim et l'événement `ObservedEvent` (`action_args["content"]`, citations, types d'actions).
  - Alimenter `evidence_refs` avec les `event_id` authentifiés et basculer à `VerificationStatus.VERIFIED`.
- [ ] **T4 — Durcissement anti-affabulation et traçabilité diagnostique** :
  - Déclasser en `UNSUPPORTED` avec justification dans `limitations` en l'absence de concordance probante.
  - Bloquer toute inférence transactionnelle non étayée par un événement métier.
- [ ] **T5 — Suite de tests hermétiques dédiée et non-régression** :
  - Créer `backend/tests/test_report_claims_reconciliation.py` couvrant AC1 à AC6.
  - Vérifier la non-régression intégrale de la suite de tests du dépôt.
- [ ] **T6 — Revue contradictoire BMAD à 4 couches et clôture** :
  - Mener la revue contradictoire, appliquer les patches requis et synchroniser le statut.

---

## Notes de développement

### Cadrage technique issu de l'audit R6
Dans la simulation réelle Keova R6 (`sim_ea4f3cfe1028` / `report_77d96ea4c1c9`) :
- Le registre `report_claims.json` contenait 258 claims, dont **0 vérifié (`0 VERIFIED`)**, 241 `UNSUPPORTED` et 17 `CONTRADICTED`.
- Le parseur créait des claims sur des phrases comme :
  - `Si Simon avait su...` $\rightarrow$ Agent : « Si » !
  - `Dès le Round 1, la discussion s'est engagée...` $\rightarrow$ Agent : « Dès » !
  - `### 4. Analyse des Dynamiques de Cohorte` $\rightarrow$ Traité comme un fait d'analyse !
- De plus, le vérificateur n'associait des `evidence_refs` que si des identifiants `evt_*` figuraient explicitement dans le Markdown, ce qui n'arrive jamais dans les synthèses rédigées par un LLM.
- La Story 012-3 résout ces dysfonctionnements à la source pour rétablir une traçabilité déterministe et authentique.

---

## Revue

*(Section complétée lors de la revue contradictoire BMAD à 4 couches)*

---

## Notes de complétion

*(Section complétée lors de la clôture de la story)*
