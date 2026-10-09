"""Adaptateurs pour les fournisseurs LLM compatibles OpenAI qui exigent un contexte de requête.

Certains passerels compatibles OpenAI refusent les requêtes qui ne s'identifient pas
ou qui ne portent pas d'identifiant de session stable. OpenCode Go / Zen en fait partie :
il répond HTTP 400 ``MissingSessionID`` en l'absence de l'en-tête ``x-opencode-session``.

Ces helpers sont sans effet sur les fournisseurs qui n'en ont pas besoin, afin que
les appelants puissent les appliquer inconditionnellement.

Variables d'environnement reconnues :

- ``LLM_REASONING_EFFORT`` : niveau d'effort de raisonnement à envoyer
  (``minimal``/``low``/``medium``/``high``). Ignorée si vide.
- ``OPENCODE_SESSION_ID`` : identifiant de session explicite. Par défaut, un
  identifiant stable pour toute la durée du processus (une exécution = une session).
"""

import os
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# Hôtes qui exigent les en-têtes de session / user-agent.
_SESSION_HEADER_HOST = "opencode.ai"

# Stable pendant toute la durée du processus : une exécution de simulation
# correspond à une seule session.
_PROCESS_SESSION_ID = uuid.uuid4().hex

# User-Agent identifiant le client, conformément aux exigences de la passerelle.
_USER_AGENT = "mirofish/0.1.0"


def _requires_session_header(base_url: Optional[str]) -> bool:
    """Indique si l'hôte cible attend des en-têtes de session OpenCode."""
    if not base_url:
        return False
    normalized_url = base_url if "://" in base_url else f"https://{base_url}"
    host = (urlparse(normalized_url).hostname or "").lower()
    return host == _SESSION_HEADER_HOST or host.endswith(f".{_SESSION_HEADER_HOST}")


def llm_request_headers(base_url: Optional[str] = None) -> Dict[str, str]:
    """Construit les en-têtes à passer au client OpenAI.

    Args:
        base_url: URL du fournisseur. Par défaut, ``LLM_BASE_URL``.

    Returns:
        Les en-têtes à passer via ``default_headers``.
    """
    if base_url is None:
        base_url = os.environ.get("LLM_BASE_URL")
    base_url = base_url or ""
    headers: Dict[str, str] = {"User-Agent": _USER_AGENT}

    if _requires_session_header(base_url):
        session_id = os.environ.get("OPENCODE_SESSION_ID") or _PROCESS_SESSION_ID
        headers["x-opencode-session"] = session_id

    return headers


def llm_completion_kwargs(effort: Optional[str] = None) -> Dict[str, Any]:
    """Construit les paramètres supplémentaires à envoyer dans le corps de la requête.

    Args:
        effort: Niveau d'effort facultatif. Si omis ou None, résout ``LLM_REASONING_EFFORT``
            depuis l'environnement.

    Returns:
        Par exemple ``{"reasoning_effort": "high"}``, ou un dictionnaire vide
        si aucun niveau d'effort n'est configuré.
    """
    if effort is None:
        effort = os.environ.get("LLM_REASONING_EFFORT")
    effort_str = (effort or "").strip()
    return {"reasoning_effort": effort_str} if effort_str else {}