---
id: "009-3"
epic: "009"
titre: "Endpoints et interface de prévalidation des acteurs (`preview` & `review`)"
statut: backlog
auteur: agent
format: "2"
---

# Story 009-3 — Endpoints et interface de prévalidation des acteurs (`preview` & `review`)

Lot C, priorité P1. En tant qu'utilisateur, je veux prévisualiser la liste des
acteurs extraits du graphe avant la génération des personas OASIS, requalifier de
façon motivée les entités en cas de besoin, visualiser les diagnostics de
contexte et les conflits connus, et pouvoir bloquer volontairement la simulation
en présence de doute ou de contradiction documentaire non résolue, afin de
garantir qu'aucun faux acteur ne participe à la simulation sans arbitrage tracé.

La story dépend de 009-1 (`done`, barrière d'éligibilité et classifieur agnostique)
et de 009-2 (`done`, documents typés, brief versionné, diagnostics de contexte et
modèle des conflits). Elle couvre FR-6 ; NFR-3, NFR-4 et NFR-5 ; critère C6 et
contribution à C5.

---

## Définition de prêt

- [ ] Objectif compris : exposer deux routes API dédiées (`POST /api/simulation/actors/preview` et `POST /api/simulation/actors/review`), persister une sélection d'acteurs versionnée (`actors.json`) rattachée à la simulation, proposer un écran de révision dans l'interface (`Step2EnvSetup.vue`), supporter le parcours simple sans friction, et permettre le blocage volontaire sur entités `review` ou conflits ouverts.
- [ ] Documents consultés : [PRD](prd.md) §4 FR-6, §5 C6/C5, §6 ; [architecture](architecture.md) §5 (séquence Mermaid), §6, §7 (sélection persistée et corrections humaines), §9 (diagnostics et conflits) ; [revue de cohérence](revue-coherence-2026-10-10.md) R01, R10, R13, R14, R19 et arbitrage 1 ; [matrice de couverture](couverture-rapport-audit.md) A04, A06, A07, A10 ; [hub](epic-009.md) ; [story 009-1](story-009-1.md) et [story 009-2](story-009-2.md) ; [AGENTS.md](../../../AGENTS.md) §2.1/2.2/2.5/2.8/2.9/2.10.
- [ ] Dépendances résolues : 009-1 (`done`), 009-2 (`done`), 004 et 005 (`done`) ; filet de référence de 1112 tests réussis sur l'hôte (1109 + 3 ignorés sous Docker au 11 octobre 2026).
- [ ] Règles d'arbitrage figées :
  - Requalification autorisée uniquement vers des rôles d'acteurs admissibles (`person`, `organization`).
  - Interdiction absolue et rejet 400 de la combinaison `product + eligible`, `concept + eligible`, `tariff + eligible` ou `url + eligible`.
  - Justification textuelle obligatoire et non vide pour toute correction humaine.
  - Concurrence optimiste par contrôle strict de `expected_revision` (rejet 409 si désynchronisé).
  - Verrouillage d'état : aucune mutation autorisée si la simulation est en cours de préparation (`preparing`) ou d'exécution (`running`/`completed`).
- [ ] Stratégie de tests identifiée : tests unitaires du modèle `ActorSelection`, tests d'intégration des routes Flask, tests de non-régression du parcours simple de `prepare_simulation`, tests de blocage volontaire et tests de l'IHM Vue 3.

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| AC1 | **Modèle et stockage persistant `ActorSelection` (`actors.json`)** : rattaché à chaque simulation dans `uploads/simulations/{simulation_id}/actors.json`. Porte `schema_version`, `policy_version`, `simulation_id`, `project_id`, `graph_id`, `revision` (entier incrémental débutant à 1), `input_fingerprint` (empreinte SHA-256 déterministe basée sur les entités, le requirement, le brief et la politique), `counts` (`total`, `eligible`, `review`, `ineligible`), la liste des qualifications d'acteurs et l'historique des modifications humaines. Écriture atomique via fichier temporaire et remplacement. | Tests unitaires de sérialisation / désérialisation, calcul d'empreinte déterministe et écriture atomique sur disque. |
| AC2 | **Route `POST /api/simulation/actors/preview`** : reçoit `{ "simulation_id": str, "force_refresh": Optional[bool] }`. Résout côté serveur `project_id`, `graph_id`, charge les entités via `ZepEntityReader` et le brief du projet. Si `actors.json` existe et que son empreinte est identique (sans `force_refresh`), il est renvoyé directement sans recalcul LLM, préservant ainsi les arbitrages humains existants. Sinon, exécute la classification `ActorClassifierService`, écrit `actors.json` révision 1 et renvoie la charge utile enrichie des diagnostics de contexte et des conflits documentaires ouverts. | Tests d'appel unitaire de route Flask, réutilisation de cache sur empreinte identique, recalcul sur force_refresh et exposition des diagnostics. |
| AC3 | **Route `POST /api/simulation/actors/review` (corrections motivées)** : reçoit `{ "simulation_id": str, "expected_revision": int, "modifications": List[Dict] }`. Contrôle de concurrence optimiste (retourne HTTP 409 si `expected_revision` est obsolète). Vérifie le statut de simulation (retourne HTTP 400 si la simulation est en préparation ou exécution). Vérifie que chaque `entity_uuid` existe dans la simulation. Valide strictement les rôles cibles : `person` et `organization` sont éligibles ; `product`, `concept`, `tariff` ou tout non-acteur avec statut éligible est strictement rejeté avec HTTP 400. Exige une justification textuelle non vide pour chaque modification. Incrémente la révision et consigne l'historique. | Tests de validation de schéma, tests des rejets (409 sur révision dépassée, 400 sur produit éligible, 400 sur justification vide, 400 sur simulation en cours). |
| AC4 | **Parcours simple préservé et intégration `prepare_simulation`** : un appel direct à `POST /api/simulation/prepare` sans prévisualisation préalable exécute automatiquement la classification, écrit `actors.json` (révision 1) et poursuit la génération sans imposer d'interaction humaine. Si `actors.json` existe et est à jour, `prepare_simulation` consomme cette sélection (avec les arbitrages humains appliqués) pour filtrer les entités avant passage à `OasisProfileGenerator`. Les rôles qualifiés (`person`, `organization`) sont transmis aux prompts des personas au lieu du label générique `Entity`. | Tests de la route `/prepare` avec et sans passage préalable par `/actors/review` ; vérification des profils OASIS générés à partir des rôles qualifiés. |
| AC5 | **Invalidation sur modification du graphe ou du brief** : si le graphe ou le brief est modifié après une révision d'acteurs, l'empreinte `input_fingerprint` diverge ; `prepare_simulation` détecte l'obsolescence et exige un recalcul au lieu d'utiliser une sélection périmée. `force_regenerate` ne permet pas de contourner la barrière d'éligibilité. | Tests de mutation du brief/graphe injectée entre la révision et la préparation ; vérification du refus ou de la re-classification obligatoire. |
| AC6 | **Blocage volontaire préventif (`block_on_review` & `block_on_conflict`)** : `prepare_simulation` accepte les paramètres optionnels `block_on_review: bool` et `block_on_conflict: bool`. Si `block_on_review=True` et qu'au moins une entité reste en statut `REVIEW`, la préparation s'interrompt avec erreur explicite listant les entités non tranchées. Si `block_on_conflict=True` et qu'au moins un `SourceConflict` ouvert (`OPEN`) existe sur le projet, la préparation s'interrompt avec erreur explicite listant les conflits non résolus. | Tests d'interruption volontaire avec diagnostics complets dans les retours d'API et journaux. |
| AC7 | **Interface IHM de révision (`Step2EnvSetup.vue`)** : intégration dans l'étape de configuration d'un panneau de prévalidation des acteurs. Affichage de la liste triée avec badges visuels d'éligibilité (`Éligible` vert, `À vérifier` orange, `Inéligible` gris), type initial et rôle. Formulaire de modification d'une entité avec sélection du rôle et saisie obligatoire de justification. Affichage des avertissements (entités `review`, conflits de sources détectés) et cases à cocher pour le blocage volontaire. Bouton d'action directe "Lancer la préparation" disponible à tout moment pour le parcours simple. | Tests de composants Vue / vérification du rendu, interactions utilisateur et soumission des formulaires. |
| AC8 | **Suite de tests hermétiques et parité Docker** : couverture de bout en bout sans réseau externe ni `.env`. Le filet global passe à 100 % vert sous Docker et sur l'hôte, au-delà de la référence de 1112 tests. | `uv run pytest tests/ -q` vert ; 0 régression. |
| AC9 | **Conformité constitutionnelle et outillage** : `ruff check .` propre, `validate_plans.py` valide, documentation et suivi à jour (`epic-009.md`, `sprint-status.yaml`, `STATUS.md`). | Validation des outils CI. |

---

## Définition de fini

- [ ] AC1 à AC9 satisfaits avec preuves et tests hermétiques.
- [ ] Modèle `ActorSelection` et sérialisation atomique dans `actors.json` implémentés et testés.
- [ ] Routes `POST /api/simulation/actors/preview` et `POST /api/simulation/actors/review` implémentées, sécurisées et couvertes par des tests exhaustifs.
- [ ] Concurrence optimiste (409), verrouillage sur simulation active (400), rejet des UUIDs étrangers et interdiction absolue de requalifier un produit/concept en acteur éligible (400) formellement prouvés par des tests négatifs.
- [ ] `SimulationManager.prepare_simulation` adapté : parcours simple fluide, consommation de la sélection révisée, transmission des rôles qualifiés aux personas et gestion du blocage volontaire.
- [ ] Interface Vue 3 (`Step2EnvSetup.vue`) enrichie du panneau de révision des acteurs, de la modalité de correction motivée et des options de blocage préventif.
- [ ] Filet hermétique complet exécuté sur l'hôte et sous Docker (nombre de tests supérieur à 1112, 0 échec).
- [ ] Revue de code contradictoire BMAD menée et validée, artefacts de suivi actualisés.

---

## Tâches

- [ ] T1 — Modèle `ActorSelection` et gestionnaire de persistance atomique `actors.json` (`app/models/actor_selection.py`) (AC1).
- [ ] T2 — Implémentation de la route `POST /api/simulation/actors/preview` avec résolution serveur, cache d'empreinte et exposition des diagnostics de contexte et de conflits (`app/api/simulation.py`) (AC2).
- [ ] T3 — Implémentation de la route `POST /api/simulation/actors/review` avec contrôle de concurrence optimiste (409), verrouillage d'état, validation stricte des rôles et justifications obligatoires (`app/api/simulation.py`) (AC3).
- [ ] T4 — Intégration de `actors.json` dans `SimulationManager.prepare_simulation` : parcours simple sans revue préalable, honorabilité des corrections humaines et transmission des rôles qualifiés aux prompts des personas (`app/services/simulation_manager.py`) (AC4).
- [ ] T5 — Mécanisme de détection d'obsolescence sur divergence de l'empreinte `input_fingerprint` et garde-fous de réutilisation (`app/services/simulation_manager.py`) (AC5).
- [ ] T6 — Mécanisme de blocage volontaire (`block_on_review`, `block_on_conflict`) avec diagnostics explicites dans l'API et le gestionnaire (`app/api/simulation.py`, `app/services/simulation_manager.py`) (AC6).
- [ ] T7 — Interface utilisateur dans `frontend/src/components/Step2EnvSetup.vue` : tableau des acteurs avec badges, dialogue de correction motivée, alertes de conflits et options de blocage préventif (AC7).
- [ ] T8 — Suites de tests hermétiques backend : modèle `ActorSelection`, routes API `/actors/preview` et `/actors/review`, intégration de `prepare_simulation` et blocage volontaire (`backend/tests/`) (AC8).
- [ ] T9 — Tests et vérifications frontend (composants Vue, formulaires et parité linguistique i18n) (AC7, AC8).
- [ ] T10 — Qualification Docker complète, passage de `ruff check .` et `validate_plans.py`, mise à jour des artefacts de suivi et passage en `review` (AC8, AC9).

---

## Notes de développement

### Modèle `ActorSelection` et structure de `actors.json`

Le fichier `actors.json` est le contrat d'échange entre la classification automatique, l'arbitrage humain et le moteur de préparation de simulation OASIS. Il réside dans `uploads/simulations/{simulation_id}/actors.json`.

Sa structure canonique :
```json
{
  "schema_version": 1,
  "policy_version": "1.0.0",
  "simulation_id": "sim_123456",
  "project_id": "proj_abcdef",
  "graph_id": "graph_abcdef",
  "revision": 1,
  "input_fingerprint": "a3f5c9...",
  "counts": {
    "total": 35,
    "eligible": 12,
    "review": 3,
    "ineligible": 20
  },
  "actors": [
    {
      "entity_uuid": "uuid_1",
      "entity_name": "Éric Zemmour",
      "original_type": "Person",
      "qualified_role": "person",
      "eligibility_status": "eligible",
      "confidence": 0.95,
      "reasoning": "Personnalité politique individuelle",
      "is_human_modified": false,
      "last_modified_at": null,
      "justification": null
    }
  ],
  "modifications_history": [],
  "created_at": "2026-10-11T12:00:00Z",
  "updated_at": "2026-10-11T12:00:00Z"
}
```

### Règles strictes d'arbitrage humain (AC3)

1. **Rôles cibles admissibles pour un acteur éligible** : seuls `person` et `organization` peuvent porter le statut `eligible`.
2. **Rejet des non-acteurs** : toute tentative de requalifier un `product`, `concept`, `url`, `tariff` ou `location` en statut `eligible` est une violation de la politique d'intégrité sémantique et doit immédiatement lever une exception HTTP 400 avec message explicatif clair.
3. **Justification obligatoire** : toute entrée dans la liste `modifications` de `POST /api/simulation/actors/review` doit comporter un champ `justification` non vide (`str.strip() != ""`), sans quoi la requête est rejetée en HTTP 400.
4. **Concurrence optimiste** : le payload de révision fournit `expected_revision`. Si `expected_revision != actors.revision`, le serveur répond en HTTP 409 Conflict pour empêcher l'écrasement silencieux d'arbitrages concurrents.
5. **Verrouillage d'état** : aucune modification n'est permise si la simulation est en cours de préparation (`SimulationStatus.PREPARING`), en cours d'exécution (`SimulationStatus.RUNNING`) ou terminée (`SimulationStatus.COMPLETED`).

### Parcours simple vs parcours avancé (AC4, AC7)

- **Mode simple par défaut** : l'utilisateur qui clique directement sur "Lancer la préparation" ne doit subir aucun blocage artificiel. Le système génère automatiquement `actors.json` (révision 1) via `ActorClassifierService` et applique immédiatement la barrière.
- **Mode révision (avancé)** : l'utilisateur accède à la liste, observe les décisions de classification, corrige au besoin certaines entités avec motif, et active optionnellement le blocage préventif en cas de doute persistant (`block_on_review`) ou de conflits ouverts (`block_on_conflict`).

### Points d'intégration du code existant

| Fichier / Composant | Modification attendue |
|---|---|
| `backend/app/models/actor_selection.py` | Nouveau modèle : dataclass `ActorSelection`, items d'acteurs, historique et persistance atomique. |
| `backend/app/api/simulation.py` | Ajout des routes `POST /api/simulation/actors/preview` et `POST /api/simulation/actors/review`, support des options de blocage dans `/prepare`. |
| `backend/app/services/simulation_manager.py` | Consommation de `actors.json`, validation de fraîcheur d'empreinte, transmission des rôles qualifiés et blocage volontaire. |
| `frontend/src/components/Step2EnvSetup.vue` | Intégration du composant de révision des acteurs, badges d'état, modal de correction motivée et options de blocage préventif. |

---

## Revue

*(Section complétée lors du passage en revue contradictoire)*

---

## Notes de complétion

*(Section complétée à la clôture de la story)*
