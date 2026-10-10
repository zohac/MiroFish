"""Tests unitaires hermétiques pour la sonde de qualification Docker (Story 005-5).

Vérifie l'ensemble des contrôles (C1 à C5), les détections de fuites de secrets,
les analyses de statuts Docker Compose et la synthèse de qualification.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.verifier_qualification_docker import (
    RapportQualificationDocker,
    ResultatControle,
    controler_c1_demarrage_unifie,
    controler_c2_filet_tests,
    controler_c3_persistance_neo4j,
    controler_c4_pipeline_e2e_docker,
    controler_c5_securite_secrets_et_ci,
    detecter_secret_dans_calque,
    main,
    run_qualification_docker_protocol,
)


class TestDetectionSecretsCalques:
    """Contrôles de détection de fuite de secrets dans les calques Docker (NFR-1, C5)."""

    def test_calque_propre_autorise(self) -> None:
        calques_valides = [
            'COPY backend/ ./backend/',
            'COPY AGENTS.md .env.example docker-compose.yml ./',
            'RUN /bin/sh -c cd backend && uv sync --locked',
            'ENV PYTHONUNBUFFERED=1 FLASK_PORT=5001',
            'EXPOSE 5001',
        ]
        for c in calques_valides:
            assert detecter_secret_dans_calque(c) is None

    def test_calque_copie_env_interdit(self) -> None:
        calques_interdits = [
            'COPY .env .',
            'COPY ./.env ./backend/.env',
            'COPY ["./.env", "/app/.env"]',
            'COPY .env.production /app/.env',
            'ADD .env /app/.env',
            'ADD [".env.local", "/app/"]',
        ]
        for c in calques_interdits:
            res = detecter_secret_dans_calque(c)
            assert res is not None
            assert "ENV" in res

    def test_calque_copie_env_example_autorise(self) -> None:
        assert detecter_secret_dans_calque('COPY .env.example .env.example') is None
        assert detecter_secret_dans_calque('COPY AGENTS.md .env.example ./') is None
        assert detecter_secret_dans_calque('ADD .env.example ./') is None

    def test_calque_tokens_sensibles_interdits(self) -> None:
        assert detecter_secret_dans_calque('ENV LLM_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456') is not None
        assert detecter_secret_dans_calque('ENV ZEP_API_KEY=z_abcdefghijklmnopqrstuvwxyz123456') is not None
        assert detecter_secret_dans_calque('RUN echo mirofish-386d4eab1e5d > /tmp/pwd') is not None

    def test_calque_variable_expansion_autorisee(self) -> None:
        assert detecter_secret_dans_calque('ENV NEO4J_PASSWORD=${NEO4J_PASSWORD}') is None
        assert detecter_secret_dans_calque('ENV LLM_API_KEY=$LLM_API_KEY') is None
        assert detecter_secret_dans_calque('ENV NEO4J_PASSWORD=${NEO4J_PASSWORD:-secret_defaut}') is None


class TestControlerC1Demarrage:
    """Tests pour le contrôle C1 : Démarrage unifié de la stack Compose."""

    def test_mode_mock(self) -> None:
        res = controler_c1_demarrage_unifie(mock=True)
        assert res.statut == "OK"
        assert res.nom == "C1_demarrage_unifie_stack"
        assert "services" in res.details

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_succes_json_docker_compose_ps(self, mock_exec: MagicMock) -> None:
        ps_json = (
            '{"Service": "neo4j", "Health": "healthy", "State": "running"}\n'
            '{"Service": "backend", "Health": "healthy", "State": "running"}\n'
            '{"Service": "frontend", "Health": "", "State": "running"}\n'
        )
        mock_exec.return_value = (0, ps_json, "")
        res = controler_c1_demarrage_unifie(mock=False)
        assert res.statut == "OK"
        assert "neo4j" in res.details["services_etat"]
        assert "backend" in res.details["services_etat"]
        assert "frontend" in res.details["services_etat"]

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_service_manquant(self, mock_exec: MagicMock) -> None:
        ps_json = (
            '{"Service": "neo4j", "Health": "healthy", "State": "running"}\n'
            '{"Service": "backend", "Health": "healthy", "State": "running"}\n'
        )
        mock_exec.return_value = (0, ps_json, "")
        res = controler_c1_demarrage_unifie(mock=False)
        assert res.statut == "ECHEC"
        assert "frontend" in res.details["manquants"]

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_service_non_healthy(self, mock_exec: MagicMock) -> None:
        ps_json = (
            '{"Service": "neo4j", "Health": "unhealthy", "State": "running"}\n'
            '{"Service": "backend", "Health": "healthy", "State": "running"}\n'
            '{"Service": "frontend", "Health": "", "State": "running"}\n'
        )
        mock_exec.return_value = (0, ps_json, "")
        res = controler_c1_demarrage_unifie(mock=False)
        assert res.statut == "ECHEC"
        assert "neo4j" in res.details["non_pret"]

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_fallback_texte_si_json_echoue(self, mock_exec: MagicMock) -> None:
        mock_exec.side_effect = [
            (1, "", "JSON non supporte"),
            (0, "NAME\nmirofish-neo4j Up (healthy)\nmirofish-backend Up\nmirofish-frontend Up", ""),
        ]
        res = controler_c1_demarrage_unifie(mock=False)
        assert res.statut == "OK"

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_fallback_texte_service_non_actif(self, mock_exec: MagicMock) -> None:
        mock_exec.side_effect = [
            (1, "", "JSON non supporte"),
            (0, "NAME\nmirofish-neo4j Up (healthy)\nmirofish-backend Exited (1)\nmirofish-frontend Up", ""),
        ]
        res = controler_c1_demarrage_unifie(mock=False)
        assert res.statut == "ECHEC"
        assert any("backend" in s for s in res.details["services_inactifs"])

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_fallback_texte_service_manquant(self, mock_exec: MagicMock) -> None:
        mock_exec.side_effect = [
            (1, "", "JSON non supporte"),
            (0, "NAME\nmirofish-neo4j Up (healthy)\nmirofish-backend Up", ""),
        ]
        res = controler_c1_demarrage_unifie(mock=False)
        assert res.statut == "ECHEC"
        assert any("frontend" in s for s in res.details["services_inactifs"])


class TestControlerC2FiletTests:
    """Tests pour le contrôle C2 : Exécution de la suite de tests sous Docker."""

    def test_mode_mock_et_skip(self) -> None:
        res_mock = controler_c2_filet_tests(mock=True)
        assert res_mock.statut == "OK"
        assert res_mock.details["tests_passes"] == 684

        res_skip = controler_c2_filet_tests(skip=True)
        assert res_skip.statut == "IGNORE"

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_succes_et_echec(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = (0, "684 passed in 45s", "")
        res = controler_c2_filet_tests(mock=False)
        assert res.statut == "OK"

        mock_exec.return_value = (1, "", "1 failed, 683 passed")
        res_err = controler_c2_filet_tests(mock=False)
        assert res_err.statut == "ECHEC"


class TestControlerC3Persistance:
    """Tests pour le contrôle C3 : Persistance des données Neo4j."""

    def test_mode_mock(self) -> None:
        res = controler_c3_persistance_neo4j(mock=True)
        assert res.statut == "OK"
        assert res.details["critere_C3"] is True

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_succes_et_echec(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = (0, json.dumps({"succes_global": True}), "")
        res = controler_c3_persistance_neo4j(mock=False)
        assert res.statut == "OK"

        mock_exec.return_value = (1, "", "Erreur de persistance")
        res_err = controler_c3_persistance_neo4j(mock=False)
        assert res_err.statut == "ECHEC"


class TestControlerC4PipelineE2E:
    """Tests pour le contrôle C4 : Pipeline complet e2e local-first dans le conteneur backend."""

    def test_mode_mock(self) -> None:
        res = controler_c4_pipeline_e2e_docker(mock=True)
        assert res.statut == "OK"
        assert res.details["statut"] == "SUCCES"

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_succes_et_echec(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = (0, json.dumps({"statut": "SUCCES", "criteres": {"C3": True}}), "")
        res = controler_c4_pipeline_e2e_docker(mock=False)
        assert res.statut == "OK"

        mock_exec.return_value = (1, "", "Erreur d'ingestion Neo4j")
        res_err = controler_c4_pipeline_e2e_docker(mock=False)
        assert res_err.statut == "ECHEC"

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_succes_avec_banniere_docker_stdout(self, mock_exec: MagicMock) -> None:
        stdout_bruite = (
            "Container mirofish-backend-run-123 Created\n"
            "Attaching to mirofish-backend-run-123\n"
            + json.dumps({"statut": "SUCCES", "criteres": {"C4": True}})
            + "\nContainer mirofish-backend-run-123 Removed\n"
        )
        mock_exec.return_value = (0, stdout_bruite, "")
        res = controler_c4_pipeline_e2e_docker(mock=False)
        assert res.statut == "OK"
        assert res.details.get("rapport_e2e", {}).get("statut") == "SUCCES"


class TestControlerC5SecuriteEtCI:
    """Tests pour le contrôle C5 : Zéro secret et conformité CI."""

    def test_mode_mock(self) -> None:
        res = controler_c5_securite_secrets_et_ci(mock=True)
        assert res.statut == "OK"
        assert res.details["ci_conforme"] is True

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_fuite_secret_detectee(self, mock_exec: MagicMock) -> None:
        mock_exec.side_effect = [
            (0, "COPY .env /app/.env\n", ""),  # backend avec fuite
            (0, "CMD pnpm run dev\n", ""),     # frontend propre
        ]
        res = controler_c5_securite_secrets_et_ci(mock=False)
        assert res.statut == "ECHEC"
        assert len(res.details["findings"]) >= 1

    @patch("scripts.verifier_qualification_docker._executer_commande")
    def test_echec_ruff_ou_plans(self, mock_exec: MagicMock) -> None:
        mock_exec.side_effect = [
            (0, "CMD uv run python run.py\n", ""),  # backend propre
            (0, "CMD pnpm run dev\n", ""),          # frontend propre
            (1, "", "F841 unused variable"),        # ruff echec
        ]
        res = controler_c5_securite_secrets_et_ci(mock=False)
        assert res.statut == "ECHEC"
        assert "ruff check" in res.message


class TestOrchestrationEtMain:
    """Tests d'orchestration globale et du point d'entrée main()."""

    def test_run_protocol_mock(self) -> None:
        rapport = run_qualification_docker_protocol(mock=True, skip_tests=False)
        assert isinstance(rapport, RapportQualificationDocker)
        assert rapport.succes_global is True
        assert len(rapport.controles) == 5
        assert all(rapport.criteres.values())

    @patch("scripts.verifier_qualification_docker.controler_c1_demarrage_unifie")
    def test_run_protocol_echec_c1(self, mock_c1: MagicMock) -> None:
        mock_c1.return_value = ResultatControle(nom="C1", statut="ECHEC", message="Echec démarrage")
        rapport = run_qualification_docker_protocol(mock=True, skip_tests=True)
        assert rapport.succes_global is False
        assert rapport.criteres["C1"] is False

    @patch("sys.argv", ["verifier_qualification_docker.py", "--mock"])
    def test_main_mock(self) -> None:
        code = main()
        assert code == 0

    @patch("sys.argv", ["verifier_qualification_docker.py", "--mock", "--json"])
    def test_main_mock_json(self, capsys: pytest.CaptureFixture) -> None:
        code = main()
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["succes_global"] is True
        assert "criteres" in data
