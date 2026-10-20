"""Tests hermétiques du catalogue de profils LLM et de l'historique enrichi (Story 013-5, FR-08, AC2, AC3).

Valide :
  - AC2 : `GET /api/report/profiles` renvoie le catalogue serveur, dans un ordre
    stable, sans aucune clé d'API ni URL de passerelle (NFR-4).
  - AC2 : un `profile_id` inconnu est refusé explicitement par
    `POST /api/report/generate` (400) — jamais un repli silencieux sur le modèle
    global, qui ferait croire à un benchmark sur un modèle non exécuté.
  - AC3 : l'historique expose l'empreinte SHA-256 des preuves figées, seule
    adresse de contenu permettant de conclure à l'identité des preuves.
  - AC1 : la sélection reste adossée à la route : l'identifiant de rapport
    reste unique et stable dans l'historique.
"""

import json
import os

import pytest

from app import create_app
from app.config import Config
from app.models.report_llm_profile import ReportLLMProfile
from app.services.report_agent import (
    Report,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    # Une passerelle et une clé factices : elles ne doivent jamais sortir.
    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://gateway.interne.invalid/v1")
    monkeypatch.setattr(Config, "LLM_API_KEY", "sk-secret-de-test-0123456789")
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _all_keys(payload):
    """Parcourt un payload et retourne l'ensemble des clés rencontrées."""
    keys = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(key)
            keys |= _all_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            keys |= _all_keys(item)
    return keys


def _create_report(report_id: str, simulation_id: str, snapshot: dict, created_at: str) -> Report:
    return Report(
        report_id=report_id,
        simulation_id=simulation_id,
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.COMPLETED,
        created_at=created_at,
        completed_at=created_at,
        outline=ReportOutline(
            title=f"Report {report_id}",
            summary="Summary",
            sections=[ReportSection(title="Section 1", content="Content 1")],
        ),
        markdown_content=f"# Report {report_id}\n\nContent\n",
        profile_id="flash-medium",
        replay_mode="replay_frozen",
        evidence_snapshot=snapshot,
    )


def _ensure_simulation_dir(simulation_id: str) -> None:
    """Crée le dossier de simulation : l'endpoint d'historique l'exige."""
    os.makedirs(
        os.path.join(Config.UPLOAD_FOLDER, "simulations", simulation_id),
        exist_ok=True,
    )


class TestReportProfilesEndpoint:
    """Catalogue serveur des profils LLM de rapport."""

    def test_endpoint_returns_every_standard_profile(self, client):
        """AC2 : le catalogue expose exactement les profils standards déclarés."""
        res = client.get("/api/report/profiles")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        profiles = body["data"]["profiles"]
        assert body["data"]["count"] == len(profiles)
        returned_ids = [item["profile_id"] for item in profiles]
        assert returned_ids == sorted(ReportLLMProfile.standard_profile_ids())
        assert set(returned_ids) == {
            "flash-medium",
            "flash-high",
            "deepseek-v4-pro",
            "qwen3.8-max",
            "gpt-6.1-sol",
        }

    def test_endpoint_order_is_deterministic(self, client):
        """AC2 : deux appels rendent la même liste, dans le même ordre."""
        first = client.get("/api/report/profiles").get_json()["data"]["profiles"]
        second = client.get("/api/report/profiles").get_json()["data"]["profiles"]
        assert [item["profile_id"] for item in first] == [
            item["profile_id"] for item in second
        ]
        assert [item["profile_id"] for item in first] == sorted(
            item["profile_id"] for item in first
        )

    def test_endpoint_never_exposes_a_secret(self, client):
        """AC2/NFR-4 : ni clé d'API, ni URL de passerelle dans la réponse."""
        res = client.get("/api/report/profiles")
        body = res.get_json()
        keys = _all_keys(body)
        assert "api_key" not in keys
        assert "base_url" not in keys
        raw = json.dumps(body)
        assert "sk-secret-de-test-0123456789" not in raw
        assert "gateway.interne.invalid" not in raw
        for item in body["data"]["profiles"]:
            assert isinstance(item["base_url_configured"], bool)
            assert item["model"]
            assert item["provider_id"]

    def test_endpoint_exposes_effort_and_budget_caps(self, client):
        """AC2 : l'IHM doit pouvoir afficher effort et plafonds sans secret."""
        profiles = {
            item["profile_id"]: item
            for item in client.get("/api/report/profiles").get_json()["data"]["profiles"]
        }
        assert profiles["flash-medium"]["reasoning_effort"] == "medium"
        assert profiles["flash-high"]["reasoning_effort"] == "high"
        for item in profiles.values():
            assert isinstance(item["max_total_cost_usd"], (int, float))
            assert isinstance(item["max_wall_seconds"], int)
            assert item["billing_mode"] in {"auto", "free", "metered"}


class TestGenerateProfileValidation:
    """Rejet explicite d'un profil inconnu (AC2)."""

    def test_unknown_profile_is_rejected(self, client):
        """AC2 : un profile_id inconnu renvoie 400, sans repli silencieux."""
        res = client.post(
            "/api/report/generate",
            json={
                "simulation_id": "sim_inconnue",
                "profile_id": "profil-inexistant",
                "force_regenerate": True,
            },
        )
        assert res.status_code == 400
        body = res.get_json()
        assert body["success"] is False
        assert "profil-inexistant" in body["error"]
        assert "flash-medium" in body["error"]

    def test_known_profile_is_not_rejected_by_the_profile_guard(self, client):
        """AC2 : un profil connu franchit le garde-fou (l'échec vient ensuite)."""
        res = client.post(
            "/api/report/generate",
            json={
                "simulation_id": "sim_inconnue",
                "profile_id": "flash-high",
                "force_regenerate": True,
            },
        )
        assert res.status_code == 404
        body = res.get_json()
        assert body["success"] is False
        assert "Unknown report profile" not in body["error"]

    def test_inline_llm_profile_still_supported(self, client):
        """AC2 : le corps llm_profile reste disponible pour les appels avancés."""
        res = client.post(
            "/api/report/generate",
            json={
                "simulation_id": "sim_inconnue",
                "llm_profile": {
                    "profile_id": "custom-job",
                    "model": "gemini-3.8-flash",
                    "reasoning_effort": "high",
                },
                "force_regenerate": True,
            },
        )
        assert res.status_code == 404
        assert "Unknown report profile" not in res.get_json()["error"]


class TestHistoryExposesEvidenceFingerprint:
    """L'historique porte l'empreinte des preuves figées (AC3)."""

    def test_history_entry_carries_snapshot_sha256(self, client, tmp_path, monkeypatch):
        """AC3 : l'historique expose l'empreinte SHA-256 des preuves."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_historique"
        snapshot = {
            "snapshot_id": "snap_abc123",
            "simulation_id": sim_id,
            "sha256_hash": "f" * 64,
            "file_hashes": {},
            "total_events": 3,
            "total_actors": 2,
            "has_archived_interviews": False,
            "created_at": "2026-10-19T10:00:00Z",
        }
        report = _create_report(
            "report_histo_01", sim_id, snapshot, "2026-10-19T10:00:00Z"
        )
        ReportManager.save_report(report)
        _ensure_simulation_dir(sim_id)

        res = client.get(f"/api/report/simulation/{sim_id}/history")
        assert res.status_code == 200
        reports = res.get_json()["data"]["reports"]
        assert len(reports) == 1
        assert reports[0]["evidence_snapshot_id"] == "snap_abc123"
        assert reports[0]["evidence_snapshot_sha256"] == "f" * 64

    def test_legacy_history_entry_is_completed_from_disk(self, client, tmp_path, monkeypatch):
        """AC3 : une entrée historique sans empreinte est complétée depuis le disque."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_legacy"
        snapshot = {
            "snapshot_id": "snap_legacy1",
            "simulation_id": sim_id,
            "sha256_hash": "a" * 64,
            "file_hashes": {},
            "total_events": 1,
            "total_actors": 1,
            "has_archived_interviews": False,
            "created_at": "2026-10-19T09:00:00Z",
        }
        report = _create_report(
            "report_legacy_01", sim_id, snapshot, "2026-10-19T09:00:00Z"
        )
        ReportManager.save_report(report)
        _ensure_simulation_dir(sim_id)
        # Index d'historique « ancien format » : ni empreinte, ni instantané.
        ReportManager._append_to_history(
            sim_id,
            {
                "report_id": "report_legacy_01",
                "simulation_id": sim_id,
                "created_at": "2026-10-19T09:00:00Z",
                "status": "completed",
            },
        )

        res = client.get(f"/api/report/simulation/{sim_id}/history")
        assert res.status_code == 200
        entry = res.get_json()["data"]["reports"][0]
        assert entry["evidence_snapshot_sha256"] == "a" * 64
        assert entry["evidence_snapshot_id"] == "snap_legacy1"

    def test_history_without_snapshot_reports_null_fingerprint(self, client, tmp_path, monkeypatch):
        """AC3 : un rapport sans instantané expose une empreinte nulle, jamais un faux hash."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_sans_preuves"
        report = _create_report(
            "report_sans_preuves", sim_id, None, "2026-10-19T08:00:00Z"
        )
        ReportManager.save_report(report)
        _ensure_simulation_dir(sim_id)

        res = client.get(f"/api/report/simulation/{sim_id}/history")
        assert res.status_code == 200
        entry = res.get_json()["data"]["reports"][0]
        assert entry["evidence_snapshot_sha256"] is None
        assert entry["evidence_snapshot_id"] is None


class TestRobustnessAgainstCorruptReports:
    """Un rapport illisible ne doit pas casser l'historique (AC6)."""

    def test_corrupt_report_is_skipped_and_history_still_works(
        self, client, tmp_path, monkeypatch
    ):
        """AC6 : un meta.json tronqué écarte le rapport, sans casser la liste."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_corrompu"
        snapshot = {
            "snapshot_id": "snap_ok",
            "simulation_id": sim_id,
            "sha256_hash": "b" * 64,
            "file_hashes": {},
            "total_events": 1,
            "total_actors": 1,
            "has_archived_interviews": False,
            "created_at": "2026-10-19T07:00:00Z",
        }
        report = _create_report("report_sain", sim_id, snapshot, "2026-10-19T07:00:00Z")
        ReportManager.save_report(report)
        _ensure_simulation_dir(sim_id)

        # Rapport corrompu : écriture tronquée, comme après un arrêt brutal.
        corrupt_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", "report_casse")
        os.makedirs(corrupt_dir, exist_ok=True)
        with open(os.path.join(corrupt_dir, "meta.json"), "w", encoding="utf-8") as handle:
            handle.write('{"report_id": "report_casse", "profile_id": ')

        res = client.get(f"/api/report/simulation/{sim_id}/history")
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        report_ids = [entry["report_id"] for entry in body["data"]["reports"]]
        assert "report_sain" in report_ids
        assert "report_casse" not in report_ids

    def test_corrupt_report_is_not_readable_as_a_report(self, tmp_path, monkeypatch):
        """AC6 : get_report renvoie None au lieu de lever une exception."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        corrupt_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", "report_casse")
        os.makedirs(corrupt_dir, exist_ok=True)
        with open(os.path.join(corrupt_dir, "meta.json"), "w", encoding="utf-8") as handle:
            handle.write("{ truncated")

        assert ReportManager.get_report("report_casse") is None

    def test_report_with_invalid_status_is_skipped(self, tmp_path, monkeypatch):
        """AC6 : un statut inconnu n'interrompt pas la lecture."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        broken_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", "report_statut")
        os.makedirs(broken_dir, exist_ok=True)
        with open(
            os.path.join(broken_dir, "meta.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "report_id": "report_statut",
                    "simulation_id": "sim_x",
                    "status": "statut_inexistant",
                },
                handle,
            )

        assert ReportManager.get_report("report_statut") is None


class TestStandardProfileCatalogueIntegrity:

    def test_declared_ids_match_the_built_catalog(self):
        """Le tuple public et le catalogue interne portent les mêmes identifiants."""
        catalog = ReportLLMProfile._build_standard_catalog()
        assert set(catalog.keys()) == set(ReportLLMProfile.standard_profile_ids())

    def test_every_standard_profile_resolves(self):
        """Chaque identifiant standard renvoie un profil exploitable."""
        for profile_id in ReportLLMProfile.standard_profile_ids():
            profile = ReportLLMProfile.get_standard_profile(profile_id)
            assert profile is not None
            assert profile.profile_id == profile_id
            assert profile.model
            assert profile.max_total_cost_usd >= 0
            assert profile.max_wall_seconds >= 0

    def test_unknown_profile_resolves_to_none(self):
        """Un identifiant hors catalogue ne renvoie aucun profil."""
        assert ReportLLMProfile.get_standard_profile("profil-inexistant") is None
