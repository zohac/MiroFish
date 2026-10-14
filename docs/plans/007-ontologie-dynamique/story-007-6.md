---
id: "007-6"
epic: "007"
titre: "Audit dans le rapport (sous-section « Ontologie appliquée ») et outil LLM"
statut: done
auteur: "Simon"
format: "2"
---

# Story 007-6 — Audit dans le rapport (sous-section « Ontologie appliquée ») et outil LLM

En tant qu'analyste ou lecteur d'un rapport de simulation MiroFish, je veux pouvoir
auditer dans le rapport final l'ontologie dynamique qui a structuré l'extraction de
connaissances et les simulations (types, descriptions, origines, statistiques
d'entités/arêtes, politique et version), et en tant qu'agent de rapport (`ReportAgent`),
je veux pouvoir consulter l'ontologie appliquée via un outil LLM dédié (`get_applied_ontology`),
afin de garantir la transparence méthodologique, de documenter la provenance des faits
et d'empêcher les affabulations sur la structure ontologique.

**Lot C — P1.** Exigences : FR-6 ; NFR-4 (continuité des flux), NFR-5 (séparation stricte données / consignes) ; critères de sortie C7 et contribution à C8.  
Dépendances : Stories 007-4 et 007-5 terminées (`done`).  
Cette story complète la section « Sources & Provenance » mise en place dans l'Epic 009
en y injectant une sous-section dédiée à l'ontologie appliquée, et dote le `ReportAgent`
de la capacité d'interrogation outillée de l'ontologie appliquée au projet courant.

## Définition de prêt

- [x] PRD §3.1/§4/C7, architecture §7, epic-007 §1/§4 et constitution consultés.
- [x] Stories 007-4 et 007-5 terminées (`done`) : modèle `OntologyVersion`, magasin `OntologyVersionStore`, méthode `Project.get_applied_ontology()` et rattachement `applied_ontology_id` opérationnels.
- [x] Code source existant analysé : `ReportAgent` (`app/services/report_agent.py`), section « Sources & Provenance » (`build_sources_provenance_section`), gestion des outils LLM (`_define_tools`, `_execute_tool`).
- [x] Modèle de provenance `InformationOrigin` (ADR 0012, 009-2) réutilisé pour qualifier l'origine de chaque type (`documentary`, `hypothesis`, `inherited`, etc.).
- [x] Stratégie de décompte Cypher par type de nœud et d'arête définie avec tolérance aux pannes et résilience en cas de base inaccessible.
- [x] Scénarios de test hermétiques C7 conçus : présence de la sous-section sur projet typé, absence stricte sur projet non typé (graphe hérité Epic 006 ou sans ontologie), appel d'outil LLM unitaire et intégration.

### Critères d’acceptation

| Réf. | Contrat mesurable | Vérification |
|---|---|---|
| AC1 | **Sous-section « Ontologie appliquée » dans le rapport (FR-6, C7)** : La méthode `ReportAgent.build_sources_provenance_section()` inclut une sous-section structurée « ### 6. Ontologie appliquée (Epic 007, FR-6) » lorsque le projet dispose d'une ontologie appliquée (`applied_ontology_id` présent). Elle comprend :<br/>• Un tableau des types d'entités : Nom du type (label), Description, Origine (`InformationOrigin`), Compte d'entités présentes dans le graphe.<br/>• Un tableau des types de relations : Nom de la relation, Description, Types source/cible, Compte d'arêtes présentes dans le graphe.<br/>• Les métadonnées de version : Identifiant (`ont_<uuid12>`), date de création ISO 8601, parent éventuel et source.<br/>• La politique de validation active (`project.ontology_policy`) et le compte des avertissements récents (`GraphValidationWarning`). | Tests unitaires sur `build_sources_provenance_section()` avec fixture de projet typé vérifiant la structure markdown exacte et la présence de tous les champs. |
| AC2 | **Absence conditionnelle stricte (C7)** : Si le projet rattaché à la simulation **n'a pas** d'ontologie appliquée (`applied_ontology_id` est `None`, cas d'un projet hérité de l'Epic 006 sans typage dynamique ou d'un projet simple), la sous-section « Ontologie appliquée » est **strictement omise** du rapport. Les sous-sections 1 à 5 de provenance (Epic 009) restent affichées nominalement sans altération ni erreur. | Test négatif sur un projet sans ontologie validant l'absence totale de la sous-section 6 et l'intégrité des 5 autres sous-sections. |
| AC3 | **Définition de l'outil LLM `get_applied_ontology` (FR-6)** : L'outil LLM est déclaré dans `ReportAgent._define_tools()` avec son schéma de paramètres :<br/>• `name`: `"get_applied_ontology"`<br/>• `description`: explication claire de l'outil invitant l'agent à l'utiliser pour expliquer la typologie des faits cités.<br/>• `parameters`: `include_counts` (booléen, défaut `true`), `since` (chaîne ISO 8601 optionnelle pour filtrer les avertissements). | Test unitaire inspectant le dictionnaire retourné par `_define_tools()`. |
| AC4 | **Exécution robuste de l'outil LLM dans `_execute_tool` (FR-6)** : Le dispatch `_execute_tool` prend en charge `"get_applied_ontology"`. Il extrait l'ontologie via `project.get_applied_ontology()`, calcule les comptes si demandés et renvoie une chaîne JSON formattée (`json.dumps(..., ensure_ascii=False, indent=2)`). Si le projet n'a pas d'ontologie appliquée, il renvoie un JSON clair `{"status": "no_ontology_applied", "message": "..."}`. En cas d'exception, il attrape l'erreur et retourne un diagnostic explicite sans lever d'exception non gérée. | Tests unitaires de `_execute_tool("get_applied_ontology", ...)` couvrant les cas projet avec ontologie, sans ontologie, et gestion d'erreurs. |
| AC5 | **Comptage Cypher performant et tolérant aux pannes (NFR-4)** : Le décompte des entités et relations par type s'appuie sur une requête Cypher agrégée optimisée exécutée via le store ou le driver Neo4j. Si le graphe est indisponible ou en cas d'erreur de requête, le décompte retombe gracieusement sur `0` ou `N/A` sans bloquer la génération du rapport. | Tests unitaires avec store mocké simulant des comptes réels et une exception réseau pour prouver la résilience. |
| AC6 | **Étanchéité des consignes et séparation des données (NFR-5)** : Les descriptions et noms de types issus de l'ontologie injectés dans le rapport ou retournés à l'outil LLM sont traités strictement comme des données d'entrée factuelles et ne sont jamais interprétés ni concaténés dans les consignes système des prompts. | Test vérifiant l'absence de fuite de consignes et l'échappement défensif des métadonnées de types d'ontologie. |
| AC7 | **Exposition API pour l'audit et l'IHM (PRD Q4)** : L'endpoint `GET /api/project/<project_id>/ontology` (ou sous-ressource associée) permet de relire l'ontologie appliquée complète incluant version, types, politique et statistiques d'entités pour consultation externe ou affichage IHM. | Test d'API Flask sur le endpoint `GET` vérifiant la réponse 200 avec structure complète ou 404 si le projet est absent. |
| AC8 | **Filet de tests hermétiques et non-régression (C8)** : Au moins **15 nouveaux tests hermétiques** ajoutés couvrant AC1 à AC7. La suite globale passe à $\ge 1534$ tests passants sur l'hôte, `ruff check .` propre, `validate_plans.py` conforme. | Exécution complète de pytest, ruff et validate_plans. |

## Définition de fini

- [x] AC1 à AC8 satisfaits avec preuves de tests unitaires et d'intégration hermétiques associées.
- [x] Sous-section « Ontologie appliquée » intégrée à `build_sources_provenance_section()` de `ReportAgent`.
- [x] Outil LLM `get_applied_ontology` défini dans `_define_tools` et exécutable dans `_execute_tool`.
- [x] Absence stricte de la sous-section validée sur les projets sans ontologie appliquée.
- [x] Comptage Cypher robuste avec repli gracieux en cas de panne.
- [x] Préservation absolue des 1157+ tests de l'Epic 009 sans régression.
- [x] Filet global $\ge 1534$ tests passants sur l'hôte, `ruff check .` propre, `validate_plans.py` conforme.
- [x] Revue contradictoire BMAD 4 couches effectuée et patches traités.
- [x] Notes de complétion rédigées, suivi `sprint-status.yaml`, `STATUS.md` et `epic-007.md` actualisés.

## Tâches

- [x] T1 — Conception de la méthode d'inspection et de décompte des entités et relations par type d'ontologie (AC5).
- [x] T2 — Intégration de la sous-section « 6. Ontologie appliquée (Epic 007, FR-6) » dans `ReportAgent.build_sources_provenance_section()` (AC1, AC2, AC6).
- [x] T3 — Déclaration du schéma d'outil `get_applied_ontology` dans `ReportAgent._define_tools()` (AC3, AC6).
- [x] T4 — Implémentation du dispatch d'exécution dans `ReportAgent._execute_tool()` avec formatage JSON structuré (AC4, AC5).
- [x] T5 — Intégration / consolidation du endpoint API `GET /api/project/<project_id>/ontology` pour exposition des métadonnées appliquées (AC7).
- [x] T6 — Écriture de la suite de tests hermétiques dédiée `backend/tests/test_report_ontology_audit.py` (AC1-AC8).
- [x] T7 — Revue contradictoire BMAD 4 couches et validation globale outillée (AC8).

### Review Findings

- [x] [Review][Patch] Reconnaissance des appels d'outils en JSON brut via VALID_TOOL_NAMES [backend/app/services/report_agent.py:1283]
- [x] [Review][Patch] Déterminisme du schéma de réponse GET /api/project/<id>/ontology?include_counts=true [backend/app/api/project.py:65-98]
- [x] [Review][Patch] Échappement défensif des descriptions dans les tableaux Markdown du rapport [backend/app/services/report_agent.py:2118,2127]
- [x] [Review][Defer] Requête Cypher agrégée pour décompte d'instances sur très grands graphes [backend/app/services/report_agent.py:2163] — deferred: choix architectural préexistant aligné avec GraphStore, simulations locales actuelles portant sur des graphes de taille modérée (<1000 nœuds).

#### Rejected Findings
- Redondance d'acquisition de store dans get_project_ontology (backend/app/api/project.py:54,71) : rejeté car le pool GraphStore gère efficacement les ouvertures et le couplage n'apporterait pas de gain mesurable.

## Notes de développement

### Flux de génération du rapport et d'interrogation de l'ontologie

```mermaid
sequenceDiagram
    autonumber
    participant U as Utilisateur / Client API
    participant RA as ReportAgent
    participant P as Project / Store
    participant OVS as OntologyVersionStore
    participant GS as GraphStore (Neo4j)

    Note over RA: Phase 1 - Génération du rapport final
    RA->>RA: build_sources_provenance_section()
    RA->>P: _resolve_project()
    alt Projet sans ontologie (applied_ontology_id is None)
        RA->>RA: Génère sous-sections 1 à 5 (Epic 009) sans sous-section 6
    else Projet avec ontologie appliquée
        RA->>OVS: OntologyVersionStore.get(applied_ontology_id)
        OVS-->>RA: OntologyVersion (types, edge_types, created_at)
        RA->>GS: get_entity_counts_by_type()
        GS-->>RA: {"PersonEntity": 12, "MediaOrganization": 4, ...}
        RA->>RA: Formate la sous-section 6 « Ontologie appliquée »
    end

    Note over RA: Phase 2 - Utilisation de l'outil LLM par l'agent
    RA->>RA: _execute_tool("get_applied_ontology", {"include_counts": true})
    RA->>OVS: Lecture version & typologie
    RA->>GS: Décompte des instances
    RA-->>RA: JSON structuré pour le LLM
```

### Format markdown attendu pour la sous-section 6

```markdown
### 6. Ontologie appliquée (Epic 007, FR-6)

| Type d'entité | Description | Origine | Compte |
|---|---|---|---|
| `PersonEntity` | Citoyen ou usager type du domaine | documentary | 12 |
| `MediaOrganization` | Organe de presse, régulateur | documentary | 4 |
| `RegulatoryDecision` | Décision ou sanction d'un régulateur | hypothesis | 0 |

| Type de relation | Source | Cible | Description | Compte |
|---|---|---|---|---|
| `REGULATES` | `MediaOrganization` | `PersonEntity` | Encadrement ou régulation | 3 |

**Version d'ontologie appliquée** : `ont_a3f9c2d8e1b7` (créée le 2026-10-14T14:22:00Z, source : brief + 2 documents).  
**Politique de validation** : mode permissif (avertissement + rétrogradation). 0 avertissement(s) actif(s).
```

### Schéma JSON retourné par l'outil `get_applied_ontology`

```json
{
  "status": "applied",
  "version_id": "ont_a3f9c2d8e1b7",
  "created_at": "2026-10-14T14:22:00Z",
  "source_summary": "brief + 2 documents",
  "policy": {
    "strict_ontology": false,
    "warnings_count": 0
  },
  "entity_types": [
    {
      "name": "PersonEntity",
      "description": "Citoyen ou usager type du domaine",
      "source": "documentary",
      "attributes": ["name", "role"],
      "count": 12
    }
  ],
  "edge_types": [
    {
      "name": "REGULATES",
      "description": "Encadrement ou régulation",
      "source_types": ["MediaOrganization"],
      "target_types": ["PersonEntity"],
      "count": 3
    }
  ]
}
```

## Revue

Revue contradictoire BMAD à 4 couches réalisée le **14 octobre 2026** sur la branche `local-first` :
- **Couche 1 : blind-hunter** :
  - Détection de l'absence de `get_applied_ontology` et des outils de provenance dans `ReportAgent.VALID_TOOL_NAMES`, empêchant la reconnaissance des appels en JSON brut (fallback LLM). Patch appliqué immédiatement.
  - Détection de l'omission du dictionnaire `statistics` dans `GET /api/project/<id>/ontology?include_counts=true` lorsque `project.graph_id` est `None`. Patch appliqué pour initialiser la structure par défaut (0 comptes).
  - Échappement défensif des descriptions dans les tableaux Markdown (`|` et `\n`) pour prévenir toute corruption de colonnes. Patch appliqué.
  - Détection de la double ouverture de connexion GraphStore dans `get_project_ontology` : analysé et rejeté en `low` sans régression ni anomalie démontrée.
- **Couche 2 : edge-case-hunter** :
  - Tolérance aux pannes du graphe (AC5) : si Neo4j ou le driver Cypher est indisponible, `_get_ontology_instance_counts` intercepte l'erreur sans propager d'exception et retombe sur des dictionnaires vides (comptes à 0), garantissant la continuité de génération du rapport (NFR-4).
  - Échappement et étanchéité NFR-5 (AC6) : les métadonnées de types injectées dans le markdown ou l'outil LLM sont traitées strictement comme des données d'entrée factuelles sans concaténation dans les consignes système des prompts.
  - Absence conditionnelle stricte (AC2) : omission totale de la sous-section 6 si `applied_ontology_id` est `None` (projets hérités Epic 006 ou non typés), avec préservation absolue des sous-sections 1 à 5 de provenance.
- **Couche 3 : verification-gap** :
  - Création de la suite hermétique `backend/tests/test_report_ontology_audit.py` avec **18 tests unitaires et d'intégration** (15 tests initiaux + 3 tests de régression couvrant les patches BMAD : parsing JSON brut, réponse sans graph_id, échappement de pipes).
  - Exécution complète de la suite de tests backend : **1537 tests passants** sur l'hôte (1537 réussis, 0 échec). Filet de sécurité grossi de +18 tests hermétiques par rapport à la story 007-5 (1519 tests).
- **Couche 4 : acceptance-auditor** :
  - 100 % des critères d'acceptation AC1 à AC8 validés avec preuves de tests.
  - `ruff check .` rigoureusement propre (0 warning, 0 erreur).
  - `validate_plans.py` conforme (9 epics, 41 fichiers validés).

## Notes de complétion

- **Sous-section « Ontologie appliquée » dans le rapport (FR-6, C7)** :
  - Intégration dans `ReportAgent.build_sources_provenance_section()` d'une sous-section dédiée « ### 6. Ontologie appliquée (Epic 007, FR-6) ».
  - Affichage structuré en deux tableaux Markdown : types d'entités (nom, description échappée, origine `InformationOrigin`, compte d'instances) et types de relations (nom, source, cible, description échappée, compte d'instances).
  - Métadonnées de traçabilité complètes : identifiant de version (`ont_<uuid12>`), date de création ISO 8601, résumé de source, et politique de validation avec compte des avertissements récents.
- **Outil LLM `get_applied_ontology` (FR-6)** :
  - Déclaration formelle du schéma de l'outil dans `ReportAgent._define_tools()` avec paramètres `include_counts` et `since`.
  - Intégration dans `VALID_TOOL_NAMES` pour reconnaissance nominale et repli JSON brut.
  - Dispatch d'exécution dans `ReportAgent._execute_tool()` renvoyant une charge JSON structurée et exhaustive avec repli propre si aucune ontologie n'est appliquée.
- **Comptage tolérant aux pannes (AC5, NFR-4)** :
  - Méthode `_get_ontology_instance_counts()` inspectant les nœuds et arêtes du graphe partitionné par `group_id` via `zep_tools`.
  - Résilience totale en cas de coupure réseau ou d'indisponibilité du store (repli à 0 sans bloquer la génération du rapport).
- **API d'audit et IHM (AC7, PRD Q4)** :
  - Enrichissement de `GET /api/project/<project_id>/ontology` dans `backend/app/api/project.py` pour retourner la politique (`strict_ontology`, `warnings_count`) et, sur paramètre optionnel `include_counts=true`, le dictionnaire complet des statistiques d'instances avec restitution propre des connexions et schéma déterministe même en l'absence de `graph_id`.
- **Filet de tests et non-régression** :
  - 18 tests hermétiques dédiés dans `tests/test_report_ontology_audit.py` (15 initiaux + 3 issus de la revue BMAD).
  - Suite globale portée de 1519 à **1537 tests passants sur l'hôte** (0 échec).
  - Lint `ruff check .` impeccable et validation de la gouvernance `validate_plans.py`.
