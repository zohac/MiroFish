---
id: "011-3"
epic: "011"
titre: "Contrat structuré ReportClaim, typage épistémique des sources et contrôle anti-affabulation"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 011-3 — Contrat structuré ReportClaim, typage épistémique des sources et contrôle anti-affabulation

Lot B, priorité **P0**. En tant qu'analyste et décideur s'appuyant sur les synthèses de MiroFish, je veux que chaque assertion formulée dans le rapport soit formellement typée selon un contrat de donnée structuré (`ReportClaim`), que la nature épistémique des sources distingue sans ambiguïté les faits documentaires historiques, les hypothèses de scénario et les profils de personas fictifs, qu'une déclaration d'intention verbale ne soit jamais requalifiée abusivement en action sociale observée sans preuve dans le registre d'événements, et que l'ensemble des affirmations du rapport fassent l'objet d'une vérification déterministe serveur consignant leur statut (`VERIFIED`, `UNSUPPORTED`, `CONTRADICTED`) dans un registre auditable (`report_claims.json`).

Cette story répond directement aux exigences fonctionnelles **FR-03** (contrat structuré `ReportClaim`) et **FR-04** (typage épistémique et étanchéité des sources) de l'Epic 011. Elle concourt aux critères de sortie chiffrés **C4** (100 % des affirmations sous `[Événements simulés]` reliées à un `event_id` valide, 0 citation verbatim non retrouvée dans les traces, 0 intention qualifiée d'action réelle) et **C5** (étanchéité épistémique des sources, 0 fait issu d'un persona fictif classé en contexte historique), tout en garantissant la résilience ReACT (**NFR-04**) et l'étanchéité des prompts (**NFR-05**).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  1. Définir le modèle de données immuable `ReportClaim` et ses énumérations associées (`ClaimKind`, `VerificationStatus`) dans `backend/app/models/report_claim.py`.
  2. Établir le typage épistémique des sources documentaires (`EpistemicSourceKind`) dans `backend/app/models/source_document.py` pour distinguer formellement `CANONICAL_DOCUMENT`, `HISTORICAL_CASE`, `PERSONA_SPECIFICATION` et `SCENARIO_BRIEF`.
  3. Poser la barrière hermétique interdisant tout transfert d'attributs fictifs issus d'un persona (ex: perte financière de 1 500 € d'Émilie dans le cas Keova) vers la section `[Contexte documentaire historique]`.
  4. Mettre en œuvre la règle d'or anti-affabulation action vs intention dans `backend/app/services/simulation_action_verifier.py` : une déclaration textuelle (« Je vais acheter ») reste strictement une `REPORTED_INTENTION` et ne peut être typée `OBSERVED_SOCIAL_ACTION` sans trace correspondante (`is_action_executed = True`) dans l'`EvidencePack`.
  5. Implémenter le moteur d'extraction, de qualification et de validation déterministe des claims du rapport avec génération de l'artefact `report_claims.json`.
- [x] **Documents consultés** :
  - [PRD Epic 011](prd.md) : §1.B (défaillances épistémiques), §3 (FR-03, FR-04), §4 (NFR-04, NFR-05), §5 (C4, C5).
  - [Architecture Epic 011](architecture.md) : §2.4 (`ReportClaim` et contrat d'affirmation), §2.5 (typage épistémique des documents sources).
  - [Hub Epic 011](epic-011.md) : index des exigences, NFR et critères de sortie.
  - [Proposition amont Keova](rapport-chatgpt.md) : analyse des 5 simulations réelles, confusion de statut documentaire d'Émilie, extrapolation sans fait observé.
  - `backend/app/models/source_document.py` : `InformationOrigin`, `DocumentRole`, `DocumentValidationStatus`, `SourceConflict`.
  - `backend/app/models/evidence_pack.py` : `ObservedEvent`, `EvidencePack`.
  - `backend/app/services/simulation_action_verifier.py` : `SimulationActionVerifier`, `compute_event_id`, `verify_citation`, `IntentionAnalysisResult`.
  - `backend/app/services/report_agent.py` : `ReportAgent`, génération des sections et boucle ReACT.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (tests hermétiques et non-régression), §2.8 (gouvernance des plans).
- [x] **Dépendances résolues** :
  - Story 011-1 close (`done`) : persistance interactive OASIS post-rounds et clôture différée.
  - Story 011-2 close (`done`) : registre d'événements observés (`OasisLogReaderService`, `EvidencePack`), bouclier `ToolShield` et déterminisme Round 0.
  - Filet global : **1 679 tests collectés et réussis sur l'hôte** (+ 9 tests frontend Node), 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `ReportClaim`** : Créer `backend/app/models/report_claim.py` avec la dataclass `ReportClaim` contenant : `claim_id` (`clm_<sha256_8>`), `text`, `claim_kind` (`ClaimKind`), `origin` (`InformationOrigin`), `evidence_refs` (`list[str]`), `verification_status` (`VerificationStatus`), `agent_name`, `round_num`, `confidence`, `limitations`.
  2. **Typage épistémique `EpistemicSourceKind`** : Enrichir `source_document.py` d'une énumération `EpistemicSourceKind` (`CANONICAL_DOCUMENT`, `HISTORICAL_CASE`, `PERSONA_SPECIFICATION`, `SCENARIO_BRIEF`) et intégrer ce champ dans `SourceDocument` et `DocumentProvenance`.
  3. **Règle d'étanchéité stricte C5** : Aucun fait ou fragment associé à un document dont l'origine est `PERSONA_SPECIFICATION` ou `SCENARIO_BRIEF` ne peut être labellisé `InformationOrigin.DOCUMENTARY` ni présenté sous `[Contexte documentaire historique]`. Il est automatiquement assigné à `InformationOrigin.HYPOTHESIS` ou étiqueté `[Persona fictif]`.
  4. **Contrôle anti-affabulation C4** : `SimulationActionVerifier.verify_report_claim` vérifie qu'une affirmation de type `OBSERVED_SOCIAL_ACTION` pointe vers au moins un `event_id` valide présent dans l'`EvidencePack` et doté de `is_action_executed = True`. À défaut, l'assertion est déclassée en `REPORTED_INTENTION` avec statut `VerificationStatus.UNSUPPORTED` ou `CONTRADICTED`.
  5. **Contrôle verbatim des citations** : Toute citation textuelle attribuée à un agent simulé est vérifiée contre les textes réels enregistrés dans les traces JSONL et SQLite.
  6. **Agrégateur `ReportClaimRegistry`** : Conteneur regroupant l'ensemble des claims du rapport, calculant les statistiques d'audit (taux de vérification, claims orphelines, contradictions) et sérialisant `report_claims.json`.
- [x] **Stratégie de tests identifiée** :
  - Suite de tests unitaires et hermétiques dédiée : `backend/tests/test_report_claim_epistemic.py`.
  - Couverture des modèles `ReportClaim`, `ClaimKind`, `VerificationStatus` et `ReportClaimRegistry`.
  - Vérification de l'étanchéité épistémique des sources (rejet de l'étiquette historique sur les personas).
  - Validation des règles anti-affabulation (déclassement automatique des intentions déclarées sans événement effectif).
  - Validation du contrôle verbatim exact et partiel des citations simulées.
  - Maintien rigoureux du filet de tests ($\ge 1 679$ tests hôte au vert).

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Modèle `ReportClaim` et registre structuré** : Le modèle `ReportClaim` encapsule de manière immuable `claim_id` (déterministe `clm_<sha256_8>`), `text`, `claim_kind` (`SOURCE_FACT`, `SCENARIO_HYPOTHESIS`, `OBSERVED_SOCIAL_ACTION`, `REPORTED_INTENTION`, `ANALYST_INFERENCE`, `SPECULATIVE_PROJECTION`), `origin` (`InformationOrigin`), `evidence_refs`, `verification_status` (`VERIFIED`, `UNSUPPORTED`, `CONTRADICTED`), `agent_name`, `round_num`, `confidence` et `limitations`. Le conteneur `ReportClaimRegistry` regroupe l'ensemble des claims avec calcul automatique des statistiques et sérialisation `to_dict` / `to_json`. | Test unitaire hermétique validant l'instanciation, la validation des types, les transitions de statut et la sérialisation JSON. |
| **AC2** | **Typage épistémique des documents sources (`EpistemicSourceKind`)** : L'énumération `EpistemicSourceKind` (`CANONICAL_DOCUMENT`, `HISTORICAL_CASE`, `PERSONA_SPECIFICATION`, `SCENARIO_BRIEF`) est déclarée dans `source_document.py`. Chaque `SourceDocument` et chaque fragment porte son statut épistémique. Une fonction d'inférence déterministe dérive `EpistemicSourceKind` à partir du `DocumentRole` ou du nom de fichier en cas d'omission. | Test unitaire vérifiant l'affectation et la dérivation automatique du type épistémique sur divers documents et fragments sources. |
| **AC3** | **Étanchéité épistémique stricte (Critère C5)** : Tout fait ou citation provenant d'un document qualifié `PERSONA_SPECIFICATION` ou `SCENARIO_BRIEF` est formellement interdit d'être catégorisé en `InformationOrigin.DOCUMENTARY` ou `CANONICAL_DOCUMENT`. Le système force la qualification en `InformationOrigin.HYPOTHESIS` avec étiquette explicite `[Persona fictif]` ou `[Hypothèse de scénario]`. 0 fait fictif promu en contexte historique. | Test unitaire injectant un profil de persona fictif (ex: Émilie) et vérifiant le rejet strict de tout étiquetage sous le contexte historique documentaire. |
| **AC4** | **Règle anti-affabulation action vs intention (Critère C4)** : Le vérificateur serveur `SimulationActionVerifier.verify_report_claim` contrôle chaque assertion `OBSERVED_SOCIAL_ACTION`. Si l'assertion ne correspond à aucun `event_id` valide dans l'`EvidencePack` ou ne repose que sur un texte de message non accompagné d'une action exécutée (`is_action_executed = True`), elle est automatiquement rétrogradée en `ClaimKind.REPORTED_INTENTION` avec statut `UNSUPPORTED` et mention d'avertissement. | Test unitaire simulant une déclaration verbale sans action réelle et constatant le déclassement déterministe en `REPORTED_INTENTION` avec alerte. |
| **AC5** | **Vérification verbatim des citations simulées (Critère C4)** : Toute citation textuelle attribuée à un persona est confrontée aux actions effectives du run via `SimulationActionVerifier.verify_simulated_citation`. Si le texte cité n'est pas retrouvé textuellement (tolérance aux ponctuations et espaces normalisés), le statut de la claim passe à `UNSUPPORTED` avec indication d'absence de trace verbatim. | Test unitaire confrontant des citations authentiques et des citations forgées face au registre d'événements du run. |
| **AC6** | **Pipeline d'audit et persistance `report_claims.json`** : À l'issue de la génération de chaque section du rapport par `ReportAgent`, les claims sont extraites, vérifiées contre l'`EvidencePack` et indexées dans le `ReportClaimRegistry`. Le fichier `simulations/<sim_id>/report_claims.json` est persisté de manière atomique avec les métadonnées de vérification. | Test d'intégration unitaire validant l'extraction de claims à partir d'un fragment de rapport Markdown, la vérification automatique et la persistance sur disque. |
| **AC7** | **Non-régression et suite hermétique dédiée** : L'ensemble des 1 679 tests existants sur l'hôte reste au vert. Une suite dédiée d'au moins 15 tests hermétiques dans `backend/tests/test_report_claim_epistemic.py` valide exhaustivement les modèles, les règles épistémiques et l'anti-affabulation. | Exécution complète de la suite pytest sans régression. |

---

## Définition de fini

- [ ] Critères d'acceptation **AC1 à AC7** satisfaits et vérifiés par des tests automatisés passants.
- [ ] Modèle `ReportClaim`, énumérations `ClaimKind`, `VerificationStatus` et registre `ReportClaimRegistry` créés dans `backend/app/models/report_claim.py`.
- [ ] Énumération `EpistemicSourceKind` créée dans `backend/app/models/source_document.py` et intégrée aux modèles documentaires.
- [ ] Barrière d'étanchéité épistémique C5 implémentée, interdisant 100 % des classifications de personas fictifs en faits historiques.
- [ ] Règle anti-affabulation C4 opérationnelle dans `SimulationActionVerifier`, rétrogradant systématiquement les intentions non exécutées.
- [ ] Contrôle verbatim des citations simulées intégré et vérifié.
- [ ] Mécanisme d'extraction, qualification et persistance de `report_claims.json` intégré dans le cycle du `ReportAgent`.
- [ ] Suite de tests hermétiques créée dans `backend/tests/test_report_claim_epistemic.py`.
- [ ] Filet global de tests maintenu et accru ($\ge 1 695$ tests réussis sur l'hôte) et parité Docker validée.
- [ ] `uv run python backend/scripts/validate_plans.py` et `uv run ruff check backend/` validés sans anomalie.
- [ ] Revue contradictoire BMAD à 4 couches réalisée avec findings consignés et résolus.
- [ ] Synchronisation des documents de suivi (`epic-011.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`).

---

## Tâches

- [ ] **T1 — Modèle de données `ReportClaim`, `ClaimKind` et `ReportClaimRegistry`** :
  - Créer `backend/app/models/report_claim.py`.
  - Définir `ClaimKind` (`SOURCE_FACT`, `SCENARIO_HYPOTHESIS`, `OBSERVED_SOCIAL_ACTION`, `REPORTED_INTENTION`, `ANALYST_INFERENCE`, `SPECULATIVE_PROJECTION`).
  - Définir `VerificationStatus` (`VERIFIED`, `UNSUPPORTED`, `CONTRADICTED`).
  - Définir la dataclass `ReportClaim` avec calcul déterministe de `claim_id` (`clm_<sha256_8>`), champs typés et méthodes `to_dict` / `from_dict`.
  - Définir la classe `ReportClaimRegistry` pour l'agrégation, le calcul des ratios de couverture et la sérialisation `to_json` / `from_json`.
- [ ] **T2 — Typage épistémique des sources (`EpistemicSourceKind`)** :
  - Mettre à jour `backend/app/models/source_document.py`.
  - Déclarer l'énumération `EpistemicSourceKind` (`CANONICAL_DOCUMENT`, `HISTORICAL_CASE`, `PERSONA_SPECIFICATION`, `SCENARIO_BRIEF`).
  - Ajouter `epistemic_kind: EpistemicSourceKind` sur `SourceDocument` et `DocumentProvenance`.
  - Implémenter la méthode helper `derive_epistemic_kind(role, filename)` pour l'inférence automatique.
- [ ] **T3 — Barrière hermétique d'étanchéité épistémique (Critère C5)** :
  - Dans `source_document.py` (`classify_record_origin`) et `SimulationActionVerifier`, bloquer tout classement de source `PERSONA_SPECIFICATION` en `InformationOrigin.DOCUMENTARY`.
  - Forcer la qualification en `InformationOrigin.HYPOTHESIS` avec étiquetage explicite `[Persona fictif]`.
  - Valider l'étanchéité sur les personas du cas Keova (Émilie, Sylvie, Simon).
- [ ] **T4 — Règle anti-affabulation et contrôle intention vs action (Critère C4)** :
  - Étendre `SimulationActionVerifier` avec `verify_report_claim(claim, evidence_pack)`.
  - Vérifier la correspondance exacte entre `OBSERVED_SOCIAL_ACTION` et les `event_id` d'`EvidencePack` (`is_action_executed = True`).
  - Déclasser automatiquement les déclarations textuelles non accompagnées d'actions exécutées vers `ClaimKind.REPORTED_INTENTION` et `VerificationStatus.UNSUPPORTED`.
- [ ] **T5 — Contrôle verbatim des citations simulées** :
  - Implémenter dans `SimulationActionVerifier` la méthode `verify_simulated_citation(agent_name, claimed_text, evidence_pack)`.
  - Comparer textuellement les citations aux champs `action_args.content` ou `result` des événements observés avec normalisation d'espaces et de ponctuation.
  - Marquer `VerificationStatus.CONTRADICTED` ou `UNSUPPORTED` en cas d'affabulation de propos.
- [ ] **T6 — Extraction et persistance des claims dans `ReportAgent`** :
  - Intégrer l'analyse des claims dans `ReportAgent` (extraction des affirmations après génération de chaque section ou en passe finale).
  - Associer les références d'événements observés (`event_id`) aux affirmations événementielles.
  - Sauvegarder `simulations/<sim_id>/report_claims.json` dans le dossier de simulation.
- [ ] **T7 — Suite de tests hermétiques dédiée** :
  - Créer `backend/tests/test_report_claim_epistemic.py`.
  - Couvrir les cas d'usage : instanciation et sérialisation de `ReportClaim`, calcul des statistiques de `ReportClaimRegistry`, étanchéité des personas fictifs face au contexte documentaire historique, déclassement des intentions sans action, et vérification des citations réelles et forgées.
- [ ] **T8 — Validation globale, exécution des suites et revue BMAD** :
  - Exécuter la suite complète des tests backend (`uv run pytest tests/`).
  - Vérifier la parité sous conteneur Docker.
  - Conduire la revue contradictoire BMAD à 4 couches et consigner les résolutions.

---

## Notes de développement

### 1. Distinction épistémique des sources (Défaut B.2 du PRD)

Dans les versions antérieures, la catégorisation des sources reposait essentiellement sur le nom du fichier ou un booléen `is_documentary`. Dans le cas Keova :
- `personas-et-cibles-keova.md` décrivait le persona fictif « Émilie, 34 ans, graphiste freelance ayant perdu 1 500 € suite à un litige ».
- Le `ReportAgent` classait cet antécédent sous `[Contexte documentaire historique]`, créant l'illusion d'une perte financière réelle prouvée avant la simulation.

Avec la Story 011-3 :
```
SourceDocument: personas-et-cibles-keova.md
    └──> epistemic_kind: PERSONA_SPECIFICATION
              └──> classify_record_origin(...) ──> InformationOrigin.HYPOTHESIS
                        └──> Étiquette imposée : "[Persona fictif : Émilie]"
                                 └──> INTERDICTION formelle d'apparaître sous "[Contexte documentaire historique]"
```

### 2. Règle d'or : Intention verbale $\neq$ Action sociale observée (Défaut B.5 du PRD)

Dans la simulation sociale :
1. Un agent publie un tweet : « Le tarif de Keova est honnête, je vais m'abonner dès ce soir ».
2. Le LLM du rapport affirmait : « Émilie a souscrit à l'offre Keova ».
3. **Réalité des faits :** Aucun événement `action_type: "subscribe"` ou transaction n'existe dans `actions.jsonl` !

Avec le modèle `ReportClaim` et `SimulationActionVerifier` :
```python
claim = ReportClaim(
    text="Émilie a souscrit à l'offre Keova",
    claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
    evidence_refs=[],
)
# Le vérificateur serveur constate l'absence d'event_id d'exécution :
verified_claim = verifier.verify_report_claim(claim, evidence_pack)
# Résultat :
# verified_claim.claim_kind = ClaimKind.REPORTED_INTENTION
# verified_claim.verification_status = VerificationStatus.UNSUPPORTED
# verified_claim.limitations = ["Aucune action d'achat observée dans les traces du run. Déclaration d'intention uniquement."]
```

### 3. Schéma de données de `ReportClaim`

```
simulations/<sim_id>/report_claims.json
{
  "simulation_id": "sim_20261016_keova",
  "total_claims": 24,
  "verified_claims": 20,
  "unsupported_claims": 3,
  "contradicted_claims": 1,
  "claims": [
    {
      "claim_id": "clm_8f2a1b9c",
      "text": "Émilie a exprimé son indignation face à l'absence d'option mensuelle au Round 2",
      "claim_kind": "OBSERVED_SOCIAL_ACTION",
      "origin": "simulation",
      "evidence_refs": ["evt_twitter_2_3_a9b1c3d4"],
      "verification_status": "VERIFIED",
      "persona_name": "Émilie",
      "round_num": 2,
      "confidence": 1.0,
      "limitations": []
    }
  ]
}
```

---

## Revue

### Review Findings (Revue contradictoire BMAD à 4 couches)

*(À renseigner lors de la revue BMAD de la story)*

#### Rejected findings
*(À renseigner lors de la revue BMAD de la story)*

---

## Notes de complétion

*(À renseigner lors de la clôture de la story)*
