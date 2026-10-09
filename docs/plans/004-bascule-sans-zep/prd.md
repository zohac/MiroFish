# PRD — Epic 004 : Construire un graphe et simuler en local sans clé Zep (ADR 0001, ADR 0004)

- **Statut** : `in-progress` · **Dépend de** : 001, 002, 003 · **Bloque** : 005, 006, 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'Epic 001 a prouvé la viabilité de la chaîne Graphiti + Neo4j 5.26 + OpenCode Go à coût marginal nul.
> L'Epic 002 a posé l'interface neutre `GraphStore` et démontré l'étanchéité architecturale par analyse AST.
> L'Epic 003 a livré l'implémentation complète `GraphitiGraphStore`, le chemin de lecture `zep_entity_reader.py` agnostique
> et le banc d'intégration réel Neo4j validé avec VERDICT GO (562 tests verts).
>
> **L'Epic 004 constitue l'aboutissement de la migration local-first** : il lève définitivement le verrou de la clé Zep
> Cloud dans l'ensemble de l'application (API, services, configuration) et assure la paramétrabilité universelle du LLM
> via les variables d'environnement `.env`.

---

## 1. Le problème

### 1.1 Contexte et état des lieux

À l'issue de l'Epic 003, `GraphitiGraphStore` implémente avec succès les 14 méthodes du contrat `GraphStore`, garantit un partitionnement strict par `group_id` dans Neo4j local, préserve la temporalité des arêtes et permet à `ZepEntityReader` d'extraire des entités sans dépendre d'une ontologie custom.

Cependant, **l'application MiroFish ne peut toujours pas être exécutée de bout en bout sans clé Zep Cloud** :
1. Les routes de l'API Flask (`backend/app/api/graph.py` et `backend/app/api/simulation.py`) contiennent des gardes rigides :
   ```python
   if not Config.ZEP_API_KEY:
       return jsonify({'error': 'ZEP_API_KEY not configured'}), 400
   ```
   Ces gardes bloquent systématiquement l'utilisateur dès la création ou la suppression d'un graphe, ainsi que lors du lancement d'une simulation, même lorsque `ZEP_BACKEND='graphiti'` est configuré.
2. Les services métiers instancient encore ponctuellement `GraphBuilderService(api_key=Config.ZEP_API_KEY)` au lieu de laisser la factory `get_graph_store()` résoudre le store de manière agnostique.
3. Le pipeline complet — du dépôt de documents bruts jusqu'à la simulation et au rapport — n'a jamais été exécuté de bout en bout en mode local sans clé Zep.

### 1.2 La paramétrabilité universelle du LLM via `.env` (ADR 0004)

Le projet a validé l'utilisation d'OpenCode Go (`https://opencode.ai/zen/go/v1` avec le modèle `space-bunny-free` et effort de raisonnement) pour garantir un coût marginal nul lors des tests et des développements (ADR 0004).

Néanmoins, **le choix du fournisseur et du modèle LLM ne doit jamais être figé en dur dans le code** :
- L'utilisateur doit pouvoir configurer dans son fichier `.env` n'importe quel endpoint compatible avec l'API OpenAI (OpenCode Go, OpenAI officiel, Groq, DeepSeek, vLLM, ou Ollama local).
- Le modèle (`LLM_MODEL_NAME`) doit être librement interchangeable (gratuit ou payant selon les besoins).
- La clé API (`LLM_API_KEY`) et l'effort de raisonnement (`LLM_REASONING_EFFORT`, ex: `low`, `medium`, `high`) doivent être pilotés dynamiquement par `.env`.
- Les mécanismes spécifiques à la passerelle OpenCode Go (injection d'en-tête de session `x-opencode-session` et `User-Agent` gérés par `llm_compat.py`) doivent rester **strictement transparents et conditionnels à l'hôte cible**, sans polluer ni perturber les requêtes adressées à d'autres fournisseurs compatibles OpenAI.
- L'ensemble des composants consommant du LLM dans l'application (`llm_client.py` pour MiroFish, `graphiti_llm_client.py` pour Graphiti) doit s'aligner sur cette configuration unique et homogène.

---

## 2. L'objectif

Permettre l'exécution complète de MiroFish en mode local-first sans clé Zep Cloud, avec un LLM 100 % paramétrable via `.env` :

1. **Lever le prérequis `ZEP_API_KEY`** :
   - Rendre `ZEP_API_KEY` strictement optionnelle dans `Config.validate()` et dans 100 % des routes de `backend/app/api/` dès lors que `ZEP_BACKEND='graphiti'`.
   - Permettre à `GraphBuilderService`, `SimulationRunner` et aux services associés d'opérer avec `api_key=None`.
2. **Homogénéiser et paramétrer le LLM via `.env`** :
   - Supporter tout endpoint compatible OpenAI via `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` et `LLM_REASONING_EFFORT`.
   - Garantir que pour nos tests et notre environnement de référence, la configuration OpenCode Go (`space-bunny-free`) fonctionne sans surcoût.
   - S'assurer que le client LLM Graphiti (`MiroFishLLMClient`) et le client MiroFish (`LLMClient`) partagent la même résolution de configuration.
3. **Construire un graphe réel de bout en bout** :
   - Valider la chaîne complète d'ingestion : document (PDF ou texte) → extraction de texte → découpage en chunks → `GraphBuilderService` → `GraphitiGraphStore` → Neo4j local.
   - Valider le suivi de progression asynchrone (`TaskManager`) et l'accès aux données du graphe via `/api/graph/<graph_id>/data`.
4. **Alimenter les personas et la simulation en local** :
   - Valider que `simulation_config_generator.py` et `oasis_profile_generator.py` exploitent le graphe Graphiti réel pour générer des personas et une configuration de simulation sans aucune clé Zep.
5. **Préserver la qualité et l'hermétisme** :
   - Maintenir le filet de 562 tests existants au vert et ajouter les tests de non-régression et de configuration dédiés.

---

## 3. Ce que cet epic n'est pas

| Hors périmètre | Pourquoi |
|---|---|
| Environnement Docker unifié pour toute l'application | Fait l'objet de l'Epic 005 (Docker-first, intégration backend + frontend + Neo4j dans compose unique). |
| Migration de données depuis un compte Zep Cloud existant | Fait l'objet de l'Epic 006 (si nécessaire). |
| Ontologie dynamique Pydantic générée à l'exécution | Reportée en v2 par l'ADR 0003 (Epic 007). |
| Refonte de l'interface utilisateur frontend (Vue) | L'API backend conserve ses contrats JSON identiques pour le frontend. |

---

## 4. Configuration cible et variables d'environnement (`.env`)

Le fichier `.env` à la racine du dépôt constitue la source unique de configuration locale :

```ini
# Backend de graphe (défaut 'graphiti' pour le mode local-first)
ZEP_BACKEND=graphiti

# Configuration LLM universelle (compatible API OpenAI)
LLM_BASE_URL=https://opencode.ai/zen/go/v1
LLM_API_KEY=opencode-go-key
LLM_MODEL_NAME=space-bunny-free
LLM_REASONING_EFFORT=medium

# Base de données graphe locale (Neo4j 5.26 épreuve)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=votre_mot_de_passe_local

# Désactivation stricte de la télémétrie Graphiti (AGENTS.md, vie privée)
GRAPHITI_TELEMETRY_ENABLED=false

# Clé Zep Cloud (optionnelle, requise UNIQUEMENT si ZEP_BACKEND=cloud)
# ZEP_API_KEY=
```

### Règles de résolution :
- Si `ZEP_BACKEND=graphiti`, `ZEP_API_KEY` n'est ni lue, ni exigée.
- Si `LLM_BASE_URL` contient `opencode.ai`, les en-têtes `x-opencode-session` et `User-Agent: mirofish/0.1.0` sont automatiquement injectés (ADR 0004).
- Si `LLM_BASE_URL` pointe vers un autre hôte (ex: `api.openai.com`, `localhost:11434`, etc.), aucun en-tête propriétaire n'est injecté, préservant la conformité standard du protocole OpenAI.
- `LLM_REASONING_EFFORT` n'est transmis dans la requête que si la variable est définie et non vide.

---

## 5. Exigences fonctionnelles (FR)

- **FR-1 (Validation de configuration sans Zep)** : `Config.validate()` ne lève d'erreur sur `ZEP_API_KEY` que si `ZEP_BACKEND == 'cloud'`. En mode `graphiti`, l'absence de `ZEP_API_KEY` est considérée comme nominale.
- **FR-2 (Déverrouillage des routes HTTP)** :
  - `POST /api/graph/build` : accepte la construction sans clé Zep.
  - `GET /api/graph/<graph_id>/data` : retourne les données de visualisation pour le frontend sans clé Zep.
  - `DELETE /api/graph/<graph_id>` : purge le graphe dans Neo4j sans clé Zep.
  - `POST /api/simulation/create` : prépare la simulation à partir du graphe local sans clé Zep.
- **FR-3 (Paramétrabilité LLM centralisée)** :
  - `backend/app/config.py` expose `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` et `LLM_REASONING_EFFORT`.
  - `backend/app/utils/llm_client.py` et `backend/app/utils/graphiti_llm_client.py` consomment ces valeurs de façon uniforme.
  - Support vérifié d'endpoints alternatifs sans régression.
- **FR-4 (Construction locale de bout en bout)** :
  - `GraphBuilderService.build_graph_async()` orchestre le traitement du texte, la soumission des batches et la complétion de la tâche avec `GraphitiGraphStore`.
  - Persistance effective des entités et relations dans l'instance locale Neo4j.
- **FR-5 (Enrichissement des Personas et Simulation)** :
  - `oasis_profile_generator.py` et `simulation_config_generator.py` interrogent le graphe via `ZepEntityReader` (adapté en Story 003-4) et génèrent des personas valides avec leurs traits et faits associés.

---

## 6. Exigences non fonctionnelles (NFR)

- **NFR-1 (Clean Architecture & DRY)** : Aucune conditionnelle `if zep else graphiti` dans les services applicatifs ou les générateurs. Toute l'adaptation passe par l'interface `GraphStore` et la factory `get_graph_store()`.
- **NFR-2 (Réversibilité)** : Si un utilisateur renseigne `ZEP_BACKEND=cloud` et fournit `ZEP_API_KEY`, le comportement hérité Zep Cloud reste 100 % fonctionnel sans régression.
- **NFR-3 (Hermétisme des tests)** : Les tests automatisés `pytest` ne dépendent ni de la présence d'un fichier `.env` réel, ni d'un accès réseau sortant.
- **NFR-4 (Robustesse des erreurs)** : En cas d'indisponibilité du LLM ou de Neo4j, les erreurs sont capturées proprement et remontées avec des messages clairs dans le statut de la tâche (`TaskStatus.FAILED`).

---

## 7. Critères de sortie — chiffrés

| # | Critère | Seuil exigé | Risque si non atteint |
|---|---|---|---|
| **C1** | **0 blocage lié à `ZEP_API_KEY`** | **100 % des routes de l'API** (`api/graph.py`, `api/simulation.py`) s'exécutent avec succès quand `ZEP_API_KEY` est absente de l'environnement (avec `ZEP_BACKEND='graphiti'`). | Blocage applicatif en local |
| **C2** | **Paramétrabilité LLM universelle** | **4 variables d'environnement** (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT`) supportées de manière unifiée par tous les clients LLM de l'application. 0 en-tête propriétaire envoyé aux hôtes hors `opencode.ai`. | Couplage rigide à un fournisseur |
| **C3** | **Construction de graphe réelle de bout en bout** | Ingestion réussie d'un document réel produisant un graphe Neo4j local non vide (**≥ 5 nœuds, ≥ 3 arêtes**) avec statut de tâche `COMPLETED` en 100 % local sans clé Zep. | Échec du pipeline d'ingestion |
| **C4** | **Extraction d'entités et configuration de simulation** | Génération avec succès d'au moins **3 personas typés** enrichis par les données du graphe local via `simulation_config_generator.py` sans clé Zep. | Rupture de la chaîne amont |
| **C5** | **Filet de tests et non-régression** | **100 % des 562 tests existants** restent au vert, enrichis de tests unitaires et d'intégration validant le fonctionnement sans clé Zep et la configuration LLM universelle (**filet global ≥ 572 tests**). | Régression silencieuse |
