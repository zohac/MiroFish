# Architecture — Epic 009 : Éligibilité des acteurs et fiabilisation des sources

- **Statut** : `backlog` · **Dépend de** : 004, 005 · **Bloque** : 007
- **Référence PRD** : [`prd.md`](prd.md)

---

## 1. Vue d'ensemble du pipeline fiabilisé

L'architecture transforme le flux linéaire aveugle hérité d'amont en un pipeline à étapes contrôlées et traçables :

```mermaid
graph TD
    subgraph Sources ["1. Sources documentaires typées"]
        Docs["SourceDocument<br/>(fichiers avec rôle, date, priorité)"]
        Brief["SimulationBrief<br/>(consigne, état initial, règles, hypothèses)"]
        Chunks["DocumentChunk<br/>(source_id, section, texte)"]
    end

    subgraph KnowledgeStore ["2. Graphe de connaissances (GraphStore)"]
        Store["GraphitiGraphStore / Neo4j<br/>(:Episodic & :Entity)"]
        Facts["Arêtes de faits [r]<br/>(avec r.episodes -> :Episodic)"]
    end

    subgraph EligibilityLayer ["3. Éligibilité des acteurs (ActorSelection)"]
        Reader["ZepEntityReader<br/>(lecture de toutes les entités)"]
        Pass1["Filtre déterministe<br/>(URLs, prix, devises, dates)"]
        Pass2["Classifieur LLM structuré<br/>(rôle, éligibilité, justification)"]
        ReviewGate{"Prévalidation IHM/API<br/>(validation humaine optionnelle)"}
        KnowledgeOnly["Objets de connaissances<br/>(ineligible : produits, concepts, tarifs)<br/>-> Restent dans le graphe"]
        EligibleActors["Acteurs qualifiés<br/>(eligible : personnes, organisations)"]
    end

    subgraph SimulationExecution ["4. Simulation sociale & Analyse"]
        ProfileGen["OasisProfileGenerator<br/>(génération de personas OASIS)"]
        OasisEngine["Simulation OASIS<br/>(Twitter & Reddit)"]
        ReportGen["ReportAgent<br/>(rapport avec provenance des faits)"]
    end

    Docs --> Chunks
    Brief --> Pass2
    Chunks --> Store
    Store --> Facts
    Facts --> Reader
    Reader --> Pass1
    Pass1 --> Pass2
    Pass2 --> ReviewGate
    ReviewGate -->|ineligible| KnowledgeOnly
    ReviewGate -->|eligible| EligibleActors
    EligibleActors --> ProfileGen
    KnowledgeOnly -.->|contexte passif| ProfileGen
    ProfileGen --> OasisEngine
    OasisEngine --> ReportGen
    Store -.->|vérification des sources| ReportGen
```

---

## 2. Modèles de données

### 2.1 Modèle d'éligibilité (`ActorEligibility`)

Placé dans `backend/app/models/actor_eligibility.py` :

```python
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

class ActorRole(str, Enum):
    """Rôle sémantique générique d'une entité."""
    PERSON = "person"                  # Individu réel ou persona humaine
    ORGANIZATION = "organization"      # Entreprise, organisme officiel, institution
    COLLECTIVE = "collective"          # Communauté, groupe informel
    PRODUCT = "product"                # Produit, logiciel, offre, formule
    SERVICE = "service"                # Service rendu
    DOMAIN = "domain"                  # Nom de domaine, site web, URL
    PLACE = "place"                    # Lieu géographique, ville, pays
    EVENT = "event"                    # Événement daté, réunion, incident
    CONCEPT = "concept"                # Idée abstraite, sujet, thématique
    UNKNOWN = "unknown"                # Non déterminé

class EligibilityStatus(str, Enum):
    """Statut d'éligibilité à devenir un agent de simulation."""
    ELIGIBLE = "eligible"              # Autorisé à devenir un compte OASIS actif
    INELIGIBLE = "ineligible"          # Conservé en base de connaissances, exclu des agents
    REVIEW = "review"                  # Nécessite confirmation (ambigu)

@dataclass
class ActorEligibility:
    """Qualification d'une entité du graphe."""
    entity_uuid: str
    entity_name: str
    role: ActorRole
    status: EligibilityStatus
    rationale: str
    confidence: float
    original_type: str = "Entity"
    attributes: Dict[str, Any] = field(default_factory=dict)
```

### 2.2 Documents sources et brief (`SourceDocument` & `SimulationBrief`)

Placés dans `backend/app/models/source_document.py` et intégrés dans `Project` :

```python
class DocumentRole(str, Enum):
    FACTS = "facts"                    # Faits établis et avérés
    SCENARIO = "scenario"              # Déroulement ou événement déclencheur
    PERSONAS = "personas"              # Descriptions de cibles ou profils
    HYPOTHESES = "hypotheses"          # Hypothèses ouvertes à explorer
    CONSTRAINTS = "constraints"        # Règles et limites infranchissables
    REFERENCE = "reference"            # Documentation technique ou légale

@dataclass
class SourceDocument:
    document_id: str
    filename: str
    role: DocumentRole
    priority: int = 1                  # 1 (haute) à 5 (basse)
    date: Optional[str] = None
    total_chunks: int = 0

@dataclass
class SimulationBrief:
    goal: str                          # Question exacte à explorer
    initial_state: str                 # Faits acquis à l'instant t0
    target_audiences: List[str]        # Cibles recherchées
    excluded_actors: List[str]         # Entités interdites de simulation
    rules: List[str]                   # Contraintes absolues
    hypotheses: List[str]              # Points d'interrogation à observer
```

---

## 3. Classifieur d'éligibilité agnostique à deux passes

Le composant `ActorClassifierService` (`backend/app/services/actor_classifier.py`) opère en deux étapes sans aucune règle hardcodée propre à un métier :

### Passe 1 : Filtrage déterministe
- **Exclusion par syntaxe structurelle** :
  - Expressions régulières de détection d'URLs, domaines internet (`.fr`, `.com`, `.org`, `http://`, `https://`).
  - Expressions régulières de tarifs, devises (`€`, `$`, `EUR`, `USD`, `mensuel`, `abonnement`).
  - Dates pures ou durées isolées (`2026-10-10`, `3 mois`).
- **Résultat immédiat** : Ces entités sont marquées `role=DOMAIN`/`PRODUCT`, `status=INELIGIBLE`, sans consommer d'appel LLM.

### Passe 2 : Classification structurée LLM (modèle universel)
Pour les entités restantes, un prompt court avec sortie JSON contrainte (Pydantic / OpenAI Generic Client) prend en entrée :
- Le nom de l'entité, son résumé (`summary`), ses attributs et ses voisins immédiats dans le graphe.
- Les consignes du `SimulationBrief` (pour savoir si une marque officielle doit disposer d'un compte de communication ou rester passive).
- **Format de sortie attendu** :
  ```json
  {
    "role": "person",
    "status": "eligible",
    "rationale": "Identifié comme praticienne cliente de la plateforme, rôle d'utilisatrice finale.",
    "confidence": 0.95
  }
  ```
- **Règle de sécurité (NFR-3)** : En cas d'échec ou d'incertitude (`confidence < 0.7`), le statut passe en `review`.

---

## 4. Traçabilité des sources dans Neo4j (`GraphStore`)

La traçabilité s'appuie sur les capacités existantes de Neo4j et Graphiti :

```mermaid
erDiagram
    SourceDocument ||--o{ DocumentChunk : "découpé en"
    DocumentChunk ||--|| EpisodicNode : "ingéré comme (:Episodic)"
    EpisodicNode ||--o{ Relationship : "r.episodes liste l'UUID"
    EntityNode ||--o{ Relationship : "source/target"

    SourceDocument {
        string document_id PK
        string filename
        string role
        int priority
    }
    EpisodicNode {
        string uuid PK
        string group_id
        string source_document_id
        string source_filename
        int chunk_index
        string content
    }
    Relationship {
        string uuid PK
        string fact
        list episodes "UUIDs des épisodes sources"
        string valid_at
    }
    EntityNode {
        string uuid PK
        string name
        list labels
    }
```

À l'ingestion dans `GraphitiGraphStore.add_text_batch` :
- Chaque appel à `add_episode` reçoit un `source_description` normalisé :
  `f"file:{doc_id}|name:{filename}|chunk:{idx}"`.
- Une passe Cypher finale indexée associe sur les nœuds `:Episodic` les propriétés `source_document_id`, `source_filename`, `chunk_index`.
- Ainsi, pour n'importe quelle relation `[r]`, une requête Cypher simple :
  ```cypher
  MATCH (e:Episodic) WHERE e.uuid IN r.episodes
  RETURN e.source_filename, e.chunk_index, e.content
  ```
  restitue la citation textuelle exacte et le document qui a produit le fait.

---

## 5. Flux de prévalidation et de simulation

```mermaid
sequenceDiagram
    autonumber
    actor User as Utilisateur / IHM
    participant API as API Flask (/api/simulation)
    participant Reader as ZepEntityReader
    participant Classifier as ActorClassifierService
    participant SimMgr as SimulationManager
    participant ProfileGen as OasisProfileGenerator
    participant Oasis as camel-oasis

    User->>API: POST /api/simulation/actors/preview (project_id, graph_id)
    API->>Reader: Lecture de toutes les entités du graphe
    Reader-->>API: 35 entités brutes (:Entity)
    API->>Classifier: classify_entities(entities, brief)
    Classifier->>Classifier: Passe 1 (déterministe) + Passe 2 (LLM structuré)
    Classifier-->>API: 12 éligibles, 20 inéligibles, 3 en review
    API-->>User: Réponse JSON (liste des acteurs, rôles et justifications)

    opt Ajustement optionnel par l'utilisateur
        User->>API: POST /api/simulation/actors/review (modifications manuelles)
        API->>SimMgr: Enregistrement dans uploads/simulations/{id}/actors.json
    end

    User->>API: POST /api/simulation/prepare
    API->>SimMgr: prepare_simulation()
    SimMgr->>SimMgr: Filtre : ne conserve QUE status=ELIGIBLE
    SimMgr->>ProfileGen: generate_profiles_from_entities(eligible_actors)
    Note over ProfileGen: 0 produit ni concept transformé en profil !
    ProfileGen-->>SimMgr: Profils Twitter/Reddit conformes
    SimMgr->>Oasis: Exécution de la simulation
```

---

## 6. Synthèse des composants et de leur responsabilité

| Composant | Fichier | Responsabilité |
|---|---|---|
| `ActorEligibility` | `app/models/actor_eligibility.py` | Modèle de données de qualification d'acteurs. |
| `SourceDocument` | `app/models/source_document.py` | Modèle de document typé avec rôle et métadonnées. |
| `ActorClassifierService` | `app/services/actor_classifier.py` | Moteur hybride (déterministe + LLM) de classification d'éligibilité. |
| `SimulationManager` | `app/services/simulation_manager.py` | Intégration de la barrière d'éligibilité avant passage à OASIS. |
| `GraphitiGraphStore` | `app/utils/graph_store/graphiti_store.py` | Provenance enrichie sur les nœuds `:Episodic`. |
| `ReportAgent` | `app/services/report_agent.py` | Provenance sourcée des affirmations dans le rapport final. |
