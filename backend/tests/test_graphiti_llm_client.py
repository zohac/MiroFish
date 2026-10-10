"""Tests unitaires hermétiques pour MiroFishLLMClient (story 001-3).

Ces tests vérifient le comportement du client LLM Graphiti :
- Injection automatique des en-têtes OpenCode Go (x-opencode-session, User-Agent)
- Neutralité stricte envers les autres fournisseurs LLM
- Mode de sortie structurée json_object par défaut
- Transmission de l'effort de raisonnement (LLM_REASONING_EFFORT)
- Compatibilité avec l'instanciation de Graphiti

Tous les appels réseau sont strictement mockés : aucun secret ni réseau requis.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest
from pydantic import BaseModel

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.errors import EmptyResponseError, RateLimitError
from graphiti_core.prompts.models import Message

from app.utils.graphiti_llm_client import MiroFishLLMClient


class SimpleExtractionModel(BaseModel):
    name: str
    category: str


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch: pytest.MonkeyPatch):
    """Garantit un environnement hermétique sans secrets ni variables polluantes."""
    monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://opencode.ai/zen/go/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "space-bunny-free")


def test_initialisation_par_defaut_injecte_headers_opencode():
    """Vérifie l'injection de l'en-tête de session et User-Agent pour OpenCode Go."""
    client = MiroFishLLMClient()

    assert client.structured_output_mode == "json_object"
    assert client.model == "space-bunny-free"

    headers = client.client.default_headers
    assert headers.get("User-Agent") == "mirofish/0.1.0"
    assert "x-opencode-session" in headers
    assert len(headers["x-opencode-session"]) > 0


def test_session_id_explicite_respectee(monkeypatch: pytest.MonkeyPatch):
    """Vérifie que OPENCODE_SESSION_ID surcharge l'identifiant par défaut."""
    monkeypatch.setenv("OPENCODE_SESSION_ID", "custom-session-uuid-12345")

    client = MiroFishLLMClient()
    headers = client.client.default_headers

    assert headers.get("x-opencode-session") == "custom-session-uuid-12345"


def test_neutralite_pour_fournisseurs_non_opencode(monkeypatch: pytest.MonkeyPatch):
    """Vérifie qu'aucun en-tête de session n'est injecté pour un hôte non-opencode."""
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")

    client = MiroFishLLMClient()
    headers = client.client.default_headers

    assert headers.get("User-Agent") == "mirofish/0.1.0"
    assert "x-opencode-session" not in headers


def test_neutralite_si_base_url_none_dans_config_explicite(monkeypatch: pytest.MonkeyPatch):
    """Vérifie qu'un LLMConfig avec base_url=None ne fait pas fuiter la session même si LLM_BASE_URL est OpenCode."""
    monkeypatch.setenv("LLM_BASE_URL", "https://opencode.ai/zen/go/v1")

    client = MiroFishLLMClient(config=LLMConfig(api_key="openai-key", base_url=None))
    headers = client.client.default_headers

    assert headers.get("User-Agent") == "mirofish/0.1.0"
    assert "x-opencode-session" not in headers


def test_client_externe_fourni_est_conserve():
    """Vérifie qu'un client AsyncOpenAI passé explicitement n'est pas réinstancié."""
    mock_async_client = MagicMock()
    client = MiroFishLLMClient(client=mock_async_client)

    assert client.client is mock_async_client


def test_mode_structured_output_personnalisable():
    """Vérifie qu'on peut forcer structured_output_mode='json_schema' si besoin."""
    client = MiroFishLLMClient(structured_output_mode="json_schema")
    assert client.structured_output_mode == "json_schema"


@pytest.mark.asyncio
async def test_generate_response_injecte_schema_dans_le_prompt_en_mode_json_object():
    """Vérifie qu'en mode json_object, le schéma est injecté dans le prompt et le response_format est json_object."""
    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"name": "Graphiti", "category": "Database"})
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)

    messages = [
        Message(role="system", content="Tu es un extracteur d'entités."),
        Message(role="user", content="Extraire les entités du texte: Graphiti est une base de données graphe."),
    ]

    result = await client.generate_response(messages, response_model=SimpleExtractionModel)

    assert result == {"name": "Graphiti", "category": "Database"}

    # Vérification des arguments passés à chat.completions.create
    mock_async_openai.chat.completions.create.assert_awaited_once()
    call_kwargs = mock_async_openai.chat.completions.create.await_args.kwargs

    assert call_kwargs["response_format"] == {"type": "json_object"}
    # Le message utilisateur doit contenir le schéma sérialisé
    sent_user_msg = [m["content"] for m in call_kwargs["messages"] if m["role"] == "user"][0]
    assert "Respond with a JSON object in the following format:" in sent_user_msg
    assert "SimpleExtractionModel" in sent_user_msg or "name" in sent_user_msg


@pytest.mark.asyncio
async def test_generate_response_transmet_reasoning_effort(monkeypatch: pytest.MonkeyPatch):
    """Vérifie que LLM_REASONING_EFFORT est relayé via extra_body."""
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")

    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"name": "Test", "category": "Unit"})
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)

    messages = [
        Message(role="user", content="Test extraction"),
    ]

    await client.generate_response(messages, response_model=SimpleExtractionModel)

    call_kwargs = mock_async_openai.chat.completions.create.await_args.kwargs
    assert "extra_body" in call_kwargs
    assert call_kwargs["extra_body"] == {"reasoning_effort": "high"}


@pytest.mark.asyncio
async def test_generate_response_sans_reasoning_effort(monkeypatch: pytest.MonkeyPatch):
    """Vérifie que sans LLM_REASONING_EFFORT, extra_body n'est pas envoyé."""
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)

    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"name": "Test", "category": "Unit"})
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)

    messages = [
        Message(role="user", content="Test extraction"),
    ]

    await client.generate_response(messages, response_model=SimpleExtractionModel)

    call_kwargs = mock_async_openai.chat.completions.create.await_args.kwargs
    assert "extra_body" not in call_kwargs


@pytest.mark.asyncio
async def test_generate_response_nettoie_les_markdown_code_fences():
    """Vérifie que les balises ```json ... ``` générées par le modèle sont nettoyées."""
    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "```json\n{\"name\": \"Nettoye\", \"category\": \"Markdown\"}\n```"
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)

    messages = [Message(role="user", content="Test markdown")]
    result = await client.generate_response(messages, response_model=SimpleExtractionModel)

    assert result == {"name": "Nettoye", "category": "Markdown"}


@pytest.mark.asyncio
async def test_generate_response_nettoie_balises_think_raisonnement():
    """Vérifie que les balises <think>...</think> émises par les modèles de raisonnement sont nettoyées."""
    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        "<think>\n"
        "Je dois extraire les entités du texte fourni.\n"
        "L'entité principale est Graphiti.\n"
        "</think>\n"
        "```json\n"
        '{"name": "Graphiti", "category": "Database"}\n'
        "```"
    )
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)
    messages = [Message(role="user", content="Extraction avec raisonnement")]

    result = await client.generate_response(messages, response_model=SimpleExtractionModel)
    assert result == {"name": "Graphiti", "category": "Database"}


@pytest.mark.asyncio
async def test_generate_response_gere_reponse_vide():
    """Vérifie qu'une réponse vide lève EmptyResponseError."""
    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)

    messages = [Message(role="user", content="Test empty")]
    with pytest.raises(EmptyResponseError, match="LLM returned an empty response"):
        await client._generate_response(messages)


@pytest.mark.asyncio
async def test_generate_response_gere_choices_vides():
    """Vérifie qu'une réponse sans choices lève EmptyResponseError."""
    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = []
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)
    messages = [Message(role="user", content="Test choices vides")]

    with pytest.raises(EmptyResponseError, match="LLM returned an empty choices list"):
        await client._generate_response(messages)


@pytest.mark.asyncio
async def test_generate_response_convertit_rate_limit_error():
    """Vérifie qu'un openai.RateLimitError est converti en RateLimitError de Graphiti."""
    mock_async_openai = MagicMock()
    mock_response_http = MagicMock()
    mock_response_http.status_code = 429
    mock_async_openai.chat.completions.create = AsyncMock(
        side_effect=openai.RateLimitError(
            message="Rate limit exceeded",
            response=mock_response_http,
            body={"error": {"message": "Rate limit exceeded"}},
        )
    )

    client = MiroFishLLMClient(client=mock_async_openai)

    messages = [Message(role="user", content="Test rate limit")]
    with pytest.raises(RateLimitError):
        await client._generate_response(messages)


from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.cross_encoder.client import CrossEncoderClient


class DummyEmbedder(EmbedderClient):
    async def create(self, input_data):
        return []


class DummyCrossEncoder(CrossEncoderClient):
    async def rank(self, query, passages):
        return []


def test_instanciation_graphiti_avec_mirofish_llm_client():
    """Vérifie que Graphiti accepte MiroFishLLMClient comme paramètre llm_client."""
    llm_client = MiroFishLLMClient(
        config=LLMConfig(api_key="fake-key", base_url="https://opencode.ai/zen/go/v1", model="space-bunny-free")
    )

    graphiti = Graphiti(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="fake-password",
        llm_client=llm_client,
        embedder=DummyEmbedder(),
        cross_encoder=DummyCrossEncoder(),
    )

    assert graphiti.llm_client is llm_client
    assert graphiti.llm_client.structured_output_mode == "json_object"


@pytest.mark.asyncio
async def test_sonde_verifier_client_graphiti_mock():
    """Vérifie que la sonde scripts/verifier_llm_graphiti.py s'exécute avec succès en mode mock."""
    from scripts.verifier_llm_graphiti import verifier_client_graphiti

    exit_code = await verifier_client_graphiti(mock=True)
    assert exit_code == 0


@pytest.mark.asyncio
async def test_generate_response_resilient_echo_schema_json():
    """Vérifie que si le LLM renvoie le schéma JSON brut au lieu d'une instance, il y a repli sur les valeurs par défaut."""
    from graphiti_core.prompts.extract_nodes import ExtractedEntities

    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(
        {
            "$defs": {
                "ExtractedEntity": {
                    "properties": {
                        "name": {"type": "string"},
                        "entity_type_id": {"type": "integer"},
                        "episode_indices": {"type": "array"},
                    },
                    "required": ["name", "entity_type_id"],
                    "title": "ExtractedEntity",
                    "type": "object",
                }
            },
            "properties": {
                "extracted_entities": {
                    "items": {"$ref": "#/$defs/ExtractedEntity"},
                    "type": "array",
                }
            },
            "required": ["extracted_entities"],
            "title": "ExtractedEntities",
            "type": "object",
        }
    )
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)
    messages = [Message(role="user", content="Extraction sur texte vide")]

    result = await client.generate_response(messages, response_model=ExtractedEntities)
    assert "extracted_entities" in result
    assert result["extracted_entities"] == []
    # Vérification que ExtractedEntities valide sans erreur
    validated = ExtractedEntities(**result)
    assert validated.extracted_entities == []


@pytest.mark.asyncio
async def test_generate_response_normalise_donnees_encapsulees_properties():
    """Vérifie qu'un dictionnaire encapsulé dans properties est désencapsulé avec succès."""
    from graphiti_core.prompts.extract_nodes import ExtractedEntities

    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(
        {
            "properties": {
                "extracted_entities": [
                    {"name": "Keova", "entity_type_id": 3, "episode_indices": [0]}
                ]
            }
        }
    )
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)
    messages = [Message(role="user", content="Extraction Keova")]

    result = await client.generate_response(messages, response_model=ExtractedEntities)
    validated = ExtractedEntities(**result)
    assert len(validated.extracted_entities) == 1
    assert validated.extracted_entities[0].name == "Keova"


@pytest.mark.asyncio
async def test_generate_response_normalise_liste_directe():
    """Vérifie qu'une liste brute retournée par le modèle est encapsulée dans le champ unique du modèle."""
    from graphiti_core.prompts.extract_nodes import ExtractedEntities

    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(
        [
            {"name": "Sophie Jouan", "entity_type_id": 1, "episode_indices": [0]}
        ]
    )
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)
    messages = [Message(role="user", content="Extraction Sophie")]

    result = await client.generate_response(messages, response_model=ExtractedEntities)
    validated = ExtractedEntities(**result)
    assert len(validated.extracted_entities) == 1
    assert validated.extracted_entities[0].name == "Sophie Jouan"


@pytest.mark.asyncio
async def test_generate_response_normalise_alias_entities():
    """Vérifie que la clé 'entities' est automatiquement renommée en 'extracted_entities'."""
    from graphiti_core.prompts.extract_nodes import ExtractedEntities

    mock_async_openai = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(
        {
            "entities": [
                {"name": "Ménopause", "entity_type_id": 4, "episode_indices": [0]}
            ]
        }
    )
    mock_response.choices = [mock_choice]
    mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

    client = MiroFishLLMClient(client=mock_async_openai)
    messages = [Message(role="user", content="Extraction Ménopause")]

    result = await client.generate_response(messages, response_model=ExtractedEntities)
    validated = ExtractedEntities(**result)
    assert len(validated.extracted_entities) == 1
    assert validated.extracted_entities[0].name == "Ménopause"

