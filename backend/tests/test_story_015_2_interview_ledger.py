# -*- coding: utf-8 -*-
"""Suite de tests unitaires hermétiques pour la Story 015-2.

Journal d'entretiens structuré par répondant et authentification des citations d'entretien.
Couvre AC1 à AC9 dans 9 tests hermétiques sans appel réseau ni modèle externe.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest

from app.models.cohort_coverage import AgentIdentityResolver
from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.provenance_regime import ProvenanceRegime
from app.models.report_claim import (
    ClaimKind,
    InformationOrigin,
    ReportClaim,
    VerificationStatus,
)
from app.models.report_interviews import (
    InterviewQuoteSpan,
    InterviewSession,
    InterviewTurn,
    ReportInterviewsPayload,
    extract_quote_spans_from_answer,
    sanitize_interview_text,
)
from app.services.report_agent import ReportAgent, ReportManager
from app.services.simulation_action_verifier import SimulationActionVerifier
from app.services.simulation_audit_service import SimulationAuditService
from app.services.zep_tools import AgentInterview, InterviewResult, ZepToolsService


def test_report_interviews_v2_schema_and_exact_quote_offsets(tmp_path):
    """AC1 : Schéma v2 par session, tour et répondant avec offsets exacts.

    Invariant vérifié : answer_text[char_start:char_end] == quote pour 100 % des key_quotes.
    """
    answer_text = (
        "Je trouve le projet très prometteur pour notre équipe. "
        "En revanche, le tarif de 49 € par mois me paraît excessif pour une petite structure. "
        "Nous attendrons une offre plus accessible."
    )
    candidates = [
        "le tarif de 49 € par mois me paraît excessif",
        "projet très prometteur",
        "phrase inexistante dans la réponse",
    ]
    spans = extract_quote_spans_from_answer(answer_text, candidates)
    assert len(spans) == 2
    for s in spans:
        assert 0 <= s.char_start < s.char_end <= len(answer_text)
        assert answer_text[s.char_start:s.char_end] == s.quote

    turn1 = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t01",
        turn_index=1,
        agent_id=14,
        persona_name="Nathalie",
        question="Que pensez-vous du tarif proposé ?",
        answer_text=answer_text,
        key_quotes=spans,
    )
    assert turn1.turn_id == "ivw_01_a8f3c21b_t01"
    assert turn1.agent_id == 14

    session = InterviewSession(
        interview_id="ivw_01_a8f3c21b",
        session_index=1,
        subject="Évaluation tarifaire",
        questions=["Que pensez-vous du tarif proposé ?"],
        mode="replay_frozen",
        recorded_at="2026-10-29T12:00:00Z",
        turns=[turn1],
    )
    payload = ReportInterviewsPayload(
        simulation_id="sim_test_015_2",
        report_id="report_015_2",
        sessions=[session],
        schema_version="2.0",
    )
    file_path = str(tmp_path / "report_interviews.json")
    payload.save_to_file(file_path)

    reloaded = ReportInterviewsPayload.load_from_file(file_path)
    assert reloaded is not None
    assert reloaded.schema_version == "2.0"
    assert len(reloaded.sessions) == 1
    sess = reloaded.sessions[0]
    assert sess.interview_id == "ivw_01_a8f3c21b"
    assert sess.mode == "replay_frozen"
    assert len(sess.turns) == 1
    t0 = sess.turns[0]
    assert t0.turn_id == "ivw_01_a8f3c21b_t01"
    assert t0.persona_name == "Nathalie"
    assert t0.agent_id == 14
    assert len(t0.key_quotes) == 2
    for q in t0.key_quotes:
        assert t0.answer_text[q.char_start:q.char_end] == q.quote

    # Test d'erreur sur invariant violé
    with pytest.raises(ValueError, match="Invariant violé"):
        InterviewTurn(
            turn_id="ivw_01_a8f3c21b_t02",
            turn_index=2,
            agent_id=14,
            persona_name="Nathalie",
            question="Q?",
            answer_text="Bonjour tout le monde",
            key_quotes=[InterviewQuoteSpan(quote="Au revoir", char_start=0, char_end=9)],
        )


def test_interview_modes_honesty_and_canonical_respondent_resolution(monkeypatch):
    """AC2 : Honnêteté du mode effectif (live, offline_archive, replay_frozen) et résolution canonique.

    Sur des profils de type reddit_profiles.json (user_id + name sans realname),
    ZepToolsService enregistre l'agent_id et le persona_name canonique.
    """
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Réponse simulée de test pour le mode archives."
    service = ZepToolsService(llm_client=mock_llm)

    # Profils façon reddit_profiles.json sans realname
    reddit_profiles = [
        {
            "user_id": 962,
            "name": "Nathalie",
            "username": "nathalie_962",
            "profession": "Architecte",
            "bio": "Bio Nathalie",
        },
        {
            "user_id": 927,
            "name": "Florence",
            "username": "florence_927",
            "profession": "Médecin",
            "bio": "Bio Florence",
        },
    ]

    monkeypatch.setattr(service, "_load_agent_profiles", lambda sid: reddit_profiles)
    monkeypatch.setattr(
        service,
        "_select_agents_for_interview",
        lambda profiles, interview_requirement, simulation_requirement, max_agents: (profiles, [0, 1], "Sélection pour test"),
    )
    monkeypatch.setattr(
        SimulationActionVerifier,
        "load_simulation_actions",
        lambda self, sid=None, sim_dir=None: [],
    )

    # SimulationRunner simulant une ValueError (environnement non disponible -> repli offline_archive)
    from app.services.simulation_runner import SimulationRunner

    def _mock_batch_error(**kwargs):
        raise ValueError("OASIS arrêté")

    monkeypatch.setattr(
        SimulationRunner,
        "interview_agents_batch",
        _mock_batch_error,
    )

    # 1. Mode par défaut démarrant à live mais basculant en offline_archive
    res_offline = service.interview_agents(
        simulation_id="sim_offline",
        interview_requirement="Question de test ?",
        max_agents=2,
        replay_mode="live",
    )
    assert res_offline.replay_mode == "offline_archive"
    assert "[[PROVENANCE:interview;mode:offline_archive]]" in res_offline.to_text()
    assert len(res_offline.interviews) == 2
    assert res_offline.interviews[0].agent_name == "Nathalie"
    assert res_offline.interviews[0].agent_id == 962
    assert res_offline.interviews[1].agent_name == "Florence"
    assert res_offline.interviews[1].agent_id == 927

    # 2. Mode replay_frozen reste replay_frozen
    res_frozen = service.interview_agents(
        simulation_id="sim_frozen",
        interview_requirement="Question de test ?",
        max_agents=2,
        replay_mode="replay_frozen",
    )
    assert res_frozen.replay_mode == "replay_frozen"
    assert "[[PROVENANCE:interview;mode:replay_frozen]]" in res_frozen.to_text()

    # 3. Mode live avec batch réussi
    monkeypatch.setattr(
        SimulationRunner,
        "interview_agents_batch",
        lambda **kwargs: {
            "success": True,
            "result": {
                "results": {
                    "twitter_0": {"response": "Avis Twitter live."},
                    "reddit_0": {"response": "Avis Reddit live."},
                }
            },
        },
    )
    res_live = service.interview_agents(
        simulation_id="sim_live",
        interview_requirement="Question de test ?",
        max_agents=1,
        replay_mode="live",
    )
    assert res_live.replay_mode == "live"
    assert "[[PROVENANCE:interview;mode:live]]" in res_live.to_text()
    assert res_live.interviews[0].agent_name == "Nathalie"
    assert res_live.interviews[0].agent_id == 962


def test_v1_backward_compatibility_and_corrupted_file_resilience(tmp_path):
    """AC3 : Compatibilité ascendante de lecture v1 et tolérance aux fichiers absents/corrompus (NFR-1)."""
    # 1. Liste racine historique v1 (format R8)
    v1_list = [
        {
            "subject": "Évaluation tarifaire",
            "agents": ["nathalie_962", "florence_927"],
            "mode": "live",
            "citations": ["Citation A", "Citation B"],
        }
    ]
    p_v1 = ReportInterviewsPayload.from_raw(v1_list, simulation_id="sim_v1", report_id="rep_v1")
    assert len(p_v1.sessions) == 1
    assert p_v1.sessions[0].subject == "Évaluation tarifaire"
    assert p_v1.sessions[0].legacy_agents == ["nathalie_962", "florence_927"]
    assert p_v1.sessions[0].legacy_citations == ["Citation A", "Citation B"]

    # 2. Enveloppe de repli historique {"report_id": "...", "interviews": [...]}
    v1_env = {
        "report_id": "rep_v1_env",
        "interviews": [
            {
                "subject": "Feedback produit",
                "agents": ["Simon"],
                "mode": "offline_archive",
                "citations": ["Citation Simon"],
            }
        ],
    }
    p_env = ReportInterviewsPayload.from_raw(v1_env, simulation_id="sim_env")
    assert len(p_env.sessions) == 1
    assert p_env.sessions[0].subject == "Feedback produit"

    # 3. Format ad-hoc de test unitaires {"interviewee", "transcript"}
    v1_adhoc = [
        {
            "interviewee": "Marie",
            "transcript": "J'utilise le service tous les matins avec satisfaction.",
        }
    ]
    p_adhoc = ReportInterviewsPayload.from_raw(v1_adhoc, simulation_id="sim_adhoc", report_id="rep_adhoc")
    assert len(p_adhoc.sessions) == 1
    assert len(p_adhoc.sessions[0].turns) == 1
    turn = p_adhoc.sessions[0].turns[0]
    assert turn.persona_name == "Marie"
    assert "J'utilise le service tous les matins" in turn.answer_text

    # 4. Fichier absent, vide ou corrompu
    missing_path = str(tmp_path / "non_existent.json")
    assert ReportInterviewsPayload.load_from_file(missing_path) is None

    empty_path = str(tmp_path / "empty.json")
    with open(empty_path, "w") as f:
        f.write("   \n")
    assert ReportInterviewsPayload.load_from_file(empty_path) is None

    corrupted_path = str(tmp_path / "corrupted.json")
    with open(corrupted_path, "w") as f:
        f.write("{invalid_json: true,")
    assert ReportInterviewsPayload.load_from_file(corrupted_path) is None


def test_authentic_respondent_interview_quote_verified_with_turn_id():
    """AC4 : Authentification VERIFIED d'une citation d'entretien du bon répondant avec turn_id.

    Garantit le maintien strict de REPORTED_INTENTION, INFERENCE, asserted_as_action=False.
    """
    turn_alice = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t01",
        turn_index=1,
        agent_id=1,
        persona_name="Alice",
        question="Quel est votre ressenti ?",
        answer_text="Je trouve la nouvelle interface très claire et intuitive.",
        key_quotes=[],
    )
    session = InterviewSession(
        interview_id="ivw_01_a8f3c21b",
        session_index=1,
        subject="Ergonomie",
        questions=["Quel est votre ressenti ?"],
        mode="replay_frozen",
        recorded_at="2026-10-29T12:00:00Z",
        turns=[turn_alice],
    )
    payload = ReportInterviewsPayload(
        simulation_id="sim_auth",
        report_id="rep_auth",
        sessions=[session],
    )

    # 1. Citation entre guillemets sous régime INTERVIEW
    claim1 = ReportClaim(
        claim_id="clm_ivw_1",
        text='Alice précise : « Je trouve la nouvelle interface très claire » lors de son entretien.',
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.INFERENCE,
        agent_name="Alice",
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    res1 = SimulationActionVerifier.verify_report_claim(
        claim=claim1,
        report_interviews=payload,
    )
    assert res1.verification_status == VerificationStatus.VERIFIED
    assert "ivw_01_a8f3c21b_t01" in res1.evidence_refs
    assert res1.claim_kind == ClaimKind.REPORTED_INTENTION
    assert res1.origin == InformationOrigin.INFERENCE
    assert res1.provenance_regime == ProvenanceRegime.INTERVIEW
    assert res1.asserted_as_action is False

    # 2. Rattrapage d'une citation d'entretien initialement sous régime UNKNOWN
    claim2 = ReportClaim(
        claim_id="clm_ivw_2",
        text='Alice a souligné : « très claire et intuitive » dans ses retours.',
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.INFERENCE,
        agent_name="Alice",
        provenance_regime=ProvenanceRegime.UNKNOWN,
    )
    res2 = SimulationActionVerifier.verify_report_claim(
        claim=claim2,
        report_interviews=payload,
    )
    assert res2.verification_status == VerificationStatus.VERIFIED
    assert "ivw_01_a8f3c21b_t01" in res2.evidence_refs
    assert res2.provenance_regime == ProvenanceRegime.INTERVIEW

    # 3. Déclaration 8-grammes sans guillemets sous régime INTERVIEW
    claim3 = ReportClaim(
        claim_id="clm_ivw_3",
        text="Alice affirme que je trouve la nouvelle interface très claire et intuitive.",
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.INFERENCE,
        agent_name="Alice",
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    res3 = SimulationActionVerifier.verify_report_claim(
        claim=claim3,
        report_interviews=payload,
    )
    assert res3.verification_status == VerificationStatus.VERIFIED
    assert "ivw_01_a8f3c21b_t01" in res3.evidence_refs


def test_misattributed_interview_quote_to_wrong_respondent_contradicted():
    """AC5 : Détection CONTRADICTED d'une citation attribuée au mauvais répondant."""
    turn_bob = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t02",
        turn_index=2,
        agent_id=2,
        persona_name="Bob",
        question="Votre avis ?",
        answer_text="Je refuse catégoriquement d'utiliser cette solution sans audit externe préalable.",
        key_quotes=[],
    )
    session = InterviewSession(
        interview_id="ivw_01_a8f3c21b",
        session_index=1,
        subject="Audit sécurité",
        questions=["Votre avis ?"],
        mode="live",
        recorded_at="2026-10-29T12:00:00Z",
        turns=[turn_bob],
    )
    payload = ReportInterviewsPayload(
        simulation_id="sim_contra",
        report_id="rep_contra",
        sessions=[session],
    )

    # Alice s'attribue la citation de Bob
    claim_misattributed = ReportClaim(
        claim_id="clm_mis",
        text='Alice indique : « Je refuse catégoriquement d\'utiliser cette solution » en entretien.',
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.INFERENCE,
        agent_name="Alice",
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    res = SimulationActionVerifier.verify_report_claim(
        claim=claim_misattributed,
        report_interviews=payload,
    )
    assert res.verification_status == VerificationStatus.CONTRADICTED
    assert res.confidence == 0.0
    assert res.evidence_refs == []
    assert res.provenance_regime == ProvenanceRegime.INTERVIEW
    assert res.asserted_as_action is False
    assert any("Bob" in lim for lim in res.limitations)
    assert any("ivw_01_a8f3c21b_t02" in lim for lim in res.limitations)


def test_altered_or_fabricated_interview_quote_marked_unsupported():
    """AC6 : Rejet UNSUPPORTED d'une citation d'entretien altérée, fabriquée ou à ivw_* introuvable."""
    turn_claire = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t03",
        turn_index=3,
        agent_id=3,
        persona_name="Claire",
        question="Quel tarif ?",
        answer_text="Le tarif de 29 € par mois me paraît convenable pour démarrer.",
        key_quotes=[],
    )
    session = InterviewSession(
        interview_id="ivw_01_a8f3c21b",
        session_index=1,
        subject="Tarifs",
        questions=["Quel tarif ?"],
        mode="replay_frozen",
        recorded_at="2026-10-29T12:00:00Z",
        turns=[turn_claire],
    )
    payload = ReportInterviewsPayload(
        simulation_id="sim_unsupported",
        report_id="rep_unsupported",
        sessions=[session],
    )

    # 1. Altération numérique (29 € -> 49 €)
    claim_altered = ReportClaim(
        claim_id="clm_alt",
        text='Claire déclare : « Le tarif de 49 € par mois me paraît convenable » en entretien.',
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.INFERENCE,
        agent_name="Claire",
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    res1 = SimulationActionVerifier.verify_report_claim(
        claim=claim_altered,
        report_interviews=payload,
    )
    assert res1.verification_status == VerificationStatus.UNSUPPORTED
    assert res1.evidence_refs == []
    assert res1.asserted_as_action is False
    assert any("altération" in lim.lower() for lim in res1.limitations)

    # 2. Référence ivw_* inexistante
    claim_bad_ref = ReportClaim(
        claim_id="clm_bad_ref",
        text="Claire a confirmé son accord lors de l'entretien ivw_99_fake_t01.",
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.INFERENCE,
        evidence_refs=["ivw_99_fake_t01"],
        agent_name="Claire",
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    res2 = SimulationActionVerifier.verify_report_claim(
        claim=claim_bad_ref,
        report_interviews=payload,
    )
    assert res2.verification_status == VerificationStatus.UNSUPPORTED
    assert res2.evidence_refs == []
    assert any("introuvable" in lim.lower() for lim in res2.limitations)


def test_interview_never_promoted_to_action_and_never_whitewashes_unverified_action():
    """AC7 : Interdiction de promotion en action OASIS et non-blanchiment d'action affirmée non exécutée."""
    turn_claire = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t01",
        turn_index=1,
        agent_id=3,
        persona_name="Claire",
        question="Avez-vous publié ?",
        answer_text="J'ai publié un message de soutien sur Twitter hier soir.",
        key_quotes=[],
    )
    session = InterviewSession(
        interview_id="ivw_01_a8f3c21b",
        session_index=1,
        subject="Activité",
        questions=["Avez-vous publié ?"],
        mode="replay_frozen",
        recorded_at="2026-10-29T12:00:00Z",
        turns=[turn_claire],
    )
    payload = ReportInterviewsPayload(
        simulation_id="sim_no_promo",
        report_id="rep_no_promo",
        sessions=[session],
    )

    # Action sociale affirmée dans la simulation (asserted_as_action=True)
    # n'ayant AUCUN événement OASIS exécuté correspondant dans evidence_pack.
    claim_unexecuted_action = ReportClaim(
        claim_id="clm_act_fail",
        text='Claire a publié sur Twitter : « J\'ai publié un message de soutien sur Twitter hier soir. »',
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Claire",
        provenance_regime=ProvenanceRegime.EVENT,
        asserted_as_action=True,
    )
    pack_empty = EvidencePack(simulation_id="sim_no_promo", events=[])

    res = SimulationActionVerifier.verify_report_claim(
        claim=claim_unexecuted_action,
        evidence_pack=pack_empty,
        report_interviews=payload,
    )
    # L'affirmation d'action ne doit PAS être validée par la réponse d'entretien !
    assert res.verification_status == VerificationStatus.UNSUPPORTED
    assert res.asserted_as_action is True
    assert res.evidence_refs == []
    assert res.claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION  # Déclassé en REPORTED_INTENTION C4


def test_persistence_order_zero_interview_envelope_and_snapshot_isolation(tmp_path, monkeypatch):
    """AC8 : Persistance atomique avant audit, cas 0 entretien et isolation EvidenceSnapshotService."""
    upload_dir = str(tmp_path / "uploads")
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", upload_dir)

    sim_id = "sim_test_order"
    rep_id = "rep_test_order"

    agent = ReportAgent(
        simulation_id=sim_id,
        graph_id="graph_test_order",
        simulation_requirement="Test requirement",
    )
    agent.replay_mode = "replay_frozen"
    agent._current_report_id = rep_id

    # 1. Simuler 0 entretien via l'agent : l'agent doit persister l'enveloppe sessions: []
    ReportManager._ensure_report_folder(rep_id)
    interviews_path = ReportManager._get_report_interviews_path(rep_id)

    # Exécuter l'audit via l'agent pour vérifier que l'agent écrit le fichier sur disque
    agent.audit_and_save_report_claims(
        markdown_content="# Rapport de test\n\nAucun entretien mené.",
        report_id=rep_id,
    )

    assert os.path.exists(interviews_path)
    loaded_zero = ReportInterviewsPayload.load_from_file(interviews_path)
    assert loaded_zero is not None
    assert loaded_zero.schema_version == "2.0"
    assert loaded_zero.sessions == []

    # 2. Vérifier que SimulationAuditService inclut report_interviews.json v2
    audit_service = SimulationAuditService(simulation_id=sim_id, report_id=rep_id)
    files = audit_service.gather_audit_files()
    assert "report_interviews.json" in files
    content = json.loads(files["report_interviews.json"].decode("utf-8"))
    assert content.get("schema_version") == "2.0"

    # 3. Vérifier que EvidenceSnapshotService n'inclut PAS report_interviews.json
    from app.services.evidence_snapshot_service import EvidenceSnapshotService
    assert "report_interviews.json" not in EvidenceSnapshotService.CANONICAL_AUDIT_FILES


def test_report_interviews_sanitizes_secrets_and_excludes_system_prompts():
    """AC9 : Zéro fuite de secret ni de prompt système interne dans report_interviews.json (NFR-4)."""
    raw_response = (
        "Voici mon retour. Attention à ne pas partager mon jeton Bearer 1234567890abcdef123456 "
        "ni la clé sk-ABCDEFGHIJKLMNOP1234567890. "
        "La base est accessible sur https://user:secretpass@private.db.internal/path. "
        "Je confirme que nous déployons la solution la semaine prochaine."
    )
    sanitized = sanitize_interview_text(raw_response)
    assert "Bearer" not in sanitized
    assert "1234567890abcdef123456" not in sanitized
    assert "sk-" not in sanitized
    assert "secretpass" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized

    candidate_quotes = ["Je confirme que nous déployons la solution la semaine prochaine."]
    spans = extract_quote_spans_from_answer(sanitized, candidate_quotes)
    assert len(spans) == 1

    turn = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t01",
        turn_index=1,
        agent_id=10,
        persona_name="Admin",
        question="Quelle est la clé API sk-ABCDEF1234567890 ?",
        answer_text=raw_response,
        key_quotes=spans,
    )
    turn_dict = turn.to_dict()
    assert "sk-ABCDEF1234567890" not in turn_dict["question"]
    assert "sk-ABCDEFGHIJKLMNOP1234567890" not in turn_dict["answer_text"]
    assert "secretpass" not in turn_dict["answer_text"]
    assert "[REDACTED_SECRET]" in turn_dict["answer_text"]

    # Roundtrip from_dict vérifiant que __post_init__ valide l'invariant sans ValueError
    reloaded_turn = InterviewTurn.from_dict(turn_dict)
    assert reloaded_turn.turn_id == "ivw_01_a8f3c21b_t01"
    assert len(reloaded_turn.key_quotes) == 1
    assert reloaded_turn.answer_text[reloaded_turn.key_quotes[0].char_start:reloaded_turn.key_quotes[0].char_end] == reloaded_turn.key_quotes[0].quote


def test_session_level_reference_multi_respondents():
    """Vérifier qu'une référence de session ivw_NN_hash n'émet pas de faux CONTRADICTED pour le 2e répondant."""
    turn_1 = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t01",
        turn_index=1,
        agent_id=1,
        persona_name="Alice",
        question="Q1",
        answer_text="Je soutiens ce projet à 100 %.",
        key_quotes=[InterviewQuoteSpan("Je soutiens ce projet à 100 %.", 0, 30)],
    )
    turn_2 = InterviewTurn(
        turn_id="ivw_01_a8f3c21b_t02",
        turn_index=2,
        agent_id=2,
        persona_name="Bob",
        question="Q2",
        answer_text="Je préfère attendre avant de décider.",
        key_quotes=[InterviewQuoteSpan("Je préfère attendre avant de décider.", 0, 37)],
    )
    session = InterviewSession(
        interview_id="ivw_01_a8f3c21b",
        session_index=1,
        subject="Tour de table",
        questions=["Q1", "Q2"],
        mode="live",
        recorded_at="2026-10-29T10:00:00Z",
        turns=[turn_1, turn_2],
    )
    payload = ReportInterviewsPayload(
        simulation_id="sim_multi",
        report_id="rep_multi",
        sessions=[session],
    )

    # Claim pour Bob citant la référence de session ivw_01_a8f3c21b
    claim_bob = ReportClaim(
        claim_id="clm_bob",
        text="Bob a déclaré en entretien : « Je préfère attendre avant de décider. » (ivw_01_a8f3c21b)",
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.INFERENCE,
        agent_name="Bob",
        evidence_refs=["ivw_01_a8f3c21b"],
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    res = SimulationActionVerifier.verify_interview_citation(claim_bob, payload)
    assert res is not None
    assert res.verification_status == VerificationStatus.VERIFIED
    assert "ivw_01_a8f3c21b_t02" in res.evidence_refs


def test_report_agent_execute_tool_populates_interview_sessions(tmp_path, monkeypatch):
    """Vérifier que _execute_tool_impl pour interview_agents peuple self._interview_sessions."""
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))

    from app.services.zep_tools import InterviewResult, AgentInterview

    agent = ReportAgent(simulation_id="sim_exec", graph_id="graph_exec", simulation_requirement="Test requirement")
    agent._current_report_id = "rep_exec"

    mock_interview = AgentInterview(
        agent_name="Claire",
        agent_role="Ingénieure",
        agent_bio="Bio",
        question="Votre avis ?",
        response="Mon avis est très favorable sur cette architecture.",
        key_quotes=["Mon avis est très favorable"],
        agent_id=42,
    )
    mock_result = InterviewResult(
        interview_topic="Architecture",
        interview_questions=["Votre avis ?"],
        interviews=[mock_interview],
    )
    mock_result.replay_mode = "live"

    import unittest.mock as mock
    agent.zep_tools.interview_agents = mock.MagicMock(return_value=mock_result)

    out = agent._execute_tool_impl("interview_agents", {"agent_roles": ["Ingénieure"], "interview_requirement": "Architecture", "interview_topic": "Architecture"})
    assert "Mon avis est très favorable" in out
    assert len(agent._interview_sessions) == 1
    sess = agent._interview_sessions[0]
    assert sess.subject == "Architecture"
    assert sess.mode == "live"
    assert len(sess.turns) == 1
    assert sess.turns[0].agent_id == 42
    assert sess.turns[0].persona_name == "Claire"


def test_extract_claims_from_content_with_ivw_reference():
    """Vérifier que extract_claims_from_content capture ivw_* en evidence_refs et force INTERVIEW."""
    agent = ReportAgent(simulation_id="sim_ext", graph_id="graph_ext", simulation_requirement="Test requirement")
    markdown = (
        "## Résultats\n\n"
        "Lors de son entretien, Claire a souligné : « Nous serons prêts » (ivw_01_a8f3c21b_t01).\n"
    )
    claims = agent.extract_claims_from_content(markdown)
    assert len(claims) >= 1
    found_ivw = [c for c in claims if "ivw_01_a8f3c21b_t01" in c.evidence_refs]
    assert len(found_ivw) == 1
    assert found_ivw[0].provenance_regime == ProvenanceRegime.INTERVIEW
    assert found_ivw[0].asserted_as_action is False
