"""Tests d'isolation architecturale et de conformité Clean Architecture (Story 002-6).

Ce module constitue le garde-fou permanent de l'Epic 002 :
- Analyse AST stricte interdisant tout import direct du SDK propriétaire Zep Cloud
  ou de ses utilitaires dans les couches métiers (app/services) et API (app/api).
- Analyse AST interdisant toute bifurcation conditionnelle (if zep else graphiti)
  dans la logique applicative (PRD C5, AGENTS.md §2.1).
- Validation de l'étanchéité du cœur GraphStore (base.py, errors.py, factory.py).
- Vérification des critères de sortie C1 à C6 de l'Epic 002.
"""

import ast
import inspect
from pathlib import Path
from typing import List, Set
import pytest

from app.config import Config
from app.utils.graph_store.base import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from app.utils.graph_store.errors import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
)
from app.utils.graph_store.factory import (
    get_graph_store,
    override_graph_store,
)
from app.utils.graph_store.zep_store import ZepGraphStore


BACKEND_ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = BACKEND_ROOT / "app" / "services"
API_DIR = BACKEND_ROOT / "app" / "api"
GRAPH_STORE_DIR = BACKEND_ROOT / "app" / "utils" / "graph_store"

FORBIDDEN_VENDOR_MODULES: Set[str] = {
    "zep_cloud",
    "app.utils.zep",
    "utils.zep",
    "app.utils.zep_paging",
    "utils.zep_paging",
}


def _find_python_files(directory: Path) -> List[Path]:
    """Retourne l'ensemble des fichiers .py d'un répertoire (hors caches)."""
    return [
        p for p in directory.rglob("*.py")
        if "__pycache__" not in p.parts and not p.name.startswith(".")
    ]


def _collect_imported_modules(tree: ast.AST) -> List[str]:
    """Extrait tous les modules cibles des instructions import / from ... import."""
    imported: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
                for alias in node.names:
                    imported.append(f"{node.module}.{alias.name}")
            else:
                for alias in node.names:
                    imported.append(alias.name)
    return imported


def _is_forbidden_import(imported_module: str) -> bool:
    """Détecte si un module importé correspond ou dérive d'un module interdit."""
    for forbidden in FORBIDDEN_VENDOR_MODULES:
        if imported_module == forbidden or imported_module.startswith(f"{forbidden}."):
            return True
    return False


def test_services_layer_has_zero_direct_zep_imports():
    """Vérifie par analyse AST qu'aucun service métier n'importe zep_cloud ou utils.zep (Critère C4)."""
    service_files = _find_python_files(SERVICES_DIR)
    assert len(service_files) > 0, "Le dossier services/ doit contenir des fichiers Python"

    violations: List[str] = []
    for file_path in service_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
        imported_modules = _collect_imported_modules(tree)

        for mod in imported_modules:
            if _is_forbidden_import(mod):
                violations.append(f"{file_path.name} importe le module interdit '{mod}'")

    assert not violations, (
        f"Violations d'isolation détectées dans services/ ({len(violations)}) :\n"
        + "\n".join(violations)
    )


def test_api_layer_has_zero_direct_zep_imports():
    """Vérifie par analyse AST qu'aucune route HTTP de app/api/ n'importe zep_cloud (Critère C4)."""
    api_files = _find_python_files(API_DIR)
    assert len(api_files) > 0, "Le dossier api/ doit contenir des fichiers Python"

    violations: List[str] = []
    for file_path in api_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
        imported_modules = _collect_imported_modules(tree)

        for mod in imported_modules:
            if _is_forbidden_import(mod):
                violations.append(f"{file_path.name} importe le module interdit '{mod}'")

    assert not violations, (
        f"Violations d'isolation détectées dans api/ ({len(violations)}) :\n"
        + "\n".join(violations)
    )


def test_graph_store_core_has_zero_vendor_imports():
    """Vérifie que le cœur abstrait (base.py, errors.py, factory.py) ne dépend d'aucun SDK externe."""
    core_files = [
        GRAPH_STORE_DIR / "base.py",
        GRAPH_STORE_DIR / "errors.py",
        GRAPH_STORE_DIR / "factory.py",
    ]

    for file_path in core_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
        imported_modules = _collect_imported_modules(tree)

        for mod in imported_modules:
            assert not mod.startswith("zep_cloud"), f"{file_path.name} ne doit pas importer zep_cloud"
            assert not mod.startswith("neo4j"), f"{file_path.name} ne doit pas importer neo4j"
            assert not mod.startswith("graphiti_core"), f"{file_path.name} ne doit pas importer graphiti_core"


def test_no_conditional_backend_branching_in_business_logic():
    """Vérifie l'absence de bifurcations 'if zep else graphiti' dans les services et l'API (Critère C5)."""
    checked_files = _find_python_files(SERVICES_DIR) + _find_python_files(API_DIR)

    suspicious_keywords = {"zep_backend", "graphiti", "cloud"}
    branching_violations: List[str] = []

    for file_path in checked_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.IfExp)):
                # Inspecter les expressions de test pour repérer des comparaisons sur le backend
                test_dump = ast.dump(node.test).lower()
                if "backend" in test_dump and any(kw in test_dump for kw in suspicious_keywords):
                    branching_violations.append(
                        f"{file_path.name}:{getattr(node, 'lineno', '?')} : bifurcation suspecte sur backend"
                    )
            elif isinstance(node, getattr(ast, "Match", ())):
                subject_dump = ast.dump(node.subject).lower()
                if "backend" in subject_dump and any(kw in subject_dump for kw in suspicious_keywords):
                    branching_violations.append(
                        f"{file_path.name}:{getattr(node, 'lineno', '?')} : match/case suspect sur backend"
                    )

    assert not branching_violations, (
        "Bifurcations conditionnelles interdites détectées dans services/ et api/ (AGENTS.md §2.1) :\n"
        + "\n".join(branching_violations)
    )


def test_factory_contract_and_default_resolution(monkeypatch):
    """Vérifie le contrat d'instanciation de get_graph_store() (Critère C3)."""
    # Isolation hermétique de l'environnement (AGENTS.md §2.2)
    monkeypatch.delenv("ZEP_BACKEND", raising=False)
    monkeypatch.setattr(Config, "ZEP_BACKEND", None, raising=False)

    # 1. Résolution par défaut (cloud)
    store = get_graph_store(api_key="fake-test-key")
    assert isinstance(store, ZepGraphStore)
    assert isinstance(store, GraphStore)

    # 2. Rejet de backend invalide
    with pytest.raises(GraphValidationError):
        get_graph_store(backend="unknown_backend")

    # 3. Réservation explicite de graphiti (Epic 003)
    with pytest.raises(NotImplementedError) as exc_info:
        get_graph_store(backend="graphiti")
    assert "Epic 003" in str(exc_info.value)

    # 4. Mécanisme d'override étanche
    class FakeIsolatedStore(GraphStore):
        def create_graph(self, name, graph_id=None): return "iso-ok"
        def delete_graph(self, graph_id): pass
        def get_graph_data(self, graph_id): return {}
        def get_graph_info(self, graph_id): return GraphInfo(graph_id, 0, 0)
        def set_ontology(self, graph_id, ontology): pass
        def add_episode(self, graph_id, text, source_description="", metadata=None, created_at=None):
            return EpisodeRecord(uuid="ep", graph_id=graph_id)
        def add_text_batch(self, graph_id, chunks, batch_size=350, progress_callback=None):
            return BatchSubmissionRecord("b", "op", ["ep"], len(chunks))
        def wait_for_batch(self, batch, progress_callback=None, timeout=600.0): return True
        def wait_for_episodes(self, graph_id, episode_uuids, timeout=600.0): return True
        def get_all_nodes(self, graph_id): return []
        def get_all_edges(self, graph_id, include_temporal=True): return []
        def get_node(self, graph_id, node_uuid): return None
        def get_node_edges(self, graph_id, node_uuid): return []
        def search(self, graph_id, query, limit=10, scope="edges", reranker=None):
            return GraphSearchResult([], [], [], query, 0)

    fake_instance = FakeIsolatedStore()
    with override_graph_store(fake_instance):
        assert get_graph_store() is fake_instance
    # Après sortie du contexte, le store revient à la normale
    assert get_graph_store(api_key="fake-test-key") is not fake_instance


def test_all_prd_exit_criteria_are_met():
    """Atteste formellement que les critères de sortie C1 à C6 de l'Epic 002 sont satisfaits."""
    # C1 : Interface formelle GraphStore (14 méthodes abstraites et modèles neutres)
    abstract_methods = {
        name for name, val in inspect.getmembers(GraphStore, predicate=inspect.isfunction)
        if getattr(val, "__isabstractmethod__", False)
    }
    expected_methods = {
        "create_graph", "delete_graph", "get_graph_data", "get_graph_info",
        "set_ontology", "add_episode", "add_text_batch", "wait_for_batch",
        "wait_for_episodes", "get_all_nodes", "get_all_edges", "get_node",
        "get_node_edges", "search",
    }
    assert expected_methods.issubset(abstract_methods), "C1 : toutes les méthodes requises doivent être abstraites"

    # C2 : ZepGraphStore implémente 100 % de l'interface (aucune méthode abstraite non implémentée)
    for method in expected_methods:
        method_func = getattr(ZepGraphStore, method, None)
        assert method_func is not None, f"C2 : ZepGraphStore doit posséder la méthode {method}"
        assert getattr(method_func, "__isabstractmethod__", False) is False, (
            f"C2 : {method} dans ZepGraphStore doit être concrètement implémentée et non abstraite"
        )

    # C3 : Factory opérationnelle
    assert callable(get_graph_store), "C3 : get_graph_store doit être appelable"

    # C4 : 0 import direct dans services et api
    test_services_layer_has_zero_direct_zep_imports()
    test_api_layer_has_zero_direct_zep_imports()

    # C5 : 0 bifurcation conditionnelle dans services et api
    test_no_conditional_backend_branching_in_business_logic()

    # C6 : Préservation des exceptions neutres
    assert issubclass(GraphNotFoundError, GraphStoreError)
    assert issubclass(GraphConnectionError, GraphStoreError)
    assert issubclass(GraphTimeoutError, GraphStoreError)
    assert issubclass(GraphValidationError, GraphStoreError)
