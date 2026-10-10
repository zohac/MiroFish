# Epic 009 — Éligibilité des acteurs et fiabilisation des sources

- **Statut** : `backlog` · **Dépend de** : 004, 005 · **Bloque** : 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **PRD** : [`prd.md`](prd.md) · **Architecture** : [`architecture.md`](architecture.md)

> L'Epic 005 a scellé l'environnement Docker de référence autonome (711 tests verts, Verdict GO).  
> **L'Epic 009 élimine la confusion sémantique entre connaissances et acteurs simulables**.  
> Il introduit une sélection rigoureuse d'éligibilité des agents (`ActorEligibility`), une modélisation typée des documents sources (`SourceDocument`), la persistance du `SimulationBrief`, une étape de prévalidation avant simulation, et la traçabilité des faits dans le rapport final.

---

## 1. Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Éligibilité des acteurs (`ActorEligibility`) | Qualification de chaque entité du graphe via un rôle (`person`, `organization`, `product`, `concept`, etc.) et un statut (`eligible`, `ineligible`, `review`). |
| **FR-2** | Filtrage hermétique dans la génération OASIS | Seules les entités avec `status=eligible` génèrent des comptes d'intervention dans `OasisProfileGenerator` ; les autres restent conservées comme contexte passif dans Neo4j. |
| **FR-3** | Documents sources structurés (`SourceDocument`) | Fichiers associés à un rôle explicite (`facts`, `scenario`, `personas`, `hypotheses`, `constraints`, `reference`) et date de validité. |
| **FR-4** | Persistance du `SimulationBrief` | Consignes, règles et état initial conservés dans l'objet `Project` et réinjectés dans la génération de configuration. |
| **FR-5** | Provenance des fragments et relations | Nœuds `:Episodic` Neo4j annotés avec `source_document_id`, `filename` et `chunk_index`, reliés aux faits via `r.episodes`. |
| **FR-6** | Prévisualisation des acteurs (`preview`/`review`) | Routes d'inspection permettant de consulter les acteurs retenus et d'ajuster leur éligibilité avant le démarrage de la simulation. |
| **FR-7** | Provenance dans le rapport final | Le `ReportAgent` étiquette clairement les faits prouvés par les documents par opposition aux événements issus de la simulation. |

---

## 2. Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Zéro règle métier spécifique (Agnosticisme strict) | Aucune heuristique liée à un client particulier dans le code (bannissement contrôlé par AST, AGENTS.md §2.1). |
| **NFR-2** | Rétrocompatibilité `GraphStore` | Aucun impact cassant sur l'abstraction `GraphStore` ni sur l'implémentation `ZepGraphStore`. |
| **NFR-3** | Résilience et repli propre | En cas d'erreur du classifieur LLM, repli sécurisé sur le filtrage syntaxique avec marquage `review`. |
| **NFR-4** | Filet de tests hermétiques et Docker | Tests automatisés sans réseau externe obligatoire, parité totale validée dans le conteneur Docker. |

---

## 3. UX requirements

- L'utilisateur peut spécifier le rôle de chaque fichier lors de l'import (faits, scénario, personas, etc.) ou laisser le système appliquer le mode simple par défaut.
- Un écran de révision présente la liste ordonnée des acteurs détectés : ceux qui participeront à la simulation (personnes, organisations autorisées) et ceux qui restent passifs en arrière-plan (produits, prix, concepts).
- L'utilisateur peut d'un clic requalifier un acteur (`eligible` / `ineligible`) avant de lancer la simulation.
- Le rapport final cite ses sources textuelles et n'affirme pas comme fait avéré une action qui relève uniquement d'un post d'agent simulé.

---

## 4. Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 009-1 | Modèle `ActorEligibility` et classifieur agnostique à deux passes (Lot A - P0) | `backlog` | `story-009-1.md` |
| 009-2 | Documents sources typés (`SourceDocument`), persistance `SimulationBrief` et traçabilité `GraphStore` (Lot B - P1) | `backlog` | `story-009-2.md` |
| 009-3 | Endpoints et interface de prévalidation des acteurs (`preview` & `review`) (Lot C - P1) | `backlog` | `story-009-3.md` |
| 009-4 | Provenance des affirmations et distinction des faits dans le `ReportAgent` (Lot D - P1) | `backlog` | `story-009-4.md` |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 009-1 | Given un graphe Neo4j avec entités mixtes (:Entity), when `ActorClassifierService` qualifie les entités, then 100 % des produits, URLs, tarifs et concepts sont classés `ineligible` ; `OasisProfileGenerator` ne crée des comptes que pour les entités `eligible` ; 0 produit ou offre commerciale ne devient persona actif ; validation sur 2 domaines distincts sans règle en dur. |
| 009-2 | Given l'upload de multiples documents, when l'API les ingère, then chaque fichier devient un `SourceDocument` typé avec rôle et métadonnées ; le `SimulationBrief` est persisté dans `project.json` ; les épisodes dans Neo4j conservent `source_document_id`, `filename` et `chunk_index` ; chaque relation `[r]` remonte à son document d'origine via `r.episodes`. |
| 009-3 | Given un projet prêt pour la simulation, when l'utilisateur appelle `GET /api/simulation/actors/preview`, then la liste détaillée des entités avec rôle, éligibilité et justification est retournée ; l'appel `POST /api/simulation/actors/review` permet d'ajuster manuellement le statut d'un acteur et persiste l'arbitrage dans `actors.json`. |
| 009-4 | Given la génération de rapport par `ReportAgent`, when le rapport final est rédigé, then les affirmations basées sur les documents sources mentionnent explicitement le document d'origine ; les conclusions issues des tours OASIS sont étiquetées comme simulations fictives ; les contradictions sont signalées et non dissimulées. |

---

## 5. Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`docs/plans/009-eligibilite-acteurs-et-sources/prd.md`](prd.md) | Contrat d'ingénierie, critères chiffrés C1 à C5. |
| [`docs/plans/009-eligibilite-acteurs-et-sources/architecture.md`](architecture.md) | Schémas Mermaid, modèles de données et flux de classification. |
| [`backend/app/services/oasis_profile_generator.py`](../../backend/app/services/oasis_profile_generator.py) | Point d'injection du filtrage d'éligibilité. |
| [`backend/app/services/simulation_manager.py`](../../backend/app/services/simulation_manager.py) | Chaîne de préparation de simulation et persistance d'état. |
| [`backend/app/utils/graph_store/graphiti_store.py`](../../backend/app/utils/graph_store/graphiti_store.py) | Ingestion des épisodes et traçabilité `r.episodes`. |
| [`backend/app/services/report_agent.py`](../../backend/app/services/report_agent.py) | Outils et prompt système de synthèse d'analyse. |
| [`AGENTS.md`](../../AGENTS.md) | Constitution du dépôt (§2.1 Clean architecture agnostique, §2.8 artefacts). |
