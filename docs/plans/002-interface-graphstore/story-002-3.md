---
id: "002-3"
epic: "002"
titre: "Factory get_graph_store() et configuration ZEP_BACKEND"
statut: done
auteur: agent
format: "2"
---

# Story 002-3 — Factory get_graph_store() et configuration ZEP_BACKEND

## Pourquoi cette story

L'Epic 002 prépare le découplage entre MiroFish et le fournisseur de graphe de connaissances (ADR 0001, AGENTS.md §2.1).
La story 002-1 a posé l'interface neutre `GraphStore` et ses modèles de données.
La story 002-2 a implémenté `ZepGraphStore` en encapsulant l'ensemble des interactions avec le SDK Zep Cloud.

Pour permettre aux services métiers et aux routes API d'abandonner l'instanciation directe du client Zep
sans introduire de bifurcations dispersées (`if zep else graphiti`, proscrit par AGENTS.md §2.1) :
1. Une **factory unique et centralisée** `get_graph_store()` doit être implémentée dans `backend/app/utils/graph_store/factory.py`.
2. La variable de configuration `ZEP_BACKEND` doit piloter le choix de l'implémentation :
   - `'cloud'` (défaut strict) : retourne une instance de `ZepGraphStore`.
   - `'graphiti'` : lève une exception explicite `NotImplementedError` indiquant que l'implémentation fait l'objet de l'Epic 003.
   - Toute autre valeur inconnue : lève `GraphValidationError` avec un message clair sur les valeurs admises.
3. Le mécanisme d'aiguillage doit être totalement insensible à la casse et aux espaces superflus (`" Cloud "` -> `"cloud"`).
4. La factory doit offrir un **mécanisme d'injection de store factice** (`set_graph_store_override` et gestionnaire de contexte `override_graph_store`)
   permettant aux tests unitaires des stories 002-4 et 002-5 d'injecter un `FakeGraphStore` sans nécessiter de clé API ni d'accès réseau.
5. `backend/app/config.py` doit déclarer formellement `ZEP_BACKEND` (défaut `'cloud'`) et adapter la validation de `ZEP_API_KEY` en conséquence.
6. `backend/app/utils/graph_store/__init__.py` doit exposer `get_graph_store`, `set_graph_store_override` et `override_graph_store`.
7. Une suite complète de tests unitaires hermétiques `backend/tests/test_graph_store_factory.py` doit valider toutes les combinaisons
   d'aiguillage, de configuration et d'isolation d'override.

Cette story crée `backend/app/utils/graph_store/factory.py`, adapte `backend/app/config.py` et pose la suite
`backend/tests/test_graph_store_factory.py`.

## Définition de prêt

- [x] Contrat d'interface `GraphStore` posé et validé par la story 002-1 dans `backend/app/utils/graph_store/base.py`
- [x] Implémentation `ZepGraphStore` finalisée, testée (68 tests) et validée par la story 002-2 dans `zep_store.py`
- [x] Spécification de la factory et des fonctions d'override documentée dans `architecture.md` §5
- [x] Critère C3 du PRD ([`prd.md`](prd.md)) pris en compte (défaut `'cloud'`, validation stricte, support d'override)
- [x] Règle constitutionnelle vérifiée : Zéro bifurcation `if zep else graphiti` en dehors de la factory (AGENTS.md §2.1)
- [x] Documents à consulter lus — [`epic-002.md`](epic-002.md), [`architecture.md`](architecture.md), [`prd.md`](prd.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md)

## Définition de fini

- [x] `backend/app/utils/graph_store/factory.py` implémente `get_graph_store()`, `set_graph_store_override()` et `override_graph_store()`
- [x] `backend/app/config.py` déclare `ZEP_BACKEND: str = os.environ.get("ZEP_BACKEND", "cloud")`
- [x] La validation dans `Config.validate()` prend en compte `ZEP_BACKEND` (n'exige `ZEP_API_KEY` que lorsque `ZEP_BACKEND == "cloud"`)
- [x] `get_graph_store()` résout la configuration selon la priorité : argument explicite `backend` > `Config.ZEP_BACKEND` > `os.environ["ZEP_BACKEND"]` > `'cloud'`
- [x] `get_graph_store()` normalise le nom du backend (insensible à la casse, suppression des espaces)
- [x] Le backend `'cloud'` instancie et retourne `ZepGraphStore` (avec propagation de l'argument optionnel `api_key`)
- [x] Le backend `'graphiti'` lève `NotImplementedError` documentant le lien avec l'Epic 003
- [x] Tout backend non supporté ou chaîne vide lève une exception `GraphValidationError`
- [x] `set_graph_store_override()` permet d'injecter ou de réinitialiser (`None`) un store de remplacement prioritaire sur toute configuration
- [x] `override_graph_store()` fournit un context manager garantissant la restauration de l'état initial même en cas d'erreur
- [x] `backend/app/utils/graph_store/__init__.py` exporte `get_graph_store`, `set_graph_store_override` et `override_graph_store`
- [x] Une suite de tests hermétiques `backend/tests/test_graph_store_factory.py` valide 100 % des branches de la factory sans réseau
- [x] 100 % des tests existants (409 tests initiaux, 442 tests finaux) restent au vert (`uv run pytest tests/ -q`)
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Déclarer `ZEP_BACKEND` dans `backend/app/config.py` et ajuster la méthode de validation `validate()`
- [x] Créer `backend/app/utils/graph_store/factory.py`
  - [x] Déclarer l'état global privé `_store_override: Optional[GraphStore]`
  - [x] Implémenter `set_graph_store_override(store: Optional[GraphStore]) -> None` avec contrôle de type `GraphStore`
  - [x] Implémenter le context manager `@contextmanager def override_graph_store(store: Optional[GraphStore])`
  - [x] Implémenter `get_graph_store(backend: Optional[str] = None, api_key: Optional[str] = None) -> GraphStore` avec résolution de priorité, normalisation, aiguillage `cloud` / `graphiti` et rejets
- [x] Exposer les nouvelles fonctions dans `backend/app/utils/graph_store/__init__.py`
- [x] Créer la suite de tests unitaires `backend/tests/test_graph_store_factory.py`
  - [x] Test de retour de `ZepGraphStore` avec le backend par défaut `'cloud'`
  - [x] Test d'aiguillage via paramètre explicite `backend="cloud"`
  - [x] Test d'aiguillage via variable d'environnement `ZEP_BACKEND`
  - [x] Test de tolérance à la casse et aux espaces (`"  CLOUD  "`, `"Cloud"`)
  - [x] Test de levée de `NotImplementedError` pour `backend="graphiti"` avec message explicite
  - [x] Test de levée de `GraphValidationError` pour backends invalides (`"invalid"`, `"neo4j"`, `""`)
  - [x] Test de transmission de `api_key` explicite à `ZepGraphStore` et nettoyage des espaces
  - [x] Test d'override via `set_graph_store_override` avec `FakeGraphStore` et rejet par `TypeError` des types invalides
  - [x] Test de réinitialisation de l'override via `set_graph_store_override(None)`
  - [x] Test d'isolation avec le context manager `override_graph_store` (restauration garantie en cas d'exception)
  - [x] Test de suspension temporaire via `override_graph_store(None)`
  - [x] Test d'étanchéité des tests via `monkeypatch` pour garantir l'indépendance de l'environnement local
  - [x] Tests complets de `Config.validate()` (rejets d'un backend non supporté, vide ou de type non-chaîne)
- [x] Vérifier la non-régression globale (`uv run pytest tests/ -q` — 442 tests)
- [x] Contrôler `ruff check .` et `validate_plans.py`

## Notes de développement

- **Règle d'or de l'aiguillage** :
  La factory `get_graph_store()` est le **seul et unique endroit** de tout le dépôt MiroFish où le nom du backend
  est évalué conditionnellement. Aucun composant applicatif (`graph_builder.py`, `oasis_profile_generator.py`, `api/graph.py`, etc.)
  ne doit contenir de conditionnel sur le type de store (AGENTS.md §2.1).
- **Priorité de résolution de la configuration** :
  1. Override actif `_store_override` (injection programmatique pour tests).
  2. Argument direct `backend` passé à la fonction `get_graph_store()`.
  3. Propriété `Config.ZEP_BACKEND` de la configuration Flask/MiroFish.
  4. Variable d'environnement système `os.environ.get("ZEP_BACKEND")`.
  5. Valeur par défaut figée : `'cloud'`.
- **Isolation des tests unitaires** :
  La présence de `set_graph_store_override` et du gestionnaire de contexte `override_graph_store` est la pierre angulaire
  du refactoring des stories 002-4 et 002-5. Elle permettra aux tests existants de bouchonner le stockage sans aucune
  manipulation complexe de `unittest.mock.patch` sur les imports internes de `services/`.
- **Couplage avec Config.validate()** :
  `Config.validate()` n'exige `ZEP_API_KEY` que lorsque `ZEP_BACKEND == "cloud"`. En mode `graphiti`, le démarrage ne bloque pas sur l'absence de clé cloud. De plus, les backends inconnus ou mal formatés sont rejetés dès le démarrage.

## Revue

Revue contradictoire menée par 4 couches indépendantes (*Blind Hunter*, *Edge Case Hunter*, *Verification Gap*, *Acceptance Auditor*).
Bilan du triage : 0 `decision-needed`, 7 `patch`, 0 `defer`, 0 rejeté.

### Constats de revue retenus (Patch)

- [x] [Review][Patch] Validation stricte de `ZEP_BACKEND` dans `Config.validate()` : rejeter les backends non supportés (ex. `"neo4j"`, `"unknown"`), les chaînes vides et les types non-chaîne au démarrage du serveur [`backend/app/config.py:88-90`]
- [x] [Review][Patch] Contrôle de type dans `set_graph_store_override()` : exiger que `store` soit une instance de `GraphStore` ou `None`, en levant `TypeError` sur tout objet invalide [`backend/app/utils/graph_store/factory.py:16-20`]
- [x] [Review][Patch] Normalisation de `api_key` dans `get_graph_store()` : nettoyer les espaces de tête et de fin (`api_key.strip()`) à la frontière de la factory avant transmission à `ZepGraphStore` [`backend/app/utils/graph_store/factory.py:66`]
- [x] [Review][Patch] Tests unitaires pour la validation de `Config.validate()` : tester le rejet des backends inconnus, chaînes vides et types invalides [`backend/tests/test_graph_store_factory.py`]
- [x] [Review][Patch] Test unitaire pour la suspension temporaire d'override : vérifier que `with override_graph_store(None)` suspend temporairement un override actif dans un scope imbriqué [`backend/tests/test_graph_store_factory.py`]
- [x] [Review][Patch] Test unitaire pour le contrôle de type dans `set_graph_store_override()` : vérifier la levée de `TypeError` lors du passage d'un objet non `GraphStore` [`backend/tests/test_graph_store_factory.py`]
- [x] [Review][Patch] Documentation de `ZEP_BACKEND` dans `.env.example` : ajouter `ZEP_BACKEND=cloud` avec commentaire explicatif pour la découvrabilité locale [`.env.example:11`]

## Notes de complétion

- `backend/app/utils/graph_store/factory.py` implémente `get_graph_store()`, `set_graph_store_override()` et `override_graph_store()`.
- La configuration `ZEP_BACKEND` (défaut `'cloud'`) est déclarée dans `backend/app/config.py` et documentée dans `.env.example`.
- La méthode `Config.validate()` a été renforcée pour valider rigoureusement `ZEP_BACKEND` (type chaîne, rejet des chaînes vides et backends inconnus, exigence de `ZEP_API_KEY` uniquement pour le mode `'cloud'`).
- La factory implémente la résolution de priorité complète (override > argument explicite > Config.ZEP_BACKEND > os.environ > 'cloud') avec normalisation insensible à la casse et nettoyage des espaces.
- `set_graph_store_override()` valide rigoureusement le type du store (`GraphStore` ou `None`), garantissant le contrat de typage de `get_graph_store()`.
- `override_graph_store()` permet l'injection temporaire ou la suspension d'override avec garantie de restauration même en cas d'exception.
- 33 tests unitaires hermétiques couvrent 100 % des cas nominaux, limites et erreurs dans `backend/tests/test_graph_store_factory.py`.
- La revue contradictoire BMad (4 couches) a permis d'identifier et d'appliquer 7 patchs d'amélioration.
- Le filet de tests global passe de 409 à 442 tests, tous au vert (`uv run pytest tests/ -q`). Aucun avertissement lint (`ruff check .`), structure de planification validée (`validate_plans.py`).


