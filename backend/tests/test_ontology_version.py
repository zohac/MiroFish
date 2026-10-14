"""Tests unitaires hermétiques pour OntologyVersion et OntologyVersionStore (story 007-4, AC1, AC2)."""

import json
import os
import pytest
from dataclasses import FrozenInstanceError

from app.config import Config
from app.models.ontology_version import (
    OntologyEdgeType,
    OntologyEntityType,
    OntologyVersion,
    OntologyVersionStore,
)
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.source_document import InformationOrigin


@pytest.fixture(autouse=True)
def isolated_upload_folder(tmp_path, monkeypatch):
    """Isole le dossier UPLOAD_FOLDER pour éviter tout résidu de test."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_dir / "projects"))
    yield upload_dir


class TestOntologyVersionModels:
    def test_entity_type_immutability_and_validation(self):
        et = OntologyEntityType(
            name="PersonEntity",
            description="Personne physique",
            attributes=("name", "role"),
            source=InformationOrigin.DOCUMENTARY,
        )
        assert et.name == "PersonEntity"
        assert et.attributes == ("name", "role")
        assert et.source == InformationOrigin.DOCUMENTARY

        with pytest.raises(FrozenInstanceError):
            et.name = "Other"

        # Nom invalide
        with pytest.raises(ValueError, match="Nom de type d'entité invalide"):
            OntologyEntityType(name="Invalid Name with spaces")

        with pytest.raises(ValueError, match="ne peut pas être vide"):
            OntologyEntityType(name="")

    def test_edge_type_immutability_and_validation(self):
        edge = OntologyEdgeType(
            name="WORKS_FOR",
            source_types=("PersonEntity",),
            target_types=("MediaOrganization",),
            description="Relation d'emploi",
        )
        assert edge.name == "WORKS_FOR"
        assert edge.source_types == ("PersonEntity",)
        assert edge.target_types == ("MediaOrganization",)

        with pytest.raises(FrozenInstanceError):
            edge.name = "OTHER"

        with pytest.raises(ValueError, match="Nom de type de relation invalide"):
            OntologyEdgeType(name="Bad-Name-With-Dashes")

    def test_ontology_version_validation_and_json_roundtrip(self):
        vid = OntologyVersion.generate_version_id()
        assert vid.startswith("ont_")

        et = OntologyEntityType(name="PersonEntity", attributes=("name",))
        edge = OntologyEdgeType(name="KNOWS", source_types=("PersonEntity",), target_types=("PersonEntity",))

        version = OntologyVersion(
            version_id=vid,
            project_id="proj_123",
            entity_types=(et,),
            edge_types=(edge,),
            created_at="2026-10-14T10:00:00Z",
            source_summary="Test round-trip",
            parent_version_id=None,
        )

        d = version.to_dict()
        reconstructed = OntologyVersion.from_dict(d)
        assert reconstructed.version_id == version.version_id
        assert reconstructed.project_id == version.project_id
        assert len(reconstructed.entity_types) == 1
        assert reconstructed.entity_types[0].name == "PersonEntity"
        assert reconstructed.edge_types[0].name == "KNOWS"
        assert reconstructed.created_at == version.created_at

    def test_ontology_version_ceiling_entities(self):
        entities = tuple(
            OntologyEntityType(name=f"Entity_{i}") for i in range(11)
        )
        with pytest.raises(ValueError, match="plafond autorisé"):
            OntologyVersion(
                version_id="ont_123456789012",
                project_id="proj_1",
                entity_types=entities,
                edge_types=(),
                created_at="2026-10-14T10:00:00Z",
            )


class TestOntologyVersionStore:
    def test_store_create_get_list(self):
        project_id = "proj_test_store"
        onto_dict = {
            "entity_types": [
                {"name": "Citizen", "description": "Citoyen", "attributes": ["age"]},
                {"name": "Organization", "description": "Organisation"},
            ],
            "edge_types": [
                {"name": "MEMBER_OF", "source_types": ["Citizen"], "target_types": ["Organization"]},
            ],
        }

        v1 = OntologyVersionStore.create(
            project_id=project_id,
            ontology_dict=onto_dict,
            parent_version_id=None,
            source_summary="Version initiale",
        )
        assert v1.version_id.startswith("ont_")
        assert len(v1.entity_types) == 2
        assert len(v1.edge_types) == 1

        # Relecture directe
        loaded = OntologyVersionStore.get(v1.version_id)
        assert loaded is not None
        assert loaded.version_id == v1.version_id
        assert loaded.project_id == project_id
        assert loaded.entity_types[0].name == "Citizen"

        # Version fille
        v2 = OntologyVersionStore.create(
            project_id=project_id,
            ontology_dict=onto_dict,
            parent_version_id=v1.version_id,
            source_summary="Version 2",
        )
        assert v2.parent_version_id == v1.version_id

        # Listing pour le projet
        versions = OntologyVersionStore.list_for_project(project_id)
        assert len(versions) == 2
        assert [v.version_id for v in versions] == [v1.version_id, v2.version_id]

    def test_get_nonexistent_or_invalid_version(self):
        assert OntologyVersionStore.get("ont_notfound") is None
        assert OntologyVersionStore.get("invalid/path/traversal") is None


class TestProjectOntologyExtension:
    def test_project_apply_ontology_monotonic(self):
        project = Project(
            project_id="proj_test_proj",
            name="Test Project",
            status=ProjectStatus.CREATED,
            created_at="2026-10-14T10:00:00Z",
            updated_at="2026-10-14T10:00:00Z",
        )
        assert project.applied_ontology_id is None
        assert project.applied_ontology_version == 0
        assert project.ontology_history == []

        # Version 1
        v1 = OntologyVersionStore.create(
            project_id=project.project_id,
            ontology_dict={"entity_types": [{"name": "TypeA"}]},
        )
        project.apply_ontology(v1)
        assert project.applied_ontology_id == v1.version_id
        assert project.applied_ontology_version == 1
        assert project.ontology_history == [v1.version_id]

        # Relecture via get_applied_ontology
        applied = project.get_applied_ontology()
        assert applied is not None
        assert applied.version_id == v1.version_id

        # Version 2
        v2 = OntologyVersionStore.create(
            project_id=project.project_id,
            ontology_dict={"entity_types": [{"name": "TypeA"}, {"name": "TypeB"}]},
            parent_version_id=v1.version_id,
        )
        project.apply_ontology(v2)
        assert project.applied_ontology_id == v2.version_id
        assert project.applied_ontology_version == 2
        assert project.ontology_history == [v1.version_id, v2.version_id]

    def test_project_to_dict_from_dict_retrocompatibility(self):
        raw_legacy = {
            "project_id": "proj_legacy",
            "name": "Legacy Project",
            "status": "created",
            "created_at": "2026-10-10T10:00:00Z",
            "updated_at": "2026-10-10T10:00:00Z",
            "files": [],
        }
        project = Project.from_dict(raw_legacy)
        assert project.applied_ontology_id is None
        assert project.applied_ontology_version == 0
        assert project.ontology_history == []

        # Sérialisation et désérialisation
        d = project.to_dict()
        assert d["applied_ontology_id"] is None
        assert d["applied_ontology_version"] == 0
        assert d["ontology_history"] == []

    def test_project_apply_ontology_rejects_invalid_id(self):
        project = Project(
            project_id="proj_invalid_id",
            name="Invalid ID Project",
            status=ProjectStatus.CREATED,
            created_at="2026-10-14T10:00:00Z",
            updated_at="2026-10-14T10:00:00Z",
        )
        with pytest.raises(ValueError, match="doit commencer par 'ont_'"):
            project.apply_ontology("bad_prefix_12345")

    def test_ontology_version_store_index_resilience(self, monkeypatch):
        # Index corrompu ou vide géré avec résilience
        project_id = "proj_corrupt_index"
        onto_dict = {"entity_types": [{"name": "TypeX"}]}
        
        index_path = OntologyVersionStore.get_index_path()
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json")
            
        # create doit recréer un index propre sans planter
        v = OntologyVersionStore.create(project_id, onto_dict)
        assert v.version_id.startswith("ont_")
        listed = OntologyVersionStore.list_for_project(project_id)
        assert len(listed) == 1
        assert listed[0].version_id == v.version_id

    def test_ontology_version_to_ontology_dict(self):
        v = OntologyVersion(
            version_id="ont_test_dict_1",
            project_id="proj_dict",
            entity_types=(OntologyEntityType(name="E1", attributes=("a",)),),
            edge_types=(OntologyEdgeType(name="R1", source_types=("E1",), target_types=("E1",)),),
            created_at="2026-10-14T10:00:00Z",
        )
        onto_dict = v.to_ontology_dict()
        assert "entity_types" in onto_dict
        assert "edge_types" in onto_dict
        assert onto_dict["entity_types"][0]["name"] == "E1"
        assert onto_dict["edge_types"][0]["name"] == "R1"
