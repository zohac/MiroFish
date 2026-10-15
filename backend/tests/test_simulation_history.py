"""
Tests hermétiques pour l'API /api/simulation/history et le tri de list_simulations.
Garantit l'ordonnancement antéchronologique (plus récent en premier),
la pagination (limit/offset), la recherche textuelle et les filtres de statut.
"""

import json
from datetime import datetime, timedelta
import pytest
from app import create_app
from app.services.simulation_manager import SimulationManager, SimulationState, SimulationStatus


@pytest.fixture
def app_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_list_simulations_order(monkeypatch, tmp_path):
    """Vérifie que list_simulations trie strictement par date antéchronologique."""
    manager = SimulationManager()
    monkeypatch.setattr(manager, "SIMULATION_DATA_DIR", str(tmp_path))

    # Créer 3 simulations avec des dates distinctes
    now = datetime.now()
    dates = [
        ("sim_old", (now - timedelta(days=2)).isoformat()),
        ("sim_recent", (now - timedelta(hours=1)).isoformat()),
        ("sim_mid", (now - timedelta(days=1)).isoformat()),
    ]

    for sim_id, dt_str in dates:
        sim_dir = tmp_path / sim_id
        sim_dir.mkdir()
        state_file = sim_dir / "state.json"
        state_data = {
            "simulation_id": sim_id,
            "project_id": "proj_1",
            "graph_id": "graph_1",
            "status": "completed",
            "created_at": dt_str,
            "updated_at": dt_str,
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

    sims = manager.list_simulations()
    assert len(sims) == 3
    # L'ordre doit être : sim_recent, sim_mid, sim_old
    assert sims[0].simulation_id == "sim_recent"
    assert sims[1].simulation_id == "sim_mid"
    assert sims[2].simulation_id == "sim_old"


def test_get_simulation_history_pagination_and_filter(app_client, monkeypatch, tmp_path):
    """Vérifie que /api/simulation/history pagine et filtre correctement."""
    from app.services.simulation_manager import SimulationManager
    manager = SimulationManager()
    monkeypatch.setattr(manager, "SIMULATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.api.simulation.SimulationManager", lambda: manager)

    # Ingestion de 5 simulations de test
    now = datetime.now()
    items = [
        ("sim_alpha", "Simuler Keova Essentiel", "completed", now - timedelta(minutes=5)),
        ("sim_beta", "Analyse transport urbain", "completed", now - timedelta(minutes=10)),
        ("sim_gamma", "Simuler Keova Premium", "running", now - timedelta(minutes=15)),
        ("sim_delta", "Test énergie renouvelable", "created", now - timedelta(minutes=20)),
        ("sim_epsilon", "Keova Signal prospective", "completed", now - timedelta(minutes=25)),
    ]

    for sim_id, req, status_val, dt in items:
        sim_dir = tmp_path / sim_id
        sim_dir.mkdir()
        state_file = sim_dir / "state.json"
        state_file.write_text(json.dumps({
            "simulation_id": sim_id,
            "project_id": "proj_demo",
            "graph_id": "graph_demo",
            "status": status_val,
            "created_at": dt.isoformat(),
            "updated_at": dt.isoformat(),
        }), encoding="utf-8")
        cfg_file = sim_dir / "simulation_config.json"
        cfg_file.write_text(json.dumps({
            "simulation_id": sim_id,
            "simulation_requirement": req,
        }), encoding="utf-8")

    # 1. Test pagination de base (limit=2, offset=0)
    res = app_client.get("/api/simulation/history?limit=2&offset=0")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["count"] == 2
    assert data["total"] == 5
    assert data["has_more"] is True
    assert data["data"][0]["simulation_id"] == "sim_alpha"
    assert data["data"][1]["simulation_id"] == "sim_beta"

    # 2. Test pagination page 2 (limit=2, offset=2)
    res_page2 = app_client.get("/api/simulation/history?limit=2&offset=2")
    data_page2 = res_page2.get_json()
    assert data_page2["count"] == 2
    assert data_page2["has_more"] is True
    assert data_page2["data"][0]["simulation_id"] == "sim_gamma"
    assert data_page2["data"][1]["simulation_id"] == "sim_delta"

    # 3. Test recherche par mot-clé "keova"
    res_search = app_client.get("/api/simulation/history?search=keova")
    data_search = res_search.get_json()
    assert data_search["total"] == 3
    found_ids = [s["simulation_id"] for s in data_search["data"]]
    assert "sim_alpha" in found_ids
    assert "sim_gamma" in found_ids
    assert "sim_epsilon" in found_ids
    assert "sim_beta" not in found_ids

    # 4. Test filtre par statut "completed"
    res_completed = app_client.get("/api/simulation/history?status=completed")
    data_completed = res_completed.get_json()
    assert data_completed["total"] == 3
    found_completed = [s["simulation_id"] for s in data_completed["data"]]
    assert "sim_alpha" in found_completed
    assert "sim_beta" in found_completed
    assert "sim_epsilon" in found_completed
    assert "sim_gamma" not in found_completed
