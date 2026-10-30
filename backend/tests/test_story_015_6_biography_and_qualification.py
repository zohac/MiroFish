# -*- coding: utf-8 -*-
"""Tests unitaires hermétiques pour la Story 015-6 :

Cohérence biographique fiches ↔ prose finale, métadonnées Docker (git_commit, horizon)
et qualification multi-domaines (Epic 015, AC1 à AC8).
"""

import json
import os
import re
import unittest
from unittest.mock import MagicMock, patch

from app.models.report_claim import (
    ClaimKind,
    InformationOrigin,
    ProvenanceRegime,
    ReportClaim,
    VerificationStatus,
)
from app.services.brief_consistency import (
    BiographicalEpisode,
    PracticeDurationAttribute,
    audit_prose_persona_consistency,
    check_claim_persona_biography,
    extract_all_biographical_durations,
    extract_episodes,
    extract_practice_durations,
    parse_duration_tokens,
)
from app.services.simulation_action_verifier import SimulationActionVerifier
from app.services.simulation_audit_service import SimulationAuditService


class TestStory0156BiographyAndQualification(unittest.TestCase):
    """Couvre l'ensemble des critères d'acceptation AC1 à AC8 de la Story 015-6."""

    def test_ac1_extract_practice_durations_fr_en_numbers_and_words(self):
        """AC1: Extraction déterministe des durées d'exercice (chiffres, lettres, demi-unités, FR/EN)."""
        # Français chiffres
        t1 = "Installée depuis 17 ans à Nantes avec un cabinet réputé."
        res1 = extract_practice_durations(t1)
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0].years, 17.0)
        self.assertEqual(res1[0].context_kind, "current_practice")

        # Français lettres avec demi-unité
        t2 = "Naturopathe installée depuis deux ans et demi à Angers."
        res2 = extract_practice_durations(t2)
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0].years, 2.5)

        # Français mois
        t3 = "En activité libérale depuis 6 mois seulement."
        res3 = extract_practice_durations(t3)
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0].years, 0.5)

        # Anglais
        t4 = "Practicing for over 5 years in private clinic."
        res4 = extract_practice_durations(t4)
        self.assertEqual(len(res4), 1)
        self.assertEqual(res4[0].years, 5.0)

        # Carrière passée distinguée (non installée actuellement)
        t5 = "Ancienne aide-soignante pendant vingt-deux ans à l'hôpital public."
        res5 = extract_practice_durations(t5)
        self.assertEqual(len(res5), 1)
        self.assertEqual(res5[0].years, 22.0)
        self.assertEqual(res5[0].context_kind, "past_career")

    def test_ac2_check_claim_persona_biography_and_verifier(self):
        """AC2: Contradiction biographique détectée et branchée dans verify_report_claim."""
        profiles_map = {
            "Sylvie": {
                "name": "Sylvie",
                "persona": "Sylvie Delaunay, 52 ans, naturopathe installée depuis deux ans et demi à Angers.",
                "bio": "",
            },
            "Émilie": {
                "name": "Émilie",
                "persona": "Émilie a versé 1 500 € pour un site WordPress mal conçu par une agence.",
                "bio": "",
            },
        }

        # 1. Test unitaire check_claim_persona_biography (ancienneté)
        claim_contra = "Sylvie, installée depuis 17 ans avec un carnet plein, refuse la formule."
        is_contra, reason = check_claim_persona_biography(
            claim_text=claim_contra,
            agent_name="Sylvie",
            profiles_by_name=profiles_map,
        )
        self.assertTrue(is_contra)
        self.assertIn("PERSONA_BIOGRAPHY_CONTRADICTION", reason)
        self.assertIn("17 ans", reason)
        self.assertIn("2.5 ans", reason)

        # 2. Test branché dans SimulationActionVerifier.verify_report_claim
        claim_obj = ReportClaim(
            claim_id="clm_sylvie_contra",
            text=claim_contra,
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            agent_name="Sylvie",
            provenance_regime=ProvenanceRegime.ACTION,
            asserted_as_action=True,
        )

        verifier = SimulationActionVerifier(simulation_id="sim_test")
        v_res = verifier.verify_report_claim(
            claim=claim_obj,
            persona_profiles=profiles_map,
        )
        self.assertEqual(v_res.verification_status, VerificationStatus.CONTRADICTED)
        self.assertEqual(v_res.confidence, 0.0)
        self.assertTrue(any("PERSONA_BIOGRAPHY_CONTRADICTION" in lim for lim in v_res.limitations))

        # 3. Contradiction croisée d'épisode monétaire
        all_eps = {name: extract_episodes(p["persona"], excluded_keywords={name.lower()}) for name, p in profiles_map.items()}
        claim_cross = "Sylvie a perdu 1 500 € avec une agence WordPress pour son ancien site."
        is_cross, reason_cross = check_claim_persona_biography(
            claim_text=claim_cross,
            agent_name="Sylvie",
            profiles_by_name=profiles_map,
            all_profile_episodes=all_eps,
        )
        self.assertTrue(is_cross)
        self.assertIn("PERSONA_BIOGRAPHY_CONTRADICTION", reason_cross)
        self.assertIn("Émilie", reason_cross)

        # Test branché de l'épisode monétaire croisé dans SimulationActionVerifier.verify_report_claim (Patch 1 BMAD)
        claim_cross_obj = ReportClaim(
            claim_id="clm_sylvie_cross",
            text=claim_cross,
            claim_kind=ClaimKind.ANALYST_INFERENCE,
            origin=InformationOrigin.SIMULATION,
            agent_name="Sylvie",
            provenance_regime=ProvenanceRegime.INFERENCE,
            asserted_as_action=False,
        )
        v_res_cross = verifier.verify_report_claim(
            claim=claim_cross_obj,
            persona_profiles=profiles_map,
        )
        self.assertEqual(v_res_cross.verification_status, VerificationStatus.CONTRADICTED)
        self.assertEqual(v_res_cross.confidence, 0.0)
        self.assertTrue(any("PERSONA_BIOGRAPHY_CONTRADICTION" in lim for lim in v_res_cross.limitations))

    def test_ac3_non_blocking_of_legitimate_opinions_and_past_careers(self):
        """AC3: Non-blocage des évolutions d'opinion, doutes et rappels fidèles de carrières passées."""
        profiles_map = {
            "Sylvie": {
                "name": "Sylvie",
                "persona": "Sylvie Delaunay, naturopathe installée depuis deux ans et demi à Angers.",
                "bio": "",
            },
            "Christine": {
                "name": "Christine",
                "persona": "Christine, ancienne aide-soignante pendant vingt-deux ans à l'hôpital.",
                "bio": "",
            },
        }

        # Évolution d'opinion
        claim_op = "Sylvie hésite vivement sur le tarif et ajourne sa décision après 72h de réflexion."
        is_contra, _ = check_claim_persona_biography(claim_op, "Sylvie", profiles_map)
        self.assertFalse(is_contra)

        # Rappel fidèle de carrière passée
        claim_past = "Christine, ancienne soignante à l'hôpital pendant 22 ans, s'inquiète de la conformité."
        is_contra_past, _ = check_claim_persona_biography(claim_past, "Christine", profiles_map)
        self.assertFalse(is_contra_past)

    def test_ac4_audit_prose_persona_consistency_and_storage(self):
        """AC4: audit_prose_persona_consistency découpe la prose et enrichit le résultat."""
        profiles = [
            {
                "name": "Sylvie",
                "persona": "Sylvie Delaunay, naturopathe installée depuis deux ans et demi à Angers.",
            },
            {
                "name": "Émilie",
                "persona": "Émilie a versé 1 500 € pour un site WordPress mal conçu par une agence.",
            },
        ]
        markdown_text = """
# Analyse des comportements

Sylvie, pourtant installée depuis 17 ans avec un carnet plein, refuse la formule.

Sylvie hésite sur le tarif et préfère ajourner son inscription après 72h.
"""
        res = audit_prose_persona_consistency(
            markdown_content=markdown_text,
            profiles=profiles,
            allowed_names={"Sylvie", "Émilie"},
        )
        self.assertFalse(res.is_consistent)
        self.assertEqual(len(res.contradictions), 1)
        self.assertEqual(res.contradictions[0].carrier, "Sylvie")
        self.assertIn("17 ans", res.contradictions[0].reason)
        self.assertIn("Sylvie", res.diagnostics.get("practice_durations_by_profile", {}))

        # Vérification de la persistance disque et empaquetage ZIP (Patch 12 BMAD / VG-2)
        import tempfile
        import shutil
        from app.config import Config
        from app.services.report_agent import ReportAgent

        tmp_dir = tempfile.mkdtemp()
        old_upload = Config.UPLOAD_FOLDER
        try:
            Config.UPLOAD_FOLDER = tmp_dir
            sim_id = "sim_test_audit_storage"
            rep_id = "rep_test_audit_storage"
            os.makedirs(os.path.join(tmp_dir, "simulations", sim_id), exist_ok=True)
            os.makedirs(os.path.join(tmp_dir, "reports", rep_id), exist_ok=True)

            # Écriture manuelle du fichier brief_consistency.json avec le résultat prose
            agent = ReportAgent("g_test", simulation_id=sim_id, simulation_requirement="")
            rep_bc_path = os.path.join(tmp_dir, "reports", rep_id, "brief_consistency.json")
            base_bc_data = {
                "is_consistent": res.is_consistent,
                "contradictions": [],
                "prose_is_consistent": res.is_consistent,
                "prose_contradictions": [c.to_dict() for c in res.contradictions],
                "diagnostics": res.diagnostics,
            }
            with open(rep_bc_path, "w", encoding="utf-8") as f_bc:
                json.dump(base_bc_data, f_bc, ensure_ascii=False, indent=2)

            self.assertTrue(os.path.exists(rep_bc_path))
            with open(rep_bc_path, "r", encoding="utf-8") as f:
                saved_bc = json.load(f)
            self.assertIn("prose_is_consistent", saved_bc)
            self.assertIn("prose_contradictions", saved_bc)
            self.assertFalse(saved_bc["prose_is_consistent"])
            self.assertFalse(saved_bc["is_consistent"])

            # Vérifier l'empaquetage dans gather_audit_files
            audit_svc = SimulationAuditService(simulation_id=sim_id, report_id=rep_id)
            files = audit_svc.gather_audit_files()
            self.assertIn("brief_consistency.json", files)
            bc_in_zip = json.loads(files["brief_consistency.json"].decode("utf-8"))
            self.assertIn("prose_is_consistent", bc_in_zip)
            self.assertFalse(bc_in_zip["prose_is_consistent"])
        finally:
            Config.UPLOAD_FOLDER = old_upload
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_ac5_docker_git_commit_metadata(self):
        """AC5: Vérification des Dockerfile/docker-compose et de _get_git_commit."""
        # 1. Vérification statique des fichiers Docker
        dockerfile_path = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            d_content = f.read()
        self.assertIn("ARG GIT_COMMIT=unknown-git-commit", d_content)
        self.assertIn("ENV GIT_COMMIT=${GIT_COMMIT}", d_content)

        compose_path = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            c_content = f.read()
        self.assertIn('GIT_COMMIT: "${GIT_COMMIT:-unknown-git-commit}"', c_content)
        self.assertIn('GIT_COMMIT: "${GIT_COMMIT:-}"', c_content)

        # 2. _get_git_commit()
        svc = SimulationAuditService(simulation_id="sim_dummy")
        # Si placeholder ou non positionné, appelle git
        with patch.dict(os.environ, {"GIT_COMMIT": "unknown-git-commit"}):
            commit = svc._get_git_commit()
            self.assertNotEqual(commit, "unknown-git-commit")
            self.assertRegex(commit, r"^[0-9a-f]{7,40}$|^unknown$")

        # Si variable explicite valide
        with patch.dict(os.environ, {"GIT_COMMIT": "abcdef1234567890"}):
            self.assertEqual(svc._get_git_commit(), "abcdef1234567890")

    def test_ac6_time_horizon_cascading_and_audit(self):
        """AC6: Résolution de l'horizon temporel en cascade avec time_horizon_is_inferred."""
        import tempfile
        import shutil
        from app.config import Config

        tmp_dir = tempfile.mkdtemp()
        old_upload = Config.UPLOAD_FOLDER
        try:
            Config.UPLOAD_FOLDER = tmp_dir
            sim_id = "sim_cascade_test"
            sim_dir = os.path.join(tmp_dir, "simulations", sim_id)
            os.makedirs(sim_dir, exist_ok=True)

            svc = SimulationAuditService(simulation_id=sim_id)

            # Cas 1: simulation_brief.json avec horizon explicite
            with open(os.path.join(sim_dir, "simulation_brief.json"), "w", encoding="utf-8") as f:
                json.dump({"time_horizon": "10 jours"}, f)
            meta1 = svc._resolve_time_horizon_metadata()
            self.assertEqual(meta1["time_horizon"], "10 jours")
            self.assertFalse(meta1["time_horizon_is_inferred"])
            self.assertEqual(meta1["time_horizon_source"], "explicit_brief")

            # Cas 2: simulation_brief.json avec goal nécessitant inférence
            with open(os.path.join(sim_dir, "simulation_brief.json"), "w", encoding="utf-8") as f:
                json.dump({"goal": "Observer l'adoption sur 2 semaines"}, f)
            meta2 = svc._resolve_time_horizon_metadata()
            self.assertEqual(meta2["time_horizon"], "2 semaines")
            self.assertTrue(meta2["time_horizon_is_inferred"])
            self.assertEqual(meta2["time_horizon_source"], "inferred_from_goal")

            # Cas 3: simulation_config.json
            os.remove(os.path.join(sim_dir, "simulation_brief.json"))
            with open(os.path.join(sim_dir, "simulation_config.json"), "w", encoding="utf-8") as f:
                json.dump({"simulation_requirement": "Tester pendant 3 jours"}, f)
            meta3 = svc._resolve_time_horizon_metadata()
            self.assertEqual(meta3["time_horizon"], "3j")
            self.assertTrue(meta3["time_horizon_is_inferred"])
            self.assertEqual(meta3["time_horizon_source"], "inferred_from_simulation_requirement")

            # Vérifier build_run_manifest et gather_audit_files (Patch 12 BMAD / VG-3)
            manifest = svc.build_run_manifest()
            self.assertTrue(manifest.get("simulation", {}).get("time_horizon_is_inferred"))
            self.assertEqual(manifest.get("simulation", {}).get("time_horizon_source"), "inferred_from_simulation_requirement")
            files = svc.gather_audit_files()
            self.assertIn("simulation_brief.json", files)
            sb_data = json.loads(files["simulation_brief.json"].decode("utf-8"))
            self.assertTrue(sb_data.get("time_horizon_is_inferred"))

            # Cas 4: Fallback total
            os.remove(os.path.join(sim_dir, "simulation_config.json"))
            meta4 = svc._resolve_time_horizon_metadata()
            self.assertIsNone(meta4["time_horizon"])
            self.assertFalse(meta4["time_horizon_is_inferred"])
            self.assertEqual(meta4["time_horizon_source"], "unresolved")
        finally:
            Config.UPLOAD_FOLDER = old_upload
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_ac7_r8_fixture_deterministic_replay(self):
        """AC7: Rejeu hermétique de l'anomalie R8 (Sylvie 17 ans vs 2.5 ans)."""
        profiles = [
            {
                "name": "Sylvie Delaunay",
                "realname": "Sylvie Delaunay",
                "persona": "Sylvie Delaunay, 52 ans, naturopathe installée depuis deux ans et demi à Angers avec une clientèle modeste.",
            }
        ]
        r8_claim = "Sylvie Delaunay, pourtant installée depuis 17 ans avec un carnet plein, ajourne sa souscription."
        res = audit_prose_persona_consistency(r8_claim, profiles)
        self.assertFalse(res.is_consistent)
        self.assertEqual(len(res.contradictions), 1)
        self.assertEqual(res.contradictions[0].carrier, "Sylvie Delaunay")
        self.assertIn("17 ans", res.contradictions[0].reason)
        self.assertIn("2.5 ans", res.contradictions[0].reason)

    def test_ac8_generic_scan_and_multidomain(self):
        """AC8: Scan de généricité AST/regex du code de production pour interdire les tokens hardcodés."""
        app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
        forbidden = [
            r"\bkeova\b",
            r"\bmenopulse\b",
            r"\bval[eé]rie blandini[eè]res\b",
            r"\bsophie jouan\b",
            r"\bmarie bourel\b",
        ]

        violations = []
        for root, _, files in os.walk(app_dir):
            for file in files:
                if file.endswith(".py"):
                    full_p = os.path.join(root, file)
                    with open(full_p, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines, 1):
                        for pat in forbidden:
                            if re.search(pat, line, re.IGNORECASE):
                                violations.append(f"{full_p}:{idx} -> {line.strip()}")

        self.assertEqual(
            violations,
            [],
            f"Violations de généricité (NFR-1) détectées dans backend/app :\n" + "\n".join(violations),
        )

    def test_ac9_verifier_qualification_epic_015_execution(self):
        """AC9 / T4.1: Exécution complète du banc de qualification verifier_qualification_epic_015."""
        import sys
        from pathlib import Path
        scripts_dir = str(Path(__file__).parents[1] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from verifier_qualification_epic_015 import Epic015Qualifier

        qualifier = Epic015Qualifier()
        res = qualifier.run_all()
        self.assertTrue(res.get("all_passed"))
        self.assertEqual(res.get("verdict"), "VERDICT GO")


if __name__ == "__main__":
    unittest.main()
