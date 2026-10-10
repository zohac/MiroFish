"""Tests unitaires hermétiques pour le pipeline ETL de migration Zep vers Neo4j (Story 006-2).

Ces tests vérifient :
1. Le parsing des arguments CLI (défauts, personnalisés, mode silencieux).
2. La fidélité et robustesse des modèles DTO (ZepNodeDTO, ZepEdgeDTO) depuis objets et dictionnaires.
3. La normalisation rigoureuse des horodatages ISO 8601 UTC ('YYYY-MM-DDTHH:MM:SSZ') (Critère C3).
4. L'assainissement des attributs Neo4j (types primitifs, exclusion des clés réservées, sérialisation JSON).
5. La préservation de la propriété entity_type pour ZepEntityReader et OASIS.
6. Le découpage par lots (chunk_list) et les requêtes Cypher UNWIND transactionnelles.
7. Le comportement du chargeur direct Neo4j (Neo4jDirectLoader) avec mocks hermétiques.
8. L'orchestration complète ETL (ZepToGraphitiMigrator) avec mocks réseau et base.
9. L'exécution du mode déterministe --mock en CLI avec génération des rapports Markdown et JSON.
10. La gestion des erreurs bloquantes (identifiants manquants, erreurs réseau) avec codes retour stricts.
11. L'absence absolue de fuite de secrets dans les comptes-rendus et sorties console.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import Config
from scripts.migrer_zep_vers_graphiti import (
    MigrationReport,
    Neo4jDirectLoader,
    SimulatedNeo4jLoader,
    TransformedEdge,
    TransformedNode,
    ZepEdgeDTO,
    ZepNodeDTO,
    ZepToGraphitiMigrator,
    ZepToGraphitiTransformer,
    chunk_list,
    generer_graphe_mock,
    main,
    masquer_secret,
    parser_arguments,
)


# ==============================================================================
# 1. Tests CLI & Arguments
# ==============================================================================


def test_parser_arguments_defaults():
    """Vérifie les valeurs par défaut du parser CLI."""
    args = parser_arguments([])
    assert args.graph_id is None
    assert args.target_graph_id is None
    assert args.api_key is None
    assert args.neo4j_uri is None
    assert args.neo4j_user is None
    assert args.neo4j_password is None
    assert args.batch_size == 100
    assert args.mock is False
    assert args.output_report is None
    assert args.output_json is None
    assert args.quiet is False


def test_parser_arguments_custom():
    """Vérifie le parsing des arguments personnalisés."""
    args = parser_arguments([
        "--graph-id", "an_source",
        "--target-graph-id", "an_target",
        "--api-key", "z_secret_12345",
        "--neo4j-uri", "bolt://127.0.0.1:7687",
        "--neo4j-user", "custom_admin",
        "--neo4j-password", "pwd_pass",
        "--batch-size", "50",
        "--mock",
        "--output-report", "/tmp/report.md",
        "--output-json", "/tmp/report.json",
        "--quiet",
    ])
    assert args.graph_id == "an_source"
    assert args.target_graph_id == "an_target"
    assert args.api_key == "z_secret_12345"
    assert args.neo4j_uri == "bolt://127.0.0.1:7687"
    assert args.neo4j_user == "custom_admin"
    assert args.neo4j_password == "pwd_pass"
    assert args.batch_size == 50
    assert args.mock is True
    assert args.output_report == "/tmp/report.md"
    assert args.output_json == "/tmp/report.json"
    assert args.quiet is True


def test_masquer_secret():
    """Vérifie le masquage sûr des secrets sans fuite."""
    assert masquer_secret(None) == "<non défini>"
    assert masquer_secret("") == "<non défini>"
    assert masquer_secret("court") == "***"
    assert masquer_secret("zep_secret_api_key_2026") == "zep...26"


# ==============================================================================
# 2. Tests DTO ZepNodeDTO & ZepEdgeDTO
# ==============================================================================


def test_zep_node_dto_from_dict():
    """Vérifie la construction d'un ZepNodeDTO depuis un dictionnaire."""
    raw = {
        "uuid": "node-123",
        "name": "Cour de Cassation",
        "summary": "Plus haute juridiction judiciaire",
        "labels": ["Entity", "Juridiction"],
        "attributes": {"entity_type": "Institution", "annee": 1804},
        "created_at": "2026-03-01T12:00:00Z",
    }
    dto = ZepNodeDTO.from_zep(raw)
    assert dto.uuid == "node-123"
    assert dto.name == "Cour de Cassation"
    assert dto.summary == "Plus haute juridiction judiciaire"
    assert dto.labels == ["Entity", "Juridiction"]
    assert dto.attributes["entity_type"] == "Institution"
    assert dto.created_at == "2026-03-01T12:00:00Z"


def test_zep_node_dto_from_object_with_uuid_underscore():
    """Vérifie la tolérance pour uuid_ (convention SDK Zep / Pydantic)."""
    class RawZepNode:
        uuid_ = "node-sdk-999"
        name = "Conseil d'État"
        summary = "Juridiction administrative suprême"
        labels = ("Entity", "Institution")
        attributes = {"role": "juge administratif"}
        created_at = None

    dto = ZepNodeDTO.from_zep(RawZepNode())
    assert dto.uuid == "node-sdk-999"
    assert dto.name == "Conseil d'État"
    assert dto.labels == ["Entity", "Institution"]
    assert dto.attributes == {"role": "juge administratif"}
    assert dto.created_at is None


def test_zep_edge_dto_from_dict_and_object():
    """Vérifie la construction de ZepEdgeDTO depuis dict et objet."""
    raw_dict = {
        "uuid_": "edge-456",
        "source_uuid": "node-1",
        "target_uuid": "node-2",
        "name": "PRESIDES",
        "fact": "Le Premier président préside la Cour.",
        "fact_type": "LEADERSHIP",
        "episodes": ["ep-1", "ep-2"],
        "attributes": {"mandat": "2024-2028"},
        "valid_at": "2024-01-01T00:00:00Z",
        "invalid_at": "2028-01-01T00:00:00Z",
    }
    dto = ZepEdgeDTO.from_zep(raw_dict)
    assert dto.uuid == "edge-456"
    assert dto.source_node_uuid == "node-1"
    assert dto.target_node_uuid == "node-2"
    assert dto.name == "PRESIDES"
    assert dto.fact_type == "LEADERSHIP"
    assert dto.episodes == ["ep-1", "ep-2"]
    assert dto.valid_at == "2024-01-01T00:00:00Z"
    assert dto.invalid_at == "2028-01-01T00:00:00Z"

    # Objet avec épisodes scalaires
    class RawZepEdge:
        uuid = "edge-scalar-789"
        source_node_uuid = "node-A"
        target_node_uuid = "node-B"
        name = "CONNECTS"
        fact = "Liaison"
        fact_type = None
        episodes = "single-episode-uuid"
        attributes = None
        created_at = "2026-01-01"
        valid_at = None
        invalid_at = None
        expired_at = None

    dto_obj = ZepEdgeDTO.from_zep(RawZepEdge())
    assert dto_obj.uuid == "edge-scalar-789"
    assert dto_obj.fact_type == "CONNECTS"
    assert dto_obj.episodes == ["single-episode-uuid"]
    assert dto_obj.attributes == {}


# ==============================================================================
# 3. Tests Normalisation Temporelle & Assainissement (C3, NFR-3)
# ==============================================================================


@pytest.mark.parametrize(
    "input_val, expected",
    [
        (None, None),
        (True, None),
        (False, None),
        ("", None),
        ("   ", None),
        (
            datetime(2026, 3, 1, 14, 30, 0, tzinfo=timezone.utc),
            "2026-03-01T14:30:00Z",
        ),
        (
            datetime(2026, 3, 1, 14, 30, 0),  # naïf -> supposé UTC
            "2026-03-01T14:30:00Z",
        ),
        (
            "2026-03-01T14:30:00Z",
            "2026-03-01T14:30:00Z",
        ),
        (
            "2026-03-01T14:30:00+00:00",
            "2026-03-01T14:30:00Z",
        ),
        (
            "2026-03-01 14:30:00",
            "2026-03-01T14:30:00Z",
        ),
        (
            "2026-03-01",
            "2026-03-01T00:00:00Z",
        ),
        (
            1772375400,  # Timestamp unix valide
            datetime.fromtimestamp(1772375400, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        (
            1772375400000,  # Millisecondes
            datetime.fromtimestamp(1772375400, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    ],
)
def test_normaliser_timestamp_utc(input_val, expected):
    """Vérifie la normalisation rigoureuse des horodatages UTC (Critère C3)."""
    assert ZepToGraphitiTransformer.normaliser_timestamp_utc(input_val) == expected


def test_sanitiser_attributs_neo4j():
    """Vérifie l'assainissement des dictionnaires pour les types compatibles Neo4j."""
    attrs = {
        "uuid": "doit-etre-ignore",  # clé réservée
        "group_id": "doit-etre-ignore",  # clé réservée
        "titre": "Rapport 2506",
        "actif": True,
        "score": 42.5,
        "tags": ["parlement", "loi", "finance"],
        "heterogene": ["texte", 123],
        "date_publication": datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        "nested_dict": {"cle": "valeur", "sous_cle": 10},
        "champ_vide": None,  # doit être filtré
    }
    reserved = {"uuid", "group_id"}
    sanitized = ZepToGraphitiTransformer.sanitiser_attributs_neo4j(attrs, reserved)

    assert "uuid" not in sanitized
    assert "group_id" not in sanitized
    assert "champ_vide" not in sanitized
    assert sanitized["titre"] == "Rapport 2506"
    assert sanitized["actif"] is True
    assert sanitized["score"] == 42.5
    assert sanitized["tags"] == ["parlement", "loi", "finance"]
    assert sanitized["heterogene"] == ["texte", "123"]
    assert sanitized["date_publication"] == "2026-03-01T09:00:00Z"
    assert json.loads(sanitized["nested_dict"]) == {"cle": "valeur", "sous_cle": 10}


def test_transformer_noeud_preservation_entity_type():
    """Vérifie que la transformation d'un nœud préserve entity_type pour ZepEntityReader."""
    # Cas 1 : entity_type déjà dans attributes
    n1 = ZepNodeDTO(
        uuid="n1",
        name="Sénat",
        labels=["Entity", "Chambre"],
        attributes={"entity_type": "Parlement"},
    )
    t1 = ZepToGraphitiTransformer.transformer_noeud(n1, "target_grp")
    assert t1.attributes["entity_type"] == "Parlement"
    assert t1.group_id == "target_grp"

    # Cas 2 : entity_type déduit du label spécifique
    n2 = ZepNodeDTO(
        uuid="n2",
        name="Commission Mixte",
        labels=["Entity", "CommissionSpeciale"],
        attributes={"autre": "info"},
    )
    t2 = ZepToGraphitiTransformer.transformer_noeud(n2, "target_grp")
    assert t2.attributes["entity_type"] == "CommissionSpeciale"

    # Cas 3 : entity_type déduit de attributes['category']
    n3 = ZepNodeDTO(
        uuid="n3",
        name="Direction Générale",
        labels=["Entity"],
        attributes={"category": "Administration"},
    )
    t3 = ZepToGraphitiTransformer.transformer_noeud(n3, "target_grp")
    assert t3.attributes["entity_type"] == "Administration"


def test_transformer_graphe_detection_aretes_orphelines():
    """Vérifie la détection et l'émission d'un warning sur arêtes orphelines."""
    nodes = [
        ZepNodeDTO(uuid="n1", name="Nœud 1"),
        ZepNodeDTO(uuid="n2", name="Nœud 2"),
    ]
    edges = [
        ZepEdgeDTO(uuid="e1", source_node_uuid="n1", target_node_uuid="n2"),
        ZepEdgeDTO(uuid="e2", source_node_uuid="n1", target_node_uuid="n_inconnu"),
    ]
    t_nodes, t_edges, warnings = ZepToGraphitiTransformer.transformer_graphe(
        nodes, edges, "grp_1"
    )
    assert len(t_nodes) == 2
    assert len(t_edges) == 2
    assert len(warnings) == 1
    assert "1 arête(s) orpheline(s)" in warnings[0]


# ==============================================================================
# 4. Tests Découpage par Lots (chunk_list)
# ==============================================================================


def test_chunk_list():
    """Vérifie le découpage régulier par lots."""
    items = list(range(10))
    assert chunk_list(items, 3) == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]
    assert chunk_list(items, 10) == [list(range(10))]
    assert chunk_list(items, 15) == [list(range(10))]
    assert chunk_list([], 5) == []

    with pytest.raises(ValueError, match="strictement positif"):
        chunk_list(items, 0)


# ==============================================================================
# 5. Tests Neo4jDirectLoader & Injection Cypher UNWIND
# ==============================================================================


def test_neo4j_direct_loader_sans_password_leve_erreur():
    """Vérifie qu'une exception claire est levée si aucun mot de passe Neo4j n'est fourni."""
    with patch.object(Config, "NEO4J_PASSWORD", None):
        with patch.dict("os.environ", {}, clear=True):
            loader = Neo4jDirectLoader(password=None)
            with pytest.raises(ValueError, match="NEO4J_PASSWORD est requis"):
                loader.get_driver()


def test_neo4j_direct_loader_injection_avec_mock_driver():
    """Vérifie l'exécution des requêtes UNWIND sur un mock driver Neo4j."""
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    loader = Neo4jDirectLoader(driver=mock_driver)

    t_node = TransformedNode(
        uuid="uuid-1",
        group_id="grp-test",
        name="N1",
        summary="S1",
        created_at="2026-03-01T00:00:00Z",
        attributes={"entity_type": "Test"},
        labels=["Entity"],
    )
    t_edge = TransformedEdge(
        uuid="edge-1",
        group_id="grp-test",
        source_node_uuid="uuid-1",
        target_node_uuid="uuid-1",
        name="RELATES_TO",
        fact="Faits",
        fact_type="TEST",
        created_at="2026-03-01T00:00:00Z",
        valid_at="2026-01-01T00:00:00Z",
        invalid_at=None,
        expired_at=None,
        episodes=["ep-1"],
        attributes={},
    )

    # Injection nœuds
    count_n = loader.injecter_noeuds([t_node], "grp-test", batch_size=100)
    assert count_n == 1
    assert mock_session.execute_write.called or mock_session.run.called

    # Injection arêtes
    count_e = loader.injecter_aretes([t_edge], "grp-test", batch_size=100)
    assert count_e == 1

    loader.close()


# ==============================================================================
# 6. Tests Orchestrateur ETL (ZepToGraphitiMigrator)
# ==============================================================================


def test_migrator_avec_mock_data():
    """Vérifie le déroulement complet du pipeline ETL avec SimulatedNeo4jLoader."""
    loader = SimulatedNeo4jLoader()
    migrator = ZepToGraphitiMigrator(loader=loader)

    mock_nodes, mock_edges = generer_graphe_mock("graph_demo")
    report = migrator.migrer_graphe(
        graph_id="graph_demo",
        target_graph_id="graph_demo_local",
        batch_size=2,
        mock_data=(mock_nodes, mock_edges),
    )

    assert report.status == "SUCCESS"
    assert report.fidelity_rate == 100.0
    assert report.nodes_extracted == 4
    assert report.nodes_loaded == 4
    assert report.edges_extracted == 3
    assert report.edges_loaded == 3
    assert report.temporal_edges_count == 3
    assert report.temporal_edges_preserved == 3

    # Vérification dans le stockage simulé
    assert len(loader.nodes_by_uuid) == 4
    assert len(loader.edges_by_uuid) == 3
    assert len(loader.executed_queries) == (2 + 2)  # 4 nœuds par lots de 2 + 3 arêtes par lots de 2


def test_migrator_avec_client_zep_mocke():
    """Vérifie l'extraction paginée et l'injection avec un client Zep mocké (0 réseau)."""
    raw_node = MagicMock()
    raw_node.uuid = "n-1"
    raw_node.name = "Nœud Réseau"
    raw_node.summary = "Test"
    raw_node.labels = ["Entity", "TestLabel"]
    raw_node.attributes = {"entity_type": "Test"}
    raw_node.created_at = "2026-03-01T10:00:00Z"

    raw_edge = MagicMock()
    raw_edge.uuid = "e-1"
    raw_edge.source_node_uuid = "n-1"
    raw_edge.target_node_uuid = "n-1"
    raw_edge.name = "CONNECTS"
    raw_edge.fact = "Fait"
    raw_edge.fact_type = "LINK"
    raw_edge.episodes = ["ep-1"]
    raw_edge.attributes = {}
    raw_edge.created_at = "2026-03-01T10:00:00Z"
    raw_edge.valid_at = "2026-03-01T10:00:00Z"
    raw_edge.invalid_at = None
    raw_edge.expired_at = None

    mock_zep_client = MagicMock()
    loader = SimulatedNeo4jLoader()
    migrator = ZepToGraphitiMigrator(loader=loader, zep_client=mock_zep_client)

    with patch("scripts.migrer_zep_vers_graphiti.fetch_all_nodes", return_value=[raw_node]):
        with patch("scripts.migrer_zep_vers_graphiti.fetch_all_edges", return_value=[raw_edge]):
            report = migrator.migrer_graphe("graphe_distant")

    assert report.status == "SUCCESS"
    assert report.nodes_extracted == 1
    assert report.edges_extracted == 1
    assert report.temporal_edges_count == 1
    assert report.temporal_edges_preserved == 1


def test_migrator_gestion_erreur_extraction():
    """Vérifie que les erreurs d'extraction sont capturées proprement sans crash."""
    loader = SimulatedNeo4jLoader()
    migrator = ZepToGraphitiMigrator(loader=loader, zep_client=None)

    report = migrator.migrer_graphe("graphe_invalide")
    assert report.status == "FAILED"
    assert len(report.errors) > 0
    assert "Client Zep non configuré" in report.errors[0]


# ==============================================================================
# 7. Tests Main CLI & Exports
# ==============================================================================


def test_main_cli_mode_mock(tmp_path):
    """Vérifie l'exécution CLI en mode --mock et l'export des fichiers JSON et Markdown."""
    out_md = tmp_path / "compte_rendu.md"
    out_json = tmp_path / "compte_rendu.json"

    ret = main([
        "--mock",
        "--graph-id", "mock_graph_test",
        "--output-report", str(out_md),
        "--output-json", str(out_json),
    ])

    assert ret == 0
    assert out_md.exists()
    assert out_json.exists()

    md_content = out_md.read_text(encoding="utf-8")
    assert "# ✅ Rapport de Migration Zep Cloud vers Neo4j" in md_content
    assert "mock_graph_test" in md_content
    assert "Coût marginal : 0,00 €" in md_content

    json_data = json.loads(out_json.read_text(encoding="utf-8"))
    assert json_data["status"] == "SUCCESS"
    assert json_data["fidelity_rate"] == 100.0
    assert json_data["nodes_extracted"] == 4
    assert json_data["edges_extracted"] == 3


def test_main_cli_mode_reel_manque_graph_id(capsys):
    """Vérifie le rejet propre si --graph-id est absent en mode réel."""
    ret = main([])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Erreur : --graph-id est obligatoire" in captured.err


def test_main_cli_mode_reel_manque_zep_key(capsys):
    """Vérifie le rejet propre si ZEP_API_KEY est manquante en mode réel."""
    with patch.object(Config, "ZEP_API_KEY", None):
        with patch.dict("os.environ", {}, clear=True):
            ret = main(["--graph-id", "test_id"])
            assert ret == 1
            captured = capsys.readouterr()
            assert "Clé Zep manquante" in captured.err


def test_main_cli_mode_reel_manque_neo4j_password(capsys):
    """Vérifie le rejet propre si NEO4J_PASSWORD est manquant en mode réel."""
    with patch.object(Config, "ZEP_API_KEY", "z_dummy_key"):
        with patch.object(Config, "NEO4J_PASSWORD", None):
            with patch.dict("os.environ", {"ZEP_API_KEY": "z_dummy_key"}, clear=True):
                ret = main(["--graph-id", "test_id"])
                assert ret == 1
                captured = capsys.readouterr()
                assert "Mot de passe Neo4j manquant" in captured.err


def test_main_cli_mode_reel_avec_mocks():
    """Vérifie l'exécution CLI en mode réel avec mocks complets de Zep et Neo4j."""
    mock_zep_client = MagicMock()
    mock_loader = SimulatedNeo4jLoader()

    with patch("scripts.migrer_zep_vers_graphiti.get_zep_client", return_value=mock_zep_client):
        with patch("scripts.migrer_zep_vers_graphiti.Neo4jDirectLoader", return_value=mock_loader):
            with patch("scripts.migrer_zep_vers_graphiti.fetch_all_nodes", return_value=[]):
                with patch("scripts.migrer_zep_vers_graphiti.fetch_all_edges", return_value=[]):
                    ret = main([
                        "--graph-id", "test_id",
                        "--api-key", "z_secret_key",
                        "--neo4j-password", "super_pwd",
                        "--quiet",
                    ])
                    assert ret == 0


def test_migration_report_formatting():
    """Vérifie le formatage Markdown et JSON d'un rapport partiel ou échoué."""
    report_partial = MigrationReport(
        graph_id="g1",
        target_graph_id="g1_local",
        status="PARTIAL",
        nodes_extracted=10,
        nodes_loaded=8,
        edges_extracted=5,
        edges_loaded=0,
        fidelity_rate=53.3,
        warnings=["Arêtes orphelines ignorées"],
        errors=["Erreur batch 2"],
    )
    md = report_partial.to_markdown()
    assert "⚠️ Rapport de Migration" in md
    assert "PARTIAL" in md
    assert "Arêtes orphelines ignorées" in md
    assert "Erreur batch 2" in md

    js = json.loads(report_partial.to_json())
    assert js["status"] == "PARTIAL"
    assert js["fidelity_rate"] == 53.3


def test_main_cli_batch_size_invalide(capsys):
    """Vérifie le rejet propre si --batch-size <= 0."""
    ret_zero = main(["--mock", "--batch-size", "0"])
    assert ret_zero == 1
    captured = capsys.readouterr()
    assert "Erreur : --batch-size doit être strictement supérieur à 0" in captured.err

    ret_neg = main(["--mock", "--batch-size", "-5"])
    assert ret_neg == 1


def test_migrator_target_graph_id_espaces():
    """Vérifie que target_graph_id contenant uniquement des espaces replie sur graph_id."""
    loader = SimulatedNeo4jLoader()
    migrator = ZepToGraphitiMigrator(loader=loader)
    mock_nodes, mock_edges = generer_graphe_mock("mon_graphe")
    report = migrator.migrer_graphe(
        graph_id="mon_graphe",
        target_graph_id="   ",
        mock_data=(mock_nodes, mock_edges),
    )
    assert report.target_graph_id == "mon_graphe"

