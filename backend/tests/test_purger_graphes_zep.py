"""Tests unitaires hermétiques pour l'outil de purge Zep Cloud et la validation de relecture (Story 006-3).

Ces tests vérifient :
1. Le parsing des arguments CLI (défauts, personnalisés, mode silencieux, validation des options mutuellement exclusives).
2. Le masquage strict des secrets (ZEP_API_KEY) et l'assainissement des messages d'erreur.
3. Les modèles typés (PurgeTarget, PurgeResult, PurgeReport) et leur sérialisation JSON / Markdown.
4. L'inventaire des cibles Zep Cloud (ciblage unitaire, balayage paginé --all, simulation --mock).
5. L'exécution unitaire et globale de la purge (mode simulation --dry-run, mode --mock, exécution réelle mockée).
6. Le mécanisme de sécurité renforcé : refus d'exécution en mode non-interactif sans --yes,
   double confirmation interactive stricte pour graphe unique et pour suppression totale.
7. Le point d'entrée exécutable main() et les exports de comptes-rendus.
8. La validation de relecture applicative post-migration (Critère C4) :
   - Relecture GraphStore (nœuds, arêtes, données de graphe complètes),
   - Filtrage et extraction d'entités typées via ZepEntityReader,
   - Compatibilité avec OasisProfileGenerator sans clé Zep.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.migrer_zep_vers_graphiti import (
    SimulatedGraphStore,
    SimulatedNeo4jLoader,
    generer_graphe_mock,
    main as migrer_main,
    valider_relecture_migree,
)
from scripts.purger_graphes_zep import (
    PurgeReport,
    PurgeResult,
    PurgeTarget,
    ZepPurgeManager,
    assainir_message_erreur,
    demander_confirmation,
    main,
    masquer_secret,
    parser_arguments,
)


# ==============================================================================
# 1. Tests CLI & Arguments (Purge)
# ==============================================================================


def test_parser_arguments_defaults():
    """Vérifie les options par défaut du parser CLI de purge."""
    args = parser_arguments([])
    assert args.graph_id is None
    assert args.all is False
    assert args.api_key is None
    assert args.yes is False
    assert args.dry_run is False
    assert args.mock is False
    assert args.output_report is None
    assert args.output_json is None
    assert args.quiet is False


def test_parser_arguments_custom():
    """Vérifie la prise en compte des options explicites."""
    args = parser_arguments([
        "--graph-id", "mon_graphe_zep",
        "--api-key", "z_secret_9999",
        "--yes",
        "--dry-run",
        "--mock",
        "--output-report", "/tmp/purge.md",
        "--output-json", "/tmp/purge.json",
        "--quiet",
    ])
    assert args.graph_id == "mon_graphe_zep"
    assert args.all is False
    assert args.api_key == "z_secret_9999"
    assert args.yes is True
    assert args.dry_run is True
    assert args.mock is True
    assert args.output_report == "/tmp/purge.md"
    assert args.output_json == "/tmp/purge.json"
    assert args.quiet is True


def test_masquer_secret():
    """Vérifie le masquage sûr des secrets sans fuite."""
    assert masquer_secret(None) == "<non défini>"
    assert masquer_secret("") == "<non défini>"
    assert masquer_secret("court") == "***"
    assert masquer_secret("zep_secret_api_key_2026") == "zep...26"


def test_assainir_message_erreur():
    """Vérifie que les clés d'API sont remplacées dans les traces d'erreurs."""
    msg = "Erreur HTTP 401 pour la clé z_abcdef123456789 sur le serveur"
    assaini = assainir_message_erreur(msg, secrets=["z_abcdef123456789"])
    assert "z_abcdef123456789" not in assaini
    assert "z_a...89" in assaini or "[CLE_ZEP_MASQUEE]" in assaini


# ==============================================================================
# 2. Dataclasses et Modèles de Données
# ==============================================================================


def test_dataclasses_purge_report_serialization():
    """Vérifie la sérialisation des modèles PurgeTarget, PurgeResult et PurgeReport."""
    target = PurgeTarget(graph_id="g1", name="Graphe 1", node_count=5, edge_count=4)
    target_dict = target.to_dict()
    assert target_dict["graph_id"] == "g1"
    assert target_dict["node_count"] == 5

    res = PurgeResult(
        graph_id="g1",
        status="PURGED",
        success=True,
        error_message=None,
        duration_seconds=0.12,
    )
    assert res.to_dict()["status"] == "PURGED"

    report = PurgeReport(
        total_targeted=1,
        total_purged=1,
        total_failed=0,
        total_skipped=0,
        dry_run=False,
        mock=True,
        results=[res],
        duration_seconds=0.15,
    )

    report_dict = report.to_dict()
    assert report_dict["total_purged"] == 1
    assert report_dict["mock"] is True

    json_str = report.to_json()
    assert '"total_purged": 1' in json_str

    md_str = report.to_markdown()
    assert "# Rapport de Purge Zep Cloud" in md_str
    assert "`g1`" in md_str
    assert "`PURGED`" in md_str


def test_purge_report_with_errors():
    """Vérifie le rendu Markdown d'un rapport contenant des échecs."""
    res = PurgeResult(
        graph_id="g_err",
        status="FAILED",
        success=False,
        error_message="ZepApiError: 404 Not Found",
        duration_seconds=0.05,
    )
    report = PurgeReport(
        total_targeted=1,
        total_purged=0,
        total_failed=1,
        total_skipped=0,
        results=[res],
        errors=["Graphe g_err : ZepApiError: 404 Not Found"],
    )
    md = report.to_markdown()
    assert "## Erreurs globales" in md
    assert "ZepApiError: 404 Not Found" in md


# ==============================================================================
# 3. Inventaire des Cibles Zep Cloud
# ==============================================================================


def test_inventorier_cibles_mock():
    """Vérifie la génération déterministe des cibles en mode --mock."""
    manager = ZepPurgeManager()

    # Graphe spécifique
    cibles_specifique = manager.inventorier_cibles(graph_id="rapport_2506", mock_mode=True)
    assert len(cibles_specifique) == 1
    assert cibles_specifique[0].graph_id == "rapport_2506"

    # Tous les graphes mock
    cibles_all = manager.inventorier_cibles(purge_all=True, mock_mode=True)
    assert len(cibles_all) == 3
    assert {c.graph_id for c in cibles_all} == {"mock_graphe_1", "mock_graphe_2", "mock_graphe_3"}

    # Défaut
    cibles_defaut = manager.inventorier_cibles(mock_mode=True)
    assert len(cibles_defaut) == 1
    assert cibles_defaut[0].graph_id == "mock_graph_demo"


def test_inventorier_cibles_reel_all_paginated():
    """Vérifie l'inventaire complet paginé d'un compte Zep réel mocké."""
    mock_client = MagicMock()

    # Simulation de 2 pages de graphes
    page1 = MagicMock()
    page1.graphs = [
        {"graph_id": "grp_1", "name": "Graphe 1"},
        {"graph_id": "grp_2", "name": "Graphe 2"},
    ]
    # Pour forcer la 2e page, on mocke len(page1.graphs) == page_size
    mock_client.graph.list_all.side_effect = [
        MagicMock(graphs=[{"graph_id": f"grp_{i}", "name": f"Graphe {i}"} for i in range(50)]),
        MagicMock(graphs=[{"graph_id": "grp_51", "name": "Graphe 51"}]),
    ]

    manager = ZepPurgeManager(zep_client=mock_client)
    cibles = manager.inventorier_cibles(purge_all=True, mock_mode=False)

    assert len(cibles) == 51
    assert cibles[0].graph_id == "grp_0"
    assert cibles[-1].graph_id == "grp_51"
    assert mock_client.graph.list_all.call_count == 2


def test_inventorier_cibles_erreur_client_manquant():
    """Vérifie l'erreur si purge_all est demandé sans client Zep."""
    manager = ZepPurgeManager(zep_client=None)
    with pytest.raises(ValueError, match="Client Zep Cloud non configuré"):
        manager.inventorier_cibles(purge_all=True, mock_mode=False)


# ==============================================================================
# 4. Exécution de la Purge
# ==============================================================================


def test_purger_graphe_dry_run():
    """Vérifie qu'aucun appel de suppression n'est émis en mode dry-run."""
    mock_client = MagicMock()
    manager = ZepPurgeManager(zep_client=mock_client)
    target = PurgeTarget(graph_id="graphe_a_garder")

    res = manager.purger_graphe(target, dry_run=True, mock_mode=False)
    assert res.status == "SKIPPED_DRY_RUN"
    assert res.success is True
    assert mock_client.graph.delete.call_count == 0


def test_purger_graphe_mock():
    """Vérifie la purge simulée réussie en mode mock."""
    manager = ZepPurgeManager()
    target = PurgeTarget(graph_id="mock_test")

    res = manager.purger_graphe(target, dry_run=False, mock_mode=True)
    assert res.status == "PURGED"
    assert res.success is True
    assert target.status == "PURGED"


def test_purger_graphe_reel_succes():
    """Vérifie l'appel effectif à client.graph.delete en mode réel."""
    mock_client = MagicMock()
    manager = ZepPurgeManager(zep_client=mock_client)
    target = PurgeTarget(graph_id="graphe_reel_1")

    res = manager.purger_graphe(target, dry_run=False, mock_mode=False)
    assert res.status == "PURGED"
    assert res.success is True
    mock_client.graph.delete.assert_called_once_with(graph_id="graphe_reel_1")


def test_purger_graphe_reel_echec():
    """Vérifie la capture et l'assainissement d'erreur en cas d'exception Zep."""
    mock_client = MagicMock()
    mock_client.graph.delete.side_effect = RuntimeError("Zep delete error with secret z_secret12345678")
    manager = ZepPurgeManager(zep_client=mock_client, api_key="z_secret12345678")
    target = PurgeTarget(graph_id="graphe_fail")

    res = manager.purger_graphe(target, dry_run=False, mock_mode=False)
    assert res.status == "FAILED"
    assert res.success is False
    assert target.status == "FAILED"
    assert "z_secret12345678" not in (res.error_message or "")


def test_executer_purge_orchestration():
    """Vérifie l'orchestration globale de la purge sur plusieurs cibles."""
    manager = ZepPurgeManager()
    cibles = [
        PurgeTarget(graph_id="c1"),
        PurgeTarget(graph_id="c2"),
    ]
    progression: list[tuple[int, int, str]] = []

    def _prog(curr: int, tot: int, gid: str) -> None:
        progression.append((curr, tot, gid))

    report = manager.executer_purge(cibles, dry_run=False, mock_mode=True, progress_callback=_prog)
    assert report.total_targeted == 2
    assert report.total_purged == 2
    assert report.total_failed == 0
    assert len(progression) == 2


# ==============================================================================
# 5. Sécurité et Confirmation Interactive
# ==============================================================================


def test_demander_confirmation_force_yes():
    """Vérifie que le flag --yes accorde immédiatement la confirmation."""
    cibles = [PurgeTarget(graph_id="mon_graphe")]
    confirme, motif = demander_confirmation(cibles, force_yes=True)
    assert confirme is True
    assert "--yes" in motif


def test_demander_confirmation_refus_non_interactif():
    """Vérifie le blocage de sécurité en environnement non interactif sans --yes."""
    cibles = [PurgeTarget(graph_id="mon_graphe")]
    confirme, motif = demander_confirmation(cibles, force_yes=False, is_interactive=False)
    assert confirme is False
    assert "Refus de sécurité" in motif
    assert "--yes" in motif


def test_demander_confirmation_interactive_unitaire_succes():
    """Vérifie la confirmation par saisie exacte de l'identifiant pour un graphe unique."""
    cibles = [PurgeTarget(graph_id="rapport_an_2506")]
    mock_input = lambda _prompt: "rapport_an_2506"

    confirme, motif = demander_confirmation(
        cibles, force_yes=False, is_interactive=True, input_func=mock_input
    )
    assert confirme is True
    assert "rapport_an_2506" in motif


def test_demander_confirmation_interactive_unitaire_echec():
    """Vérifie l'annulation si l'identifiant saisi est incorrect."""
    cibles = [PurgeTarget(graph_id="rapport_an_2506")]
    mock_input = lambda _prompt: "mauvais_nom"

    confirme, motif = demander_confirmation(
        cibles, force_yes=False, is_interactive=True, input_func=mock_input
    )
    assert confirme is False
    assert "Confirmation incorrecte" in motif


def test_demander_confirmation_interactive_all_succes():
    """Vérifie la confirmation collective avec 'SUPPRIMER TOUT' pour --all."""
    cibles = [PurgeTarget(graph_id="g1"), PurgeTarget(graph_id="g2")]
    mock_input = lambda _prompt: "SUPPRIMER TOUT"

    confirme, motif = demander_confirmation(
        cibles, force_yes=False, is_interactive=True, input_func=mock_input
    )
    assert confirme is True
    assert "SUPPRIMER TOUT" in motif


def test_demander_confirmation_interactive_all_echec():
    """Vérifie l'annulation si la saisie collective n'est pas 'SUPPRIMER TOUT'."""
    cibles = [PurgeTarget(graph_id="g1"), PurgeTarget(graph_id="g2")]
    mock_input = lambda _prompt: "oui"

    confirme, motif = demander_confirmation(
        cibles, force_yes=False, is_interactive=True, input_func=mock_input
    )
    assert confirme is False
    assert "Confirmation incorrecte" in motif


def test_demander_confirmation_interactive_interruption():
    """Vérifie la gestion propre de Ctrl+C ou EOFError."""
    cibles = [PurgeTarget(graph_id="g1")]

    def _interrupted(_prompt: str) -> str:
        raise EOFError

    confirme, motif = demander_confirmation(
        cibles, force_yes=False, is_interactive=True, input_func=_interrupted
    )
    assert confirme is False
    assert "interrompue" in motif


# ==============================================================================
# 6. Point d'Entrée Principal main() de purger_graphes_zep.py
# ==============================================================================


def test_main_purge_mock_yes(tmp_path: Path):
    """Vérifie l'exécution complète du main en mode --mock --yes avec export."""
    report_file = tmp_path / "report.md"
    json_file = tmp_path / "report.json"

    ret = main([
        "--mock",
        "--yes",
        "--graph-id", "mock_graphe_an",
        "--output-report", str(report_file),
        "--output-json", str(json_file),
        "--quiet",
    ])
    assert ret == 0
    assert report_file.exists()
    assert json_file.exists()

    report_content = report_file.read_text(encoding="utf-8")
    assert "mock_graphe_an" in report_content
    assert "PURGED" in report_content

    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["total_purged"] == 1


def test_main_purge_mutually_exclusive_args():
    """Vérifie l'erreur quand --graph-id et --all sont fournis ensemble."""
    ret = main(["--graph-id", "g1", "--all", "--yes"])
    assert ret == 1


def test_main_purge_missing_target():
    """Vérifie l'erreur quand aucune cible n'est spécifiée en mode réel."""
    ret = main(["--yes"])
    assert ret == 1


def test_main_purge_missing_api_key(monkeypatch: pytest.MonkeyPatch):
    """Vérifie l'erreur quand la clé Zep est absente en mode réel."""
    monkeypatch.delenv("ZEP_API_KEY", raising=False)
    with patch("scripts.purger_graphes_zep.Config.ZEP_API_KEY", None):
        ret = main(["--graph-id", "g1", "--yes"])
        assert ret == 1


# ==============================================================================
# 7. Validation de Relecture Applicative (Critère C4 du PRD)
# ==============================================================================


def test_simulated_graph_store_relecture():
    """Vérifie que SimulatedGraphStore restitue fidèlement nœuds et arêtes."""
    loader = SimulatedNeo4jLoader()
    mock_nodes, mock_edges = generer_graphe_mock("graph_c4_test")

    # Transformation et injection simulée
    from scripts.migrer_zep_vers_graphiti import ZepToGraphitiTransformer

    trans = ZepToGraphitiTransformer()
    tnodes, tedges, _ = trans.transformer_graphe(mock_nodes, mock_edges, "graph_c4_test")
    loader.injecter_noeuds(tnodes, "graph_c4_test")
    loader.injecter_aretes(tedges, "graph_c4_test")

    store = SimulatedGraphStore(loader=loader)

    # Relecture nœuds et arêtes
    nodes = store.get_all_nodes("graph_c4_test")
    edges = store.get_all_edges("graph_c4_test")
    assert len(nodes) == len(mock_nodes)
    assert len(edges) == len(mock_edges)

    # Données complètes API web
    data = store.get_graph_data("graph_c4_test")
    assert data["node_count"] == len(mock_nodes)
    assert data["edge_count"] == len(mock_edges)
    assert len(data["nodes"]) == len(mock_nodes)
    assert len(data["edges"]) == len(mock_edges)

    # Métadonnées synthétiques
    info = store.get_graph_info("graph_c4_test")
    assert info.node_count == len(mock_nodes)
    assert info.edge_count == len(mock_edges)
    assert "Person" in info.entity_types or "Institution" in info.entity_types

    # Vérification get_node et get_node_edges
    first_uuid = nodes[0].uuid
    assert store.get_node("graph_c4_test", first_uuid) is not None
    assert store.get_node("graph_c4_test", "inconnu") is None
    connected_edges = store.get_node_edges("graph_c4_test", first_uuid)
    assert isinstance(connected_edges, list)


def test_valider_relecture_migree_succes():
    """Valide de bout en bout la relecture applicative (GraphStore, ZepEntityReader, OASIS)."""
    loader = SimulatedNeo4jLoader()
    mock_nodes, mock_edges = generer_graphe_mock("c4_full_check")

    from scripts.migrer_zep_vers_graphiti import ZepToGraphitiTransformer

    trans = ZepToGraphitiTransformer()
    tnodes, tedges, _ = trans.transformer_graphe(mock_nodes, mock_edges, "c4_full_check")
    loader.injecter_noeuds(tnodes, "c4_full_check")
    loader.injecter_aretes(tedges, "c4_full_check")

    store = SimulatedGraphStore(loader=loader)

    bilan = valider_relecture_migree(
        target_graph_id="c4_full_check",
        store=store,
        entity_types=["Person", "Institution", "Commission", "Document"],
    )

    assert bilan["valid"] is True
    assert bilan["nodes_count"] == len(mock_nodes)
    assert bilan["edges_count"] == len(mock_edges)
    assert bilan["filtered_entities_count"] == len(mock_nodes)
    assert bilan["oasis_ready"] is True
    assert all(bilan["checks"].values())


def test_migrer_zep_vers_graphiti_cli_verify_relecture(tmp_path: Path):
    """Vérifie l'exécution CLI de migrer_zep_vers_graphiti.py avec --verify-relecture."""
    rep_md = tmp_path / "mig_rep.md"
    rep_json = tmp_path / "mig_rep.json"

    ret = migrer_main([
        "--mock",
        "--graph-id", "test_c4_cli",
        "--verify-relecture",
        "--output-report", str(rep_md),
        "--output-json", str(rep_json),
        "--quiet",
    ])

    assert ret == 0
    assert rep_md.exists()
    assert rep_json.exists()

    md_content = rep_md.read_text(encoding="utf-8")
    assert "Validation de Relecture Applicative (Critère C4)" in md_content
    assert "**Statut global** : ✅ Validée" in md_content

    json_data = json.loads(rep_json.read_text(encoding="utf-8"))
    assert json_data["relecture_validation"]["valid"] is True
    assert json_data["relecture_validation"]["oasis_ready"] is True
