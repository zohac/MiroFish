"""Gestion de la politique d'écriture ontologique par projet."""

from __future__ import annotations

from typing import Callable, Optional

from ..models.project import ProjectManager, ProjectStatus
from ..utils.graph_store import GraphStore, GraphValidationWarning
from ..utils.graph_store.errors import GraphNotFoundError, GraphValidationError

from ..utils.project_locks import project_lock
from ..utils.graph_store.factory import get_graph_store, release_graph_store


class OntologyPolicyService:
    """Orchestre la préférence projet sans connaître le backend concret."""

    @staticmethod
    def update(project_id: str, strict_ontology: bool, store: Optional[GraphStore] = None, store_factory: Callable[[], GraphStore] = get_graph_store):
        if type(strict_ontology) is not bool:
            raise GraphValidationError("strict_ontology doit être un booléen JSON")
        with project_lock(project_id):
            project = ProjectManager.get_project(project_id)
            if project is None:
                raise GraphNotFoundError(f"Projet introuvable : {project_id}")
            if project.status == ProjectStatus.GRAPH_BUILDING:
                raise GraphValidationError("La politique ne peut pas changer pendant une ingestion")
            # Un graphe peut être connu alors que sa pose d'ontologie a échoué.
            if project.graph_id:
                owned = store is None
                store = store if store is not None else store_factory()
                try:
                    if store.get_applied_ontology(project.graph_id) is not None:
                        store.update_ontology_policy(project.graph_id, strict_ontology)
                finally:
                    if owned:
                        release_graph_store(store)
            if project.strict_ontology != strict_ontology:
                project.strict_ontology = strict_ontology
                ProjectManager.save_project(project)
            return project

    @staticmethod
    def warnings(
        project_id: str,
        store: Optional[GraphStore] = None,
        since: Optional[str] = None,
        store_factory: Callable[[], GraphStore] = get_graph_store,
    ) -> list[GraphValidationWarning]:
        project = ProjectManager.get_project(project_id)
        if project is None:
            raise GraphNotFoundError(f"Projet introuvable : {project_id}")
        if not project.graph_id:
            raise GraphNotFoundError(f"Aucune ontologie appliquée au projet : {project_id}")
        owned = store is None
        store = store if store is not None else store_factory()
        try:
            if store.get_applied_ontology(project.graph_id) is None:
                raise GraphNotFoundError(f"Aucune ontologie appliquée au projet : {project_id}")
            return store.get_ontology_warnings(project.graph_id, since=since)
        finally:
            if owned:
                release_graph_store(store)
