"""Tests unitaires hermétiques pour l'outil d'audit Zep Cloud (Story 006-1).

Ces tests vérifient :
1. L'exécution complète du mode mock CLI et la structure du rapport d'audit.
2. L'export des rapports au format JSON normalisé et Markdown récapitulatif.
3. Le respect du mode silencieux (--quiet).
4. La gestion sécurisée et l'arrêt propre sur clé ZEP_API_KEY manquante.
5. L'application exacte de l'arbre de décision d'arbitrage (« Migrer vs Jeter vs Purger »).
6. La détection heuristique des documents locaux dans uploads/documents/.
7. L'extraction paginée et l'agrégation avec un client Zep mocké (0 appel réseau).
8. La gestion robuste des erreurs d'authentification (401) et de limitation (429).
9. L'absence absolue de fuite de la clé secrète dans les logs, sorties et exports.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from zep_cloud.core.api_error import ApiError as ZepApiError

from app.config import Config
from scripts.auditer_graphes_zep import (
    ACTION_MIGRATE,
    ACTION_PURGE,
    ACTION_REBUILD_LOCAL,
    LABEL_MIGRATE,
    LABEL_PURGE,
    LABEL_REBUILD_LOCAL,
    AuditReport,
    GraphSummary,
    auditer_compte_zep,
    detecter_documents_locaux,
    determiner_arbitrage,
    main,
    parser_arguments,
)


class DummyGraph:
    """Mock léger représentant un Graph Zep Cloud."""

    def __init__(
        self,
        graph_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> None:
        self.graph_id = graph_id
        self.name = name
        self.description = description
        self.created_at = created_at


class DummyGraphListResponse:
    """Mock représentant une page de réponse client.graph.list_all."""

    def __init__(self, graphs: list[DummyGraph]) -> None:
        self.graphs = graphs
        self.row_count = len(graphs)
        self.total_count = len(graphs)


class DummyEpisode:
    """Mock léger représentant un Episode Zep Cloud."""

    def __init__(self, source_description: str = "") -> None:
        self.source_description = source_description


class DummyEpisodeResponse:
    """Mock représentant la réponse client.graph.episode.get_by_graph_id."""

    def __init__(self, episodes: list[DummyEpisode]) -> None:
        self.episodes = episodes


def test_parser_arguments_defaults():
    """Vérifie le parsing des arguments CLI par défaut."""
    args = parser_arguments([])
    assert args.api_key is None
    assert args.output_json is None
    assert args.output_report is None
    assert args.uploads_dir is None
    assert args.mock is False
    assert args.quiet is False


def test_parser_arguments_custom():
    """Vérifie le parsing des arguments CLI personnalisés."""
    args = parser_arguments([
        "--api-key", "z_custom_key",
        "--output-json", "/tmp/out.json",
        "--output-report", "/tmp/out.md",
        "--uploads-dir", "/tmp/uploads",
        "--mock",
        "--quiet",
    ])
    assert args.api_key == "z_custom_key"
    assert args.output_json == "/tmp/out.json"
    assert args.output_report == "/tmp/out.md"
    assert args.uploads_dir == "/tmp/uploads"
    assert args.mock is True
    assert args.quiet is True


def test_audit_cli_mock_mode(capsys):
    """Vérifie l'exécution complète en mode mock et l'intégrité des métriques."""
    ret = main(["--mock"])
    assert ret == 0

    captured = capsys.readouterr()
    assert "MiroFish — Audit et Inventaire de Compte Zep Cloud" in captured.out
    assert "Total Graphes    : 3" in captured.out
    assert "Total Nœuds      : 131" in captured.out
    assert "Total Arêtes     : 159" in captured.out
    assert "Total Épisodes   : 80" in captured.out
    assert "Jeter / Re-ingérer en local (0 €) [REBUILD_LOCAL]: 1" in captured.out
    assert "Migrer vers Neo4j local (ETL) [MIGRATE]: 1" in captured.out
    assert "Purger le graphe distant [PURGE]: 1" in captured.out


def test_audit_output_json_and_markdown_files(tmp_path):
    """Vérifie l'export sur disque des rapports JSON et Markdown."""
    json_path = tmp_path / "audit.json"
    report_path = tmp_path / "audit.md"

    ret = main([
        "--mock",
        "--output-json", str(json_path),
        "--output-report", str(report_path),
        "--quiet",
    ])
    assert ret == 0
    assert json_path.exists()
    assert report_path.exists()

    # Vérification du JSON
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["total_graphs"] == 3
    assert data["total_nodes"] == 131
    assert data["total_edges"] == 159
    assert data["total_episodes"] == 80
    assert data["recommendations_breakdown"][ACTION_REBUILD_LOCAL] == 1
    assert data["recommendations_breakdown"][ACTION_MIGRATE] == 1
    assert data["recommendations_breakdown"][ACTION_PURGE] == 1
    assert len(data["graphs"]) == 3

    # Vérification du Markdown
    md_content = report_path.read_text(encoding="utf-8")
    assert "# Rapport d'audit Zep Cloud" in md_content
    assert "| **Jeter / Re-ingérer en local (0 €)** (`REBUILD_LOCAL`) | 1 |" in md_content
    assert "| `mirofish_rapport_an_2506` |" in md_content
    assert "| `mirofish_strategie_ia_2024` |" in md_content
    assert "| `test_sandbox_ephemeral_dev` |" in md_content


def test_audit_quiet_mode(capsys):
    """Vérifie que l'option --quiet n'imprime aucune ligne sur stdout."""
    ret = main(["--mock", "--quiet"])
    assert ret == 0

    captured = capsys.readouterr()
    assert captured.out == ""


def test_audit_missing_api_key_exits_with_error(monkeypatch, capsys):
    """Vérifie qu'un appel sans clé et sans mock produit un code retour 1 explicite."""
    monkeypatch.delenv("ZEP_API_KEY", raising=False)
    monkeypatch.setattr(Config, "ZEP_API_KEY", "")

    ret = main([])
    assert ret == 1

    captured = capsys.readouterr()
    assert "Erreur lors de l'audit Zep Cloud" in captured.err
    assert "Clé ZEP_API_KEY non configurée" in captured.err


def test_audit_arbitrage_decision_tree():
    """Valide les règles de l'arbre de décision « Migrer vs Jeter vs Purger »."""
    # 1. Graphe vide -> PURGE
    action, label, reason = determiner_arbitrage(
        graph_id="g1",
        name="Graphe Inutilisé",
        node_count=0,
        edge_count=0,
        has_local_documents=False,
        local_document_matches=[],
    )
    assert action == ACTION_PURGE
    assert label == LABEL_PURGE
    assert "Graphe vide" in reason

    # 1b. Graphe de test éphémère avec très peu de nœuds -> PURGE
    action, label, reason = determiner_arbitrage(
        graph_id="test_ingest_temp",
        name="Test Ingest",
        node_count=1,
        edge_count=0,
        has_local_documents=False,
        local_document_matches=[],
    )
    assert action == ACTION_PURGE

    # 2. Graphe avec documents sources locaux disponibles -> REBUILD_LOCAL
    action, label, reason = determiner_arbitrage(
        graph_id="g2",
        name="Transition Énergétique",
        node_count=50,
        edge_count=40,
        has_local_documents=True,
        local_document_matches=["rapport-an-2506.pdf"],
    )
    assert action == ACTION_REBUILD_LOCAL
    assert label == LABEL_REBUILD_LOCAL
    assert "0 €" in reason
    assert "rapport-an-2506.pdf" in reason

    # 3. Graphe orphelin (sans documents sources locaux) -> MIGRATE
    action, label, reason = determiner_arbitrage(
        graph_id="g3",
        name="Défense Nationale",
        node_count=120,
        edge_count=200,
        has_local_documents=False,
        local_document_matches=[],
    )
    assert action == ACTION_MIGRATE
    assert label == LABEL_MIGRATE
    assert "migrer_zep_vers_graphiti.py" in reason


def test_audit_detection_documents_locaux(tmp_path):
    """Vérifie la détection heuristique des documents locaux dans uploads/documents."""
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir(parents=True)

    # Création de faux documents
    doc1 = docs_dir / "rapport-an-2506-territorialisation.pdf"
    doc1.write_text("dummy", encoding="utf-8")
    doc2 = docs_dir / "strategie_maritime.pdf"
    doc2.write_text("dummy", encoding="utf-8")

    # Match par stem / nom dans graph_id
    has_match, matches = detecter_documents_locaux(
        graph_id="mirofish_rapport_an_2506",
        graph_name="Territorialisation",
        uploads_dir=docs_dir,
    )
    assert has_match is True
    assert "rapport-an-2506-territorialisation.pdf" in matches

    # Match via description d'épisode
    has_match, matches = detecter_documents_locaux(
        graph_id="autre_graphe",
        graph_name="Autre",
        episodes_descriptions=["Extrait du document strategie_maritime.pdf page 12"],
        uploads_dir=docs_dir,
    )
    assert has_match is True
    assert "strategie_maritime.pdf" in matches

    # Aucun match
    has_match, matches = detecter_documents_locaux(
        graph_id="graphe_inconnu",
        graph_name="Projet Inconnu",
        episodes_descriptions=[],
        uploads_dir=docs_dir,
    )
    assert has_match is False
    assert matches == []

    # Dossier inexistant
    has_match, matches = detecter_documents_locaux(
        graph_id="g1",
        graph_name="n1",
        uploads_dir=tmp_path / "dossier_fantome",
    )
    assert has_match is False
    assert matches == []


def test_audit_with_mocked_zep_client(tmp_path):
    """Vérifie l'audit complet avec un mock du client Zep Cloud (pagination 2 pages et comptages)."""
    mock_client = MagicMock()

    # Pagination réelle sur 2 pages : page 1 (100 graphes) + page 2 (1 graphe)
    page1_graphs = [
        DummyGraph(f"graph_{i}", f"Graphe {i}", f"Desc {i}", "2026-09-01T10:00:00Z")
        for i in range(100)
    ]
    page2_graphs = [
        DummyGraph("graph_100", "Cent-unième Graphe", "Desc 100", "2026-09-02T10:00:00Z"),
    ]

    mock_client.graph.list_all.side_effect = [
        DummyGraphListResponse(page1_graphs),
        DummyGraphListResponse(page2_graphs),
    ]

    # Mock fetch_all_nodes et fetch_all_edges
    mock_nodes = [MagicMock(uuid="n1"), MagicMock(uuid="n2"), MagicMock(uuid="n3")]
    mock_edges = [MagicMock(uuid="e1"), MagicMock(uuid="e2")]

    # Mock épisodes
    mock_client.graph.episode.get_by_graph_id.return_value = DummyEpisodeResponse([
        DummyEpisode("source document test"),
    ])

    with (
        patch("scripts.auditer_graphes_zep.fetch_all_nodes", return_value=mock_nodes),
        patch("scripts.auditer_graphes_zep.fetch_all_edges", return_value=mock_edges),
    ):
        report = auditer_compte_zep(
            client=mock_client,
            mock=False,
            uploads_dir=tmp_path,
        )

    assert mock_client.graph.list_all.call_count == 2
    assert report.total_graphs == 101
    assert report.total_nodes == 101 * 3
    assert report.total_edges == 101 * 2
    assert report.total_episodes == 101
    g = report.graphs[0]
    assert g.graph_id == "graph_0"
    assert g.node_count == 3
    assert g.edge_count == 2
    assert g.episode_count == 1
    assert g.has_error is False
    assert g.recommendation == ACTION_MIGRATE


def test_audit_handles_zep_401_unauthorized(capsys):
    """Vérifie qu'une erreur 401 d'authentification est capturée proprement."""
    mock_client = MagicMock()
    mock_client.graph.list_all.side_effect = ZepApiError(
        status_code=401,
        headers={},
        body="Unauthorized: Invalid API Key",
    )

    with patch("scripts.auditer_graphes_zep.get_zep_client", return_value=mock_client):
        ret = main(["--api-key", "cle_invalide_401"])

    assert ret == 1
    captured = capsys.readouterr()
    assert "Erreur lors de l'audit Zep Cloud" in captured.err


def test_audit_handles_zep_429_rate_limit(capsys):
    """Vérifie la gestion d'une erreur 429 de limitation de débit."""
    mock_client = MagicMock()
    mock_client.graph.list_all.side_effect = ZepApiError(
        status_code=429,
        headers={"retry-after": "5"},
        body="Too Many Requests",
    )

    with (
        patch("scripts.auditer_graphes_zep.get_zep_client", return_value=mock_client),
        patch("scripts.auditer_graphes_zep.call_zep_read_with_retry", side_effect=ZepApiError(status_code=429, headers={}, body="Rate limited")),
    ):
        ret = main(["--api-key", "cle_valide_mais_429"])

    assert ret == 1
    captured = capsys.readouterr()
    assert "Erreur lors de l'audit Zep Cloud" in captured.err


def test_audit_never_leaks_api_key(capsys, tmp_path):
    """Garantit qu'aucun jeton d'API ne fuite dans les sorties ou fichiers générés."""
    secret_key = "zep_secret_ultra_confidentiel_xyz123"
    json_path = tmp_path / "audit_secret.json"
    report_path = tmp_path / "audit_secret.md"

    # Test avec échec d'authentification
    mock_client = MagicMock()
    mock_client.graph.list_all.side_effect = Exception("Erreur de connexion sécurisée")

    with patch("scripts.auditer_graphes_zep.get_zep_client", return_value=mock_client):
        ret = main([
            "--api-key", secret_key,
            "--output-json", str(json_path),
            "--output-report", str(report_path),
        ])

    assert ret == 1
    captured = capsys.readouterr()
    assert secret_key not in captured.out
    assert secret_key not in captured.err

    # Vérification dans les fichiers générés en mode mock
    main([
        "--mock",
        "--api-key", secret_key,
        "--output-json", str(json_path),
        "--output-report", str(report_path),
        "--quiet",
    ])
    assert secret_key not in json_path.read_text(encoding="utf-8")
    assert secret_key not in report_path.read_text(encoding="utf-8")


def test_audit_report_empty_graphs():
    """Vérifie le formatage Markdown et JSON d'un rapport sans graphes."""
    empty_report = AuditReport(
        timestamp="2026-10-10T00:00:00Z",
        total_graphs=0,
        total_nodes=0,
        total_edges=0,
        total_episodes=0,
        graphs=[],
        recommendations_breakdown={},
    )
    md = empty_report.to_markdown()
    assert "Aucun graphe recensé sur ce compte Zep Cloud" in md
    json_dict = empty_report.to_dict()
    assert json_dict["total_graphs"] == 0
    assert json_dict["graphs"] == []


def test_audit_partial_error_prevents_purge(tmp_path):
    """Garantit qu'une erreur de lecture de nœuds ou arêtes ne conduit JAMAIS à une purge erronée."""
    mock_client = MagicMock()
    mock_client.graph.list_all.return_value = DummyGraphListResponse([
        DummyGraph("graph_err", "Graphe Important en Panne"),
    ])
    mock_client.graph.episode.get_by_graph_id.return_value = DummyEpisodeResponse([])

    # Simulation d'un échec réseau ou 500 sur fetch_all_nodes
    with (
        patch("scripts.auditer_graphes_zep.fetch_all_nodes", side_effect=RuntimeError("500 Zep Backend Failure")),
        patch("scripts.auditer_graphes_zep.fetch_all_edges", return_value=[]),
    ):
        report = auditer_compte_zep(
            client=mock_client,
            mock=False,
            uploads_dir=tmp_path,
        )

    g = report.graphs[0]
    assert g.has_error is True
    assert "500 Zep Backend Failure" in (g.error_message or "")
    assert g.node_count == 0
    # Sécurité : la recommandation DOIT être MIGRATE et JAMAIS PURGE
    assert g.recommendation == ACTION_MIGRATE
    assert "Purge proscrite par précaution" in g.recommendation_reason


def test_audit_ephemeral_detection_word_boundaries():
    """Vérifie que des mots normaux contenant 'test' ou 'tmp' ne sont pas pris pour des artefacts éphémères."""
    # 1. Mots contenant les sous-chaînes mais légitimes -> NON éphémère -> MIGRATE
    action, _, _ = determiner_arbitrage(
        graph_id="latest_release",
        name="Contest Benchmark",
        node_count=1,
        edge_count=0,
        has_local_documents=False,
        local_document_matches=[],
    )
    assert action == ACTION_MIGRATE

    action2, _, _ = determiner_arbitrage(
        graph_id="attestation_fiscale",
        name="Template Document",
        node_count=1,
        edge_count=0,
        has_local_documents=False,
        local_document_matches=[],
    )
    assert action2 == ACTION_MIGRATE

    # 2. Vrais artefacts éphémères avec délimiteurs -> PURGE
    action_purge, _, reason_purge = determiner_arbitrage(
        graph_id="sandbox_dev",
        name="Test Sandbox Rapide",
        node_count=1,
        edge_count=0,
        has_local_documents=False,
        local_document_matches=[],
    )
    assert action_purge == ACTION_PURGE
    assert "artefact de test éphémère" in reason_purge


def test_audit_normalization_handles_accents(tmp_path):
    """Vérifie que normaliser() gère les diacritiques français sans corrompre les mots."""
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir(parents=True)
    doc_fr = docs_dir / "strategie_energetique_regionale.pdf"
    doc_fr.write_text("contenu", encoding="utf-8")

    has_match, matches = detecter_documents_locaux(
        graph_id="graphe_energie",
        graph_name="Stratégie Énergétique Régionale",
        uploads_dir=docs_dir,
    )
    assert has_match is True
    assert "strategie_energetique_regionale.pdf" in matches


def test_audit_api_key_cli_takes_precedence_over_config(monkeypatch):
    """Vérifie que l'option CLI --api-key a la priorité sur Config.ZEP_API_KEY."""
    monkeypatch.setattr(Config, "ZEP_API_KEY", "cle_config_env")

    mock_client = MagicMock()
    mock_client.graph.list_all.return_value = DummyGraphListResponse([])

    with patch("scripts.auditer_graphes_zep.get_zep_client", return_value=mock_client) as mock_get_client:
        auditer_compte_zep(api_key="cle_cli_prioritaire")
        mock_get_client.assert_called_once_with(api_key="cle_cli_prioritaire")
