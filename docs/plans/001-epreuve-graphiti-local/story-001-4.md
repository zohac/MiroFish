---
id: "001-4"
epic: "001"
titre: "Embedder local Sentence-Transformers pour Graphiti"
statut: done
auteur: agent
format: "2"
---

# Story 001-4 — Embedder local Sentence-Transformers pour Graphiti

## Pourquoi cette story

L'épreuve Graphiti local (Epic 001) a pour but de valider que la construction du
graphe de connaissances peut fonctionner intégralement en environnement local,
sans dépendre d'un service cloud payant (ADR 0001, ADR 0004 et NFR-1 : coût
marginal de 0 €).

La story 001-3 a résolu l'accès au LLM gratuit (`space-bunny-free` sur OpenCode Go)
en injectant les en-têtes de session requis. Cependant, `graphiti-core` a besoin
d'une seconde brique fondamentale d'inférence : un client d'embeddings
(`EmbedderClient`). Cet embedder est invoqué systématiquement lors de l'extraction
d'épisodes pour vectoriser :
1. Les noms d'entités (`node.generate_name_embedding`) ;
2. Les faits portés par les arêtes (`edge.generate_embedding`) ;
3. Les nœuds en lot lors de la consolidation (`create_entity_node_embeddings`).

Par défaut, si aucun `embedder` n'est fourni au constructeur `Graphiti(...)`, la
bibliothèque instancie automatiquement `OpenAIEmbedder()`, qui fait appel à l'API
cloud payante `text-embedding-3-small` d'OpenAI. Sans clé OpenAI valide, tout appel
d'extraction d'épisode échoue immédiatement avec une erreur d'authentification.

### Levée d'une fausse hypothèse de blocage (ADR 0010 et `architecture.md` §3)

Les documents de cadrage initiaux (`story-001-1.md`, `architecture.md` §3, `epic-001.md`)
anticipaient que cette story serait bloquée par un conflit de dépendances
identique à celui du driver Neo4j :
> `camel-oasis==0.2.5` épingle `sentence-transformers==3.0.0` alors que
> `graphiti-core[sentence-transformers]` réclame `>=3.2.1`.

L'inspection minutieuse de `graphiti-core==0.30.2` (installé au cours de la story 001-1b)
révèle une réalité différente et bien plus favorable :
1. `graphiti-core` ne fournit **aucun** `SentenceTransformerEmbedder` interne, même
   lorsque l'extra `[sentence-transformers]` est activé ! L'extra ne servait qu'à
   un composant de reclassement optionnel (`BGERerankerClient`).
2. Pour les embeddings, `graphiti-core` expose une interface abstraite pure et minimale :
   `graphiti_core.embedder.client.EmbedderClient` (méthodes `create` et `create_batch`).
3. `sentence-transformers==3.0.0` et `torch==2.9.1` sont **déjà installés et opérationnels**
   dans l'environnement virtuel du projet (fournis par `camel-oasis`).
4. `SentenceTransformer` s'importe et s'exécute déjà avec succès en local (validé
   sur le modèle `all-MiniLM-L6-v2`, produisant des vecteurs de 384 dimensions en ~1 ms).

**Conclusion architecturale :** Il n'y a **aucun conflit de dépendances à arbitrer**.
Nous n'avons besoin d'aucun extra `graphiti-core[sentence-transformers]`, d'aucune
modification de `backend/pyproject.toml`, et d'aucun élargissement de l'override
de l'ADR 0010. Les 19 tests stricts de `backend/tests/test_pyproject_override.py`
demeurent intacts et 100 % conformes.

Cette story consiste donc à développer un adaptateur local propre
`SentenceTransformerEmbedder` sous-classant `EmbedderClient`, à le tester
unitairement et à prouver son intégration avec Graphiti sans aucun appel réseau.

## Définition de prêt

- [x] Critères Given/When/Then formalisés et mesurables
- [x] Aucune dépendance externe non résolue — `sentence-transformers==3.0.0` et `torch==2.9.1` sont déjà présents dans `uv.lock`
- [x] Invariants de l'ADR 0010 et de `test_pyproject_override.py` respectés (aucune modification de `backend/pyproject.toml`)
- [x] Contrat d'interface de `graphiti_core.embedder.client.EmbedderClient` inspecté (`create`, `create_batch`)
- [x] Modèle d'embedding local sélectionné (`all-MiniLM-L6-v2`, 384 dimensions, poids légers ~90 Mo)
- [x] Documents à consulter lus — [`epic-001.md`](epic-001.md),
      [`prd.md`](prd.md),
      [`architecture.md`](architecture.md) §3,
      [ADR 0001](../../decisions/0001-graphiti-neo4j-local.md),
      [ADR 0010](../../decisions/0010-override-driver-neo4j.md),
      [ADR 0011](../../decisions/0011-inventaire-driver-et-format-de-story.md),
      `backend/tests/test_pyproject_override.py`

## Définition de fini

- [x] Un module `backend/app/utils/graphiti_embedder.py` fournit la classe `SentenceTransformerEmbedder`, sous-classe directe de `graphiti_core.embedder.client.EmbedderClient`
- [x] La méthode `create(input_data)` vectorise une chaîne unique ou une liste unitaire et renvoie une liste native Python de flottants (`list[float]`) de dimension 384
- [x] La méthode `create_batch(input_data_list)` vectorise un lot de chaînes et renvoie une liste de vecteurs (`list[list[float]]`)
- [x] Les calculs d'inférence CPU/GPU sont exécutés hors de la boucle événementielle asyncio via `asyncio.to_thread` afin de ne pas bloquer les requêtes concurrentes
- [x] L'instanciation de `Graphiti(..., embedder=SentenceTransformerEmbedder())` est fonctionnelle sans nécessiter `OPENAI_API_KEY`
- [x] Une sonde de vérification autonome (`backend/scripts/verifier_embedder_graphiti.py`) permet d'exercer l'encodage local (unitaire et par lot), de mesurer le temps d'inférence et de vérifier la stabilité des dimensions
- [x] Une suite de tests unitaires hermétiques (`backend/tests/test_graphiti_embedder.py`) couvre tous les cas avec mocks (ou modèle factice) sans téléchargement intempestif en CI
- [x] Aucun changement n'est apporté à `backend/pyproject.toml` : `test_override_targets_neo4j_only` et tous les tests de `test_pyproject_override.py` restent au vert
- [x] Les 297 tests existants restent verts (aucun test ne régresse) — 315 tests au total
- [x] `ruff check .` et `scripts/validate_plans.py` passent sans avertissement ni erreur
- [x] Aucun secret ni fichier de poids volumineux n'est commité dans le dépôt

## Tâches

- [x] 1. Définir l'adaptateur `SentenceTransformerEmbedder(EmbedderClient)` dans `backend/app/utils/graphiti_embedder.py` avec configuration de modèle et de dimensions (défaut : `all-MiniLM-L6-v2`, 384 dim)
- [x] 2. Implémenter le chargement paresseux (*lazy loading*) de `SentenceTransformer` pour éviter d'alourdir le temps de démarrage des commandes simples
- [x] 3. Implémenter les méthodes `create` et `create_batch` avec conversion rigoureuse en `list[float]` et délégation asynchrone via `asyncio.to_thread`
- [x] 4. Écrire le script de vérification `backend/scripts/verifier_embedder_graphiti.py` exerçant l'encodage unitaire et par lot, avec affichage des dimensions et de la latence
- [x] 5. Écrire les tests unitaires dans `backend/tests/test_graphiti_embedder.py` (vérification des dimensions, compatibilité des formats d'entrée, gestion du mode batch, intégration avec `Graphiti`)
- [x] 6. Vérifier l'intégration conjointe `Graphiti(llm_client=MiroFishLLMClient(), embedder=SentenceTransformerEmbedder())`
- [x] 7. Vérifier la suite de tests complète (297 existants + nouveaux tests) et le linter `ruff`
- [x] 8. Mettre à jour `docs/STATUS.md`, `epic-001.md`, `sprint-status.yaml` et consigner les conclusions dans les notes de complétion

## Notes de développement

**Ce que cette story ne doit pas faire.** Elle ne doit pas modifier `backend/pyproject.toml`
ni `backend/uv.lock`. Elle ne doit pas tenter d'ajouter l'extra `[sentence-transformers]`
à `graphiti-core` (puisque cet extra n'apporte aucun embedder et créerait un conflit
artificiel avec le pin `camel-oasis`). Elle ne doit pas exécuter l'extraction des 30
chunks du document de l'épreuve (c'est l'objet de la story **001-5**). Son périmètre est
strictement la fourniture d'un embedder local conforme à l'interface Graphiti.

**Interface de `EmbedderClient` dans `graphiti-core 0.30.2`.**
Dans `graphiti_core/embedder/client.py` :
```python
class EmbedderConfig(BaseModel):
    embedding_dim: int = Field(default=EMBEDDING_DIM, frozen=True)

class EmbedderClient(ABC):
    @abstractmethod
    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        pass

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        raise NotImplementedError()
```
Deux points d'attention majeurs :
1. `node.generate_name_embedding` et `edge.generate_embedding` appellent `embedder.create(input_data=[text])` avec une liste contenant une seule chaîne. L'implémentation de `create` doit donc accepter aussi bien un `str` qu'un `list[str]` à un élément et retourner un vecteur unique `list[float]`.
2. `create_entity_node_embeddings` appelle explicitement `await embedder.create_batch([node.name for node in filtered_nodes])`. La méthode `create_batch` ne doit pas lever `NotImplementedError` mais vectoriser efficacement la liste complète.

**Choix du modèle local et performances.**
Le modèle `all-MiniLM-L6-v2` présente des caractéristiques optimales pour l'épreuve :
- Poids : ~90 Mo (téléchargé et mis en cache localement au premier usage) ;
- Dimensionnalité : 384 (compact, garantissant des recherches rapides) ;
- Vitesse d'inférence : ~5 à 7 ms par texte sur CPU moderne à chaud (~50 ms pour un lot de 8 entités) ;
- Compatibilité : supporté nativement par `sentence-transformers==3.0.0` et `torch==2.9.1`.

**Délégation asynchrone non-bloquante.**
L'inférence PyTorch de `model.encode(...)` est bloquante pour l'interpréteur Python.
Pour préserver la réactivité de la boucle événementielle `asyncio` lors des traitements
Graphiti, les appels d'encodage sont délégués au pool de threads via `asyncio.to_thread(...)`.

**Stratégie de test : herméticité en CI.**
Conformément à AGENTS.md §2.2 :
- Les tests unitaires en CI ne dépendent pas du téléchargement d'un modèle lourd (classe `FakeSentenceTransformer` déterministe).
- La sonde autonome `verifier_embedder_graphiti.py` valide le modèle réel en conditions d'exécution locales et dispose d'un mode `--mock` testable en CI.

## Revue

Revue contradictoire menée par 4 couches indépendantes (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor).
Bilan du triage : 0 decision-needed, 6 patch, 0 defer, 2 rejetés.

### Constats de revue retenus (Patch)

- [x] [Review][Patch] Validation de dimension minimale et alerte de dimension de modèle (`backend/app/utils/graphiti_embedder.py:100`)
- [x] [Review][Patch] Gestion des chaînes vides et espaces blancs dans `create` (`backend/app/utils/graphiti_embedder.py:118`)
- [x] [Review][Patch] Avertissement explicite si `create` est appelé avec une liste multi-éléments (`backend/app/utils/graphiti_embedder.py:123`)
- [x] [Review][Patch] Ajout du mode `--mock` dans `verifier_embedder_graphiti.py` et test unitaire de la sonde hermétique (`backend/scripts/verifier_embedder_graphiti.py:38`, `backend/tests/test_graphiti_embedder.py`)
- [x] [Review][Patch] Rectification de l'arithmétique du filet de tests dans la documentation (base 297 + 18 tests = 315)
- [x] [Review][Patch] Alignement du statut de la story en `review` pendant le cycle de revue formel (AGENTS.md §2.8)

### Rejets documentés

- `Iterable[int]` token IDs dans `create` (`graphiti_embedder.py:129`) : faux positif, Graphiti ne manipule aucun identifiant de token brut, ce typage abstrait est un reliquat théorique de l'interface OpenAI.
- Troncature supérieure `vec[:dim]` : comportement conservé par conception pour permettre des configurations avec modèles à projection ou sous-espaces de dimensions.

## Notes de complétion

La story 001-4 a été menée à son terme avec succès et validée par revue de code bmad (4 couches contradictoires, 6 correctifs appliqués) :

1. **Adaptateur local Sentence-Transformers** (`backend/app/utils/graphiti_embedder.py`) :
   - `SentenceTransformerEmbedder` implémente `EmbedderClient` pour `graphiti-core 0.30.2`.
   - Modèle par défaut : `all-MiniLM-L6-v2` (384 dimensions, coût marginal de 0 €).
   - Lazy-loading thread-safe et encodage asynchrone non-bloquant via `asyncio.to_thread`.
   - Conversion native garantie en `list[float]` (compatibilité sérialisation Graphiti / Neo4j).
   - Robustesse accrue : vérification stricte de dimension minimale (`ValueError`), détection d'incohérence de dimension modèle, gestion neutre immédiate des chaînes vides/blanches et log d'avertissement en cas d'appel de `create()` avec plusieurs éléments.

2. **Sonde autonome de validation** (`backend/scripts/verifier_embedder_graphiti.py`) :
   - Exécution réelle validée : latence unitaire de ~7 ms à chaud, encodage par lot de 8 entités en ~50 ms (~6 ms/entité).
   - Mode `--mock` autonome intégré, permettant une exécution rapide en ~0.5 ms sans dépendance réseau.
   - Instanciation conjointe avec `Graphiti` et `MiroFishLLMClient` sans aucune clé OpenAI.

3. **Garanties et tests** :
   - 18 tests unitaires hermétiques dans `backend/tests/test_graphiti_embedder.py` couvrant les configurations, l'instanciation paresseuse, les cas limites, les exceptions de dimension et l'exécution mockée de la sonde.
   - Filet global étendu à **315 tests passés** (297 existants + 18 tests) sans aucune régression.
   - Aucun changement apporté au fichier `backend/pyproject.toml` : l'override Neo4j de l'ADR 0010 demeure le seul et unique override du projet.

