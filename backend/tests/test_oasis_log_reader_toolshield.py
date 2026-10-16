"""Tests hermétiques pour OasisLogReaderService, EvidencePack, ToolShield et assignation Round 0 (Story 011-2).

Couvre exhaustivement :
  - AC1 : Modèle EvidencePack et ObservedEvent (instanciation, sérialisation, to_text, immutabilité).
  - AC2 : Service OasisLogReaderService (parsing JSONL multi-plateformes, traces SQLite, stabilité des event_id, invalidation mtime).
  - AC3 : Outil query_simulation_events dans ReportAgent / ZepToolsService (recherche multi-critères, formatage textuel).
  - AC4 : Bouclier ToolShield (interception des paramètres vides, injection de repli contextuel, résilience aux erreurs de store, zéro burn d'itérations).
  - AC5 : Déterminisme nominatif de l'assignation Round 0 dans SimulationConfigGenerator (élimination des inversions type Keova : Émilie, Sylvie, Christine).
  - AC6 : Distinction stricte entre action réelle observée et intention verbale.
  - AC7 : Maintien de l'intégrité et non-régression.
"""

import json
import os
import sqlite3
import pytest

from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.services.oasis_log_reader import OasisLogReaderService
from app.services.tool_shield import ToolShield
from app.services.simulation_action_verifier import SimulationActionVerifier
from app.services.simulation_config_generator import (
    SimulationConfigGenerator,
    EventConfig,
    AgentActivityConfig,
)
from app.services.zep_tools import ZepToolsService
from app.utils.graph_store import GraphValidationError


# ============================================================================
# AC1 : Tests du modèle EvidencePack et ObservedEvent
# ============================================================================

def test_observed_event_creation_and_immutability():
    """Vérifie l'instanciation, l'immutabilité et la sérialisation d'ObservedEvent."""
    event = ObservedEvent(
        event_id="evt_twitter_1_10_abcdef1234567890",
        simulation_id="sim_123",
        platform="twitter",
        round_num=1,
        agent_id=10,
        agent_name="Émilie Martin",
        action_type="post",
        timestamp="2026-10-16T12:00:00Z",
        action_args={"content": "Je teste la simulation"},
        is_action_executed=True,
        result="Success",
        success=True,
    )
    assert event.event_id == "evt_twitter_1_10_abcdef1234567890"
    assert event.is_action_executed is True

    # Immutabilité (dataclass frozen)
    with pytest.raises(Exception):
        event.round_num = 2  # type: ignore

    d = event.to_dict()
    assert d["simulation_id"] == "sim_123"
    assert d["agent_name"] == "Émilie Martin"
    assert d["action_type"] == "post"

    restored = ObservedEvent.from_dict(d)
    assert restored.event_id == event.event_id
    assert restored.agent_name == event.agent_name
    assert restored.action_args == event.action_args


def test_evidence_pack_statistics_and_filtering():
    """Vérifie le calcul des statistiques et le filtrage multi-critères dans EvidencePack."""
    e1 = ObservedEvent(
        event_id="evt_twitter_1_1_1111",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Émilie",
        action_type="post",
        timestamp="2026-10-16T10:00:00Z",
        action_args={"content": "Avis sur les tarifs Keova"},
    )
    e2 = ObservedEvent(
        event_id="evt_reddit_1_2_2222",
        simulation_id="sim_test",
        platform="reddit",
        round_num=1,
        agent_id=2,
        agent_name="Sylvie",
        action_type="comment",
        timestamp="2026-10-16T10:05:00Z",
        action_args={"content": "Je réponds à la discussion"},
    )
    e3 = ObservedEvent(
        event_id="evt_twitter_2_1_3333",
        simulation_id="sim_test",
        platform="twitter",
        round_num=2,
        agent_id=1,
        agent_name="Émilie",
        action_type="like",
        timestamp="2026-10-16T10:10:00Z",
        action_args={"post_id": 42},
    )

    pack = EvidencePack.from_events("sim_test", [e1, e2, e3])

    assert pack.total_events == 3
    assert pack.events_by_platform == {"twitter": 2, "reddit": 1}
    assert pack.events_by_type == {"post": 1, "comment": 1, "like": 1}
    assert pack.events_by_agent == {"Émilie": 2, "Sylvie": 1}
    assert pack.rounds_range == [1, 2]

    # Filtrage par plateforme
    twitter_events = pack.filter_events(platform="twitter")
    assert len(twitter_events) == 2

    # Filtrage par agent_name
    sylvie_events = pack.filter_events(agent_name="Sylvie")
    assert len(sylvie_events) == 1
    assert sylvie_events[0].event_id == "evt_reddit_1_2_2222"

    # Filtrage textuel dans les action_args
    keova_events = pack.filter_events(query="Keova")
    assert len(keova_events) == 1
    assert keova_events[0].agent_name == "Émilie"

    # Vérification to_text
    summary_text = pack.to_text()
    assert "EvidencePack" in summary_text
    assert "Émilie" in summary_text
    assert "Sylvie" in summary_text


# ============================================================================
# AC2 : Tests du service OasisLogReaderService
# ============================================================================

def test_oasis_log_reader_extraction_jsonl_and_sqlite(tmp_path):
    """Vérifie le chargement conjoint des traces JSONL et SQLite avec stabilité d'event_id."""
    sim_dir = tmp_path / "simulations" / "sim_oasis_test"
    os.makedirs(sim_dir / "twitter", exist_ok=True)
    os.makedirs(sim_dir / "reddit", exist_ok=True)

    # 1. Écrire des actions JSONL
    twitter_actions = [
        {
            "action_type": "post",
            "round": 1,
            "agent_id": 101,
            "agent_name": "Alice",
            "timestamp": "2026-10-16T14:00:00Z",
            "action_args": {"content": "Premier tweet de test"},
        },
        {
            # Événement de cycle à ignorer
            "event_type": "round_start",
            "round": 1,
        },
    ]
    with open(sim_dir / "twitter" / "actions.jsonl", "w", encoding="utf-8") as f:
        for act in twitter_actions:
            f.write(json.dumps(act) + "\n")

    # 2. Créer une base SQLite twitter_simulation.db avec une table comment
    db_path = sim_dir / "twitter_simulation.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE comment (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            user_name TEXT,
            content TEXT,
            round INTEGER,
            created_at TEXT
        )
    """)
    cursor.execute("""
        INSERT INTO comment (id, user_id, user_name, content, round, created_at)
        VALUES (1, 102, 'Bob', 'Commentaire sous le post', 1, '2026-10-16T14:05:00Z')
    """)
    conn.commit()
    conn.close()

    service = OasisLogReaderService("sim_oasis_test")
    # Pointeur vers le dossier temporaire
    service.get_simulation_dir = lambda sim_id=None: str(sim_dir)

    events = service.load_events("sim_oasis_test", force_reload=True)
    assert len(events) == 2

    # Vérification des événements extraits
    post_ev = next(e for e in events if e.action_type == "post")
    assert post_ev.agent_name == "Alice"
    assert post_ev.platform == "twitter"
    assert post_ev.is_action_executed is True
    assert post_ev.event_id.startswith("evt_twitter_1_101_")

    comm_ev = next(e for e in events if e.action_type == "comment")
    assert comm_ev.agent_name == "Bob"
    assert comm_ev.platform == "twitter"
    assert comm_ev.is_action_executed is True
    assert comm_ev.event_id.startswith("evt_twitter_1_102_")

    # Vérification cache et stabilité
    events_cached = service.load_events("sim_oasis_test", force_reload=False)
    assert len(events_cached) == 2
    assert events_cached[0].event_id == events[0].event_id


def test_oasis_log_reader_query_events_filter(tmp_path):
    """Vérifie la méthode query_events avec filtrage par round et type."""
    sim_dir = tmp_path / "simulations" / "sim_query_test"
    os.makedirs(sim_dir, exist_ok=True)

    actions = [
        {"action_type": "post", "round": 0, "agent_id": 1, "timestamp": "t0", "action_args": {"content": "Init"}},
        {"action_type": "like", "round": 1, "agent_id": 2, "timestamp": "t1", "action_args": {"target": 1}},
        {"action_type": "post", "round": 2, "agent_id": 3, "timestamp": "t2", "action_args": {"content": "Final"}},
    ]
    with open(sim_dir / "actions.jsonl", "w", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps(a) + "\n")

    service = OasisLogReaderService("sim_query_test")
    service.get_simulation_dir = lambda sim_id=None: str(sim_dir)

    res_round2 = service.query_events(round_min=2)
    assert len(res_round2) == 1
    assert res_round2[0].round_num == 2

    res_post = service.query_events(action_type="post")
    assert len(res_post) == 2


# ============================================================================
# AC3 : Tests de l'outil query_simulation_events
# ============================================================================

def test_zep_tools_query_simulation_events(monkeypatch, tmp_path):
    """Vérifie l'exécution de query_simulation_events et son formatage textuel."""
    sim_dir = tmp_path / "simulations" / "sim_tool_test"
    os.makedirs(sim_dir, exist_ok=True)

    actions = [
        {
            "action_type": "boycott",
            "round": 3,
            "agent_id": 42,
            "agent_name": "Christine",
            "timestamp": "2026-10-16T15:00:00Z",
            "action_args": {"content": "Je boycotte formellement la marque"},
            "result": "success",
        }
    ]
    with open(sim_dir / "actions.jsonl", "w", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps(a) + "\n")

    monkeypatch.setattr(
        OasisLogReaderService,
        "get_simulation_dir",
        lambda self, sim_id=None: str(sim_dir),
    )

    zep_tools = ZepToolsService()
    text_result = zep_tools.query_simulation_events(
        simulation_id="sim_tool_test",
        query="boycotte",
        agent_name="Christine",
    )

    assert "【Événements observés de simulation" in text_result
    assert "Agent Christine -> Action: boycott" in text_result
    assert "evt_generic_3_42_" in text_result
    assert "Je boycotte formellement la marque" in text_result

    # Recherche sans résultat
    empty_res = zep_tools.query_simulation_events(
        simulation_id="sim_tool_test",
        query="introuvable_xyz",
    )
    assert "【Aucun événement observé correspondant】" in empty_res


# ============================================================================
# AC4 : Tests du bouclier ToolShield
# ============================================================================

def test_tool_shield_sanitize_empty_queries():
    """Vérifie que ToolShield intercepte les requêtes vides et injecte le repli adéquat."""
    # 1. quick_search avec query vide
    params, modified = ToolShield.sanitize_parameters(
        tool_name="quick_search",
        parameters={"query": ""},
        section_title="Impact sur les indépendants",
        simulation_requirement="Tarification Keova 2026",
    )
    assert modified is True
    assert params["query"] == "Impact sur les indépendants"

    # 2. panorama_search avec dictionnaire vide
    params, modified = ToolShield.sanitize_parameters(
        tool_name="panorama_search",
        parameters={},
        section_title="",
        simulation_requirement="Tarification Keova 2026",
    )
    assert modified is True
    assert params["query"] == "Tarification Keova 2026"

    # 3. interview_agents sans topic
    params, modified = ToolShield.sanitize_parameters(
        tool_name="interview_agents",
        parameters={},
        section_title="Analyse des réactions",
    )
    assert modified is True
    assert params["interview_topic"] == "Analyse des réactions"

    # 4. Requête déjà valide non modifiée
    params, modified = ToolShield.sanitize_parameters(
        tool_name="quick_search",
        parameters={"query": "Tarif pro"},
    )
    assert modified is False
    assert params["query"] == "Tarif pro"


def test_tool_shield_handles_store_validation_error():
    """Vérifie que ToolShield capture GraphValidationError et retourne une observation constructive."""
    def failing_executor(tool_name, params):
        raise GraphValidationError("Le texte de recherche query est requis")

    result = ToolShield.execute_with_shield(
        tool_name="quick_search",
        parameters={"query": "test"},
        executor=failing_executor,
    )
    assert "【ToolShield - Avertissement】" in result
    assert "Le texte de recherche query est requis" in result


# ============================================================================
# AC5 : Tests du déterminisme nominatif au Round 0
# ============================================================================

def test_simulation_config_generator_round0_nominative_assignment():
    """Vérifie l'assignation nominative stricte au Round 0 (C6, cas Keova : Émilie, Sylvie, Christine)."""
    generator = SimulationConfigGenerator()

    # Création d'agents de même type ("person") avec noms distincts
    agents = [
        AgentActivityConfig(agent_id=1, entity_uuid="u1", entity_name="Christine", entity_type="Person", influence_weight=0.9),
        AgentActivityConfig(agent_id=2, entity_uuid="u2", entity_name="Sylvie", entity_type="Person", influence_weight=0.8),
        AgentActivityConfig(agent_id=3, entity_uuid="u3", entity_name="Émilie", entity_type="Person", influence_weight=0.7),
    ]

    event_cfg = EventConfig(
        initial_posts=[
            {
                "content": "Je suis Émilie et je m'exprime sur le nouveau forfait.",
                "poster_type": "Person",
                "poster_persona": "Émilie",
            },
            {
                "content": "Avis de Sylvie : proposition intéressante.",
                "poster_type": "Person",
                "poster_persona": "Sylvie",
            },
            {
                "content": "En tant que Christine, je refuse ces conditions.",
                "poster_type": "Person",
                "poster_persona": "Christine",
            },
        ],
        scheduled_events=[],
        hot_topics=[],
        narrative_direction="",
    )

    # Exécuter 10 fois pour prouver la stabilité déterministe (zéro inversion aléatoire)
    for _ in range(10):
        assigned = generator._assign_initial_post_agents(event_cfg, agents)
        posts = assigned.initial_posts

        # Post 1 doit être assigné à Émilie (agent_id=3)
        assert posts[0]["poster_agent_id"] == 3
        assert posts[0]["poster_entity_name"] == "Émilie"

        # Post 2 doit être assigné à Sylvie (agent_id=2)
        assert posts[1]["poster_agent_id"] == 2
        assert posts[1]["poster_entity_name"] == "Sylvie"

        # Post 3 doit être assigné à Christine (agent_id=1)
        assert posts[2]["poster_agent_id"] == 1
        assert posts[2]["poster_entity_name"] == "Christine"


def test_simulation_config_generator_content_mention_fallback():
    """Vérifie que la mention du nom dans le texte du post assigne correctement le persona si poster_persona manque."""
    generator = SimulationConfigGenerator()

    agents = [
        AgentActivityConfig(agent_id=10, entity_uuid="u10", entity_name="Dr. Moreau", entity_type="Expert", influence_weight=0.5),
        AgentActivityConfig(agent_id=20, entity_uuid="u20", entity_name="Julien", entity_type="Student", influence_weight=0.5),
    ]

    event_cfg = EventConfig(
        initial_posts=[
            {
                "content": "Julien : Le campus est bloqué aujourd'hui.",
                "poster_type": "Student",
            }
        ],
        scheduled_events=[],
        hot_topics=[],
        narrative_direction="",
    )

    assigned = generator._assign_initial_post_agents(event_cfg, agents)
    assert assigned.initial_posts[0]["poster_agent_id"] == 20
    assert assigned.initial_posts[0]["poster_entity_name"] == "Julien"


# ============================================================================
# AC6 : Tests d'étanchéité action réelle vs intention textuelle
# ============================================================================

def test_epistemic_distinction_action_vs_verbal_intention(tmp_path):
    """Vérifie qu'un post contenant une intention verbale non suivie d'action n'est pas qualifié d'action observée."""
    sim_dir = tmp_path / "simulations" / "sim_epistemic_test"
    os.makedirs(sim_dir, exist_ok=True)

    # 1. Un post exprimant l'intention « Je vais me désabonner » dans SQLite post
    db_path = sim_dir / "twitter_simulation.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE post (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            user_name TEXT,
            content TEXT,
            round INTEGER,
            created_at TEXT
        )
    """)
    cursor.execute("""
        INSERT INTO post (id, user_id, user_name, content, round, created_at)
        VALUES (1, 10, 'Sylvie', 'Je suis déçue, je vais me désabonner dès demain.', 1, '2026-10-16T12:00:00Z')
    """)
    conn.commit()
    conn.close()

    # Aucun fichier actions.jsonl ne contient d'action effective de désabonnement
    verifier = SimulationActionVerifier("sim_epistemic_test")
    # Pointeur sim_dir
    verifier.load_simulation_actions = lambda s_id=None, s_dir=None: []

    # Vérification de l'affirmation d'action
    claim_check = verifier.validate_report_claim(
        simulation_id="sim_epistemic_test",
        claim_text="Sylvie a résilié son abonnement",
        claimed_agent="Sylvie",
        claimed_action_type="unsubscribe",
    )

    # Doit être REFUSÉ comme action observée
    assert claim_check["allowed_as_observed_action"] is False
    assert claim_check["event_id"] is None
    assert "Interdiction anti-affabulation (C7)" in claim_check["warning"]


def test_report_agent_execute_tool_with_toolshield(monkeypatch):
    """Vérifie l'intégration directe de ToolShield dans ReportAgent._execute_tool."""
    from app.services.report_agent import ReportAgent

    # Instanciation minimale de ReportAgent avec mocks
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "test_graph"
    agent.simulation_id = "test_sim"
    agent.simulation_requirement = "Test simulation requirement"
    agent.zep_tools = ZepToolsService()

    # Mocker quick_search pour vérifier que query a été assaini
    captured_args = {}
    def mock_quick_search(graph_id, query, limit):
        captured_args["query"] = query
        captured_args["limit"] = limit
        from app.services.zep_tools import SearchResult
        return SearchResult(facts=["Fait 1"], edges=[], nodes=[], query=query, total_count=1)

    monkeypatch.setattr(agent.zep_tools, "quick_search", mock_quick_search)

    # Appel avec paramètres vides : ToolShield doit injecter report_context ou simulation_requirement
    res = agent._execute_tool(
        tool_name="quick_search",
        parameters={},
        report_context="Section Titre Contexte",
    )
    assert captured_args["query"] == "Section Titre Contexte"
    assert "Fait 1" in res


def test_oasis_log_reader_offline_resilience(tmp_path):
    """Vérifie que OasisLogReaderService ne crashe pas si le répertoire n'existe pas ou est vide."""
    service = OasisLogReaderService("sim_non_existent")
    service.get_simulation_dir = lambda sim_id=None: str(tmp_path / "inconnu")

    events = service.load_events()
    assert events == []

    pack = service.build_evidence_pack()
    assert pack.total_events == 0
    assert pack.to_text() != ""


def test_toolshield_preserves_budget_on_success():
    """Vérifie que ToolShield transmet fidèlement le résultat d'un exécuteur valide."""
    def working_executor(tool_name, params):
        return f"OK: {tool_name} with {params.get('query')}"

    res = ToolShield.execute_with_shield(
        tool_name="quick_search",
        parameters={"query": "bonjour"},
        executor=working_executor,
    )
    assert res == "OK: quick_search with bonjour"


def test_oasis_log_reader_handles_null_values_in_jsonl_and_sqlite(tmp_path):
    """Vérifie la robustesse face à des champs null ou types invalides (Patches 1 & 2 BMAD)."""
    sim_dir = tmp_path / "simulations" / "sim_null_test"
    os.makedirs(sim_dir / "twitter", exist_ok=True)

    # 1. JSONL contenant une ligne avec round: null et agent_id: null, suivie d'une ligne valide
    actions = [
        {"action_type": "post", "round": None, "agent_id": None, "timestamp": None, "action_args": {"content": "Post 1"}},
        {"action_type": "comment", "round": "invalid_int", "agent_id": "abc", "action_args": {"content": "Post 2"}},
        {"action_type": "like", "round": 2, "agent_id": 99, "action_args": {"target": 1}},
    ]
    with open(sim_dir / "twitter" / "actions.jsonl", "w", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps(a) + "\n")

    # 2. SQLite contenant une table post avec colonnes NULL
    db_path = sim_dir / "twitter_simulation.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE post (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            user_name TEXT,
            content TEXT,
            round INTEGER,
            created_at TEXT
        )
    """)
    cursor.execute("INSERT INTO post VALUES (1, NULL, NULL, 'Contenu SQLite', NULL, NULL)")
    conn.commit()
    conn.close()

    service = OasisLogReaderService("sim_null_test")
    service.get_simulation_dir = lambda sim_id=None: str(sim_dir)

    events = service.load_events("sim_null_test", force_reload=True)
    # Les 3 lignes JSONL + la ligne SQLite doivent être lues sans crash
    assert len(events) == 4
    # La ligne avec round: None doit avoir round_num=0 par défaut
    ev_null = next(e for e in events if e.action_type == "post" and e.platform == "twitter" and "Post 1" in str(e.action_args))
    assert ev_null.round_num == 0
    assert ev_null.agent_id == 0

    # La 3e ligne valide doit être préservée (pas d'abandon prématuré de la boucle)
    ev_valid = next(e for e in events if e.action_type == "like")
    assert ev_valid.round_num == 2
    assert ev_valid.agent_id == 99


def test_tool_shield_sanitizes_trivial_serialized_strings():
    """Vérifie que ToolShield assainit les chaînes sérialisées triviales comme '{}' ou '[]' (Patch 3 BMAD)."""
    for trivial_query in ["{}", "[]", '""', "''", "null", "none", "<empty>", "   "]:
        params, modified = ToolShield.sanitize_parameters(
            tool_name="quick_search",
            parameters={"query": trivial_query},
            section_title="Titre Section",
        )
        assert modified is True
        assert params["query"] == "Titre Section"


def test_simulation_config_generator_robustness_to_none_entity_name():
    """Vérifie la robustesse face à des entités avec entity_name=None (Patch 5 BMAD)."""
    generator = SimulationConfigGenerator()
    agents = [
        AgentActivityConfig(agent_id=1, entity_uuid="u1", entity_name=None, entity_type=None),  # type: ignore
        AgentActivityConfig(agent_id=2, entity_uuid="u2", entity_name="Sylvie", entity_type="Person"),
    ]
    event_cfg = EventConfig(
        initial_posts=[{"content": "Hello", "poster_type": "Person", "poster_persona": "Sylvie"}],
        scheduled_events=[],
        hot_topics=[],
        narrative_direction="",
    )
    assigned = generator._assign_initial_post_agents(event_cfg, agents)
    assert assigned.initial_posts[0]["poster_agent_id"] == 2


def test_report_agent_execute_tool_invalid_parameters(monkeypatch):
    """Vérifie que des arguments numériques non valides ne font pas crasher ReportAgent (Patch 6 BMAD)."""
    from app.services.report_agent import ReportAgent

    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "test_graph"
    agent.simulation_id = "test_sim"
    agent.simulation_requirement = "Requirement"
    agent.zep_tools = ZepToolsService()

    captured = {}
    def mock_query_events(**kwargs):
        captured.update(kwargs)
        return "OK"

    monkeypatch.setattr(agent.zep_tools, "query_simulation_events", mock_query_events)

    res = agent._execute_tool(
        tool_name="query_simulation_events",
        parameters={"limit": "not_an_int", "round_min": "invalid", "round_max": None},
    )
    assert res == "OK"
    assert captured["limit"] == 20
    assert captured["round_min"] is None
    assert captured["round_max"] is None
