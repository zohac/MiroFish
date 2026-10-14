"""Service d'orchestration des événements ontologiques (E1, E2, E3, E4) (story 007-4).

Ce service implémente :
- Comparaison de similarité de brief (SequenceMatcher) et règle du seuil < 0.95 (E2, AC4)
- Régénération sur ajout de document avec préservation des nœuds existants (E1, AC3, C4)
- Régénération forcée sur demande explicite (E3, AC5)
- Initialisation de la version initiale v1 (E4, AC7)
- Application idempotente au GraphStore
"""

from __future__ import annotations

import difflib
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..models.ontology_version import OntologyVersion, OntologyVersionStore
from ..models.project import Project, ProjectManager, ProjectStatus
from ..services.ontology_generator import OntologyGenerator
from ..utils.graph_store import GraphStore
from ..utils.graph_store.errors import GraphNotFoundError, GraphValidationError
from ..utils.graph_store.factory import get_graph_store, release_graph_store
from ..utils.project_locks import project_lock

logger = logging.getLogger(__name__)

BRIEF_SIMILARITY_THRESHOLD = 0.95


def calculate_brief_similarity(old_brief: Optional[str], new_brief: Optional[str]) -> float:
    """Calcule le ratio de similarité textuelle entre deux versions de brief.
    
    Retourne 1.0 si les deux sont identiques ou vides, ou difflib.SequenceMatcher.ratio().
    """
    s1 = (old_brief or "").strip()
    s2 = (new_brief or "").strip()
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def should_regenerate_on_brief_change(old_brief: Optional[str], new_brief: Optional[str]) -> bool:
    """Détermine si un changement de brief justifie une régénération (ratio < 0.95)."""
    ratio = calculate_brief_similarity(old_brief, new_brief)
    return ratio < BRIEF_SIMILARITY_THRESHOLD


class OntologyEventService:
    """Service centralisant les déclencheurs d'événements ontologiques E1, E2, E3, E4."""

    @staticmethod
    def _collect_project_texts(project: Project) -> List[str]:
        """Récupère les textes de tous les documents du projet."""
        doc_texts = ProjectManager.get_all_document_texts(project.project_id)
        if doc_texts:
            return list(doc_texts.values())
        # Repli sur le texte extrait unique ou vide
        single_text = ProjectManager.get_extracted_text(project.project_id)
        return [single_text] if single_text else []

    @classmethod
    def initialize_ontology(
        cls,
        project_id: str,
        ontology_dict: Dict[str, Any],
        source_summary: str = "Initialisation v1 du projet",
        store: Optional[GraphStore] = None,
        store_factory: Callable[[], GraphStore] = get_graph_store,
    ) -> OntologyVersion:
        """Événement E4 (Initialisation à la création) : crée la version v1 et l'applique (AC7)."""
        with project_lock(project_id):
            project = ProjectManager.get_project(project_id)
            if project is None:
                raise GraphNotFoundError(f"Projet introuvable : {project_id}")

            # Création de la version v1 immuable
            version = OntologyVersionStore.create(
                project_id=project_id,
                ontology_dict=ontology_dict,
                parent_version_id=None,
                source_summary=source_summary,
            )

            # Application sur le modèle projet
            project.apply_ontology(version)
            project.ontology = ontology_dict
            ProjectManager.save_project(project)

            # Pose sur le store si un graph_id est déjà associé
            if project.graph_id:
                owned = store is None
                st = store if store is not None else store_factory()
                try:
                    st.set_ontology(
                        project.graph_id,
                        version.to_ontology_dict(),
                        strict=project.strict_ontology,
                    )
                finally:
                    if owned:
                        release_graph_store(st)

            return version

    @classmethod
    def regenerate_on_demand(
        cls,
        project_id: str,
        generator: Optional[OntologyGenerator] = None,
        store: Optional[GraphStore] = None,
        store_factory: Callable[[], GraphStore] = get_graph_store,
    ) -> OntologyVersion:
        """Événement E3 (Demande explicite) : régénère immédiatement l'ontologie du projet (AC5)."""
        with project_lock(project_id):
            project = ProjectManager.get_project(project_id)
            if project is None:
                raise GraphNotFoundError(f"Projet introuvable : {project_id}")

            if project.status == ProjectStatus.GRAPH_BUILDING:
                raise GraphValidationError("Une construction de graphe ou ingestion est déjà en cours")

            texts = cls._collect_project_texts(project)
            requirement = project.simulation_requirement or ""
            context = project.additional_context

            gen = generator or OntologyGenerator()
            try:
                new_onto_dict = gen.generate(
                    document_texts=texts,
                    simulation_requirement=requirement,
                    additional_context=context,
                )
            except Exception as exc:
                raise GraphValidationError(f"Échec de la génération d'ontologie : {exc}") from exc

            # Vérifier que le format généré est valide
            if not isinstance(new_onto_dict, dict) or "entity_types" not in new_onto_dict:
                raise GraphValidationError("L'ontologie générée par le modèle est invalide")

            parent_id = project.applied_ontology_id
            version = OntologyVersionStore.create(
                project_id=project_id,
                ontology_dict=new_onto_dict,
                parent_version_id=parent_id,
                source_summary="Régénération explicite sur demande API",
            )

            project.apply_ontology(version)
            project.ontology = new_onto_dict
            ProjectManager.save_project(project)

            if project.graph_id:
                owned = store is None
                st = store if store is not None else store_factory()
                try:
                    st.set_ontology(
                        project.graph_id,
                        version.to_ontology_dict(),
                        strict=project.strict_ontology,
                    )
                finally:
                    if owned:
                        release_graph_store(st)

            return version

    @classmethod
    def on_brief_changed(
        cls,
        project_id: str,
        new_brief_text: str,
        generator: Optional[OntologyGenerator] = None,
        store: Optional[GraphStore] = None,
        store_factory: Callable[[], GraphStore] = get_graph_store,
    ) -> Tuple[bool, Optional[OntologyVersion]]:
        """Événement E2 (Modification du brief) : compare et régénère si ratio < 0.95 (AC4).
        
        Retourne (regenerated: bool, version: Optional[OntologyVersion]).
        """
        with project_lock(project_id):
            project = ProjectManager.get_project(project_id)
            if project is None:
                raise GraphNotFoundError(f"Projet introuvable : {project_id}")

            old_brief_text = project.simulation_requirement or ""
            ratio = calculate_brief_similarity(old_brief_text, new_brief_text)

            # Mise à jour du texte du brief sur le projet
            project.simulation_requirement = new_brief_text
            if project.simulation_brief:
                project.simulation_brief["goal"] = new_brief_text
                project.simulation_brief["raw_brief"] = new_brief_text

            if ratio >= BRIEF_SIMILARITY_THRESHOLD:
                # Retouche mineure : pas de régénération LLM
                ProjectManager.save_project(project)
                return False, None

            # Ratio < 0.95 : changement sémantique substantiel -> régénération
            texts = cls._collect_project_texts(project)
            gen = generator or OntologyGenerator()
            try:
                new_onto_dict = gen.generate(
                    document_texts=texts,
                    simulation_requirement=new_brief_text,
                    additional_context=project.additional_context,
                )
            except Exception as exc:
                ProjectManager.save_project(project)
                raise GraphValidationError(f"Échec de régénération lors du changement de brief : {exc}") from exc

            parent_id = project.applied_ontology_id
            version = OntologyVersionStore.create(
                project_id=project_id,
                ontology_dict=new_onto_dict,
                parent_version_id=parent_id,
                source_summary=f"Régénération sur modification du brief (ratio similarité {ratio:.2f} < 0.95)",
            )

            project.apply_ontology(version)
            project.ontology = new_onto_dict
            ProjectManager.save_project(project)

            if project.graph_id:
                owned = store is None
                st = store if store is not None else store_factory()
                try:
                    st.set_ontology(
                        project.graph_id,
                        version.to_ontology_dict(),
                        strict=project.strict_ontology,
                    )
                finally:
                    if owned:
                        release_graph_store(st)

            return True, version

    @classmethod
    def on_document_added(
        cls,
        project_id: str,
        document_id: str,
        document_text: str,
        filename: str,
        generator: Optional[OntologyGenerator] = None,
        store: Optional[GraphStore] = None,
        store_factory: Callable[[], GraphStore] = get_graph_store,
    ) -> OntologyVersion:
        """Événement E1 (Ajout de document) : régénère l'ontologie sur le corpus cumulé (AC3, C4)."""
        with project_lock(project_id):
            project = ProjectManager.get_project(project_id)
            if project is None:
                raise GraphNotFoundError(f"Projet introuvable : {project_id}")

            # Sauvegarde du nouveau document normalisé
            ProjectManager.save_document_text(project_id, document_id, document_text)
            
            # Mise à jour de la liste files si nécessaire
            existing_filenames = {f.get("filename") for f in project.files}
            if filename not in existing_filenames:
                project.files.append({
                    "filename": filename,
                    "size": len(document_text.encode("utf-8")),
                })

            # Réévaluation du corpus global cumulé
            texts = cls._collect_project_texts(project)
            requirement = project.simulation_requirement or ""
            context = project.additional_context

            gen = generator or OntologyGenerator()
            try:
                new_onto_dict = gen.generate(
                    document_texts=texts,
                    simulation_requirement=requirement,
                    additional_context=context,
                )
            except Exception as exc:
                raise GraphValidationError(f"Échec de régénération lors de l'ajout de document : {exc}") from exc

            parent_id = project.applied_ontology_id
            version = OntologyVersionStore.create(
                project_id=project_id,
                ontology_dict=new_onto_dict,
                parent_version_id=parent_id,
                source_summary=f"Régénération sur ajout du document {filename}",
            )

            project.apply_ontology(version)
            project.ontology = new_onto_dict
            ProjectManager.save_project(project)

            # Application sur le GraphStore (non destructif pour les nœuds existants, AC3/C4)
            if project.graph_id:
                owned = store is None
                st = store if store is not None else store_factory()
                try:
                    st.set_ontology(
                        project.graph_id,
                        version.to_ontology_dict(),
                        strict=project.strict_ontology,
                    )
                finally:
                    if owned:
                        release_graph_store(st)

            return version
