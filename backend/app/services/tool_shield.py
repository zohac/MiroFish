"""Bouclier défensif pour les outils ReACT du ReportAgent (Story 011-2, FR-05, C3).

Ce module intercepte les appels d'outils de recherche ReACT :
  - Détecte les paramètres vides ou absents (`query=""`, `parameters={}`, `query=None`).
  - Substitue automatiquement un terme de repli pertinent dérivé du contexte de la section
    ou de l'objectif de simulation (`section_title` ou `simulation_requirement`).
  - Intercepte les erreurs de validation (`GraphValidationError`) ou exceptions de store
    pour renvoyer une observation textuelle constructive au lieu de brûler vainement
    une itération ReACT ou faire crasher l'agent.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger("mirofish.tool_shield")


def _is_empty_or_trivial(val: Any) -> bool:
    """Détecte si une valeur est None, vide ou un littéral trivial sérialisé."""
    if val is None:
        return True
    s = str(val).strip()
    if not s:
        return True
    trivial_literals = {"{}", "[]", '""', "''", "null", "none", "<empty>", "undefined", "dict()", "list()"}
    return s.lower() in trivial_literals


class ToolShield:
    """Bouclier d'interception et de fiabilisation des outils ReACT."""

    EMPTY_PARAM_TOOLS = {"quick_search", "panorama_search", "insight_forge"}

    @classmethod
    def sanitize_parameters(
        cls,
        tool_name: str,
        parameters: Dict[str, Any],
        fallback_query: str = "",
        section_title: str = "",
        simulation_requirement: str = "",
    ) -> Tuple[Dict[str, Any], bool]:
        """Assainit les paramètres d'un outil avant son exécution.
        
        Retourne (params_assainis, a_été_modifié).
        """
        params = dict(parameters) if isinstance(parameters, dict) else {}
        modified = False

        if tool_name in cls.EMPTY_PARAM_TOOLS:
            query = params.get("query")
            if _is_empty_or_trivial(query):
                # Terme de repli ordonné : section_title > fallback_query > simulation_requirement > "analyse générale"
                chosen_term = (
                    section_title.strip()
                    or fallback_query.strip()
                    or simulation_requirement.strip()
                    or "analyse générale"
                )
                params["query"] = chosen_term
                modified = True
                logger.info(
                    f"[ToolShield] Paramètre 'query' vide ou manquant intercepté pour '{tool_name}'. "
                    f"Substitution par terme de repli : '{chosen_term}'"
                )

        elif tool_name == "interview_agents":
            topic = params.get("interview_topic") if params.get("interview_topic") is not None else params.get("query")
            if _is_empty_or_trivial(topic):
                chosen_term = (
                    section_title.strip()
                    or fallback_query.strip()
                    or simulation_requirement.strip()
                    or "Avis sur la situation actuelle"
                )
                params["interview_topic"] = chosen_term
                modified = True
                logger.info(
                    f"[ToolShield] Thème d'interview vide intercepté pour '{tool_name}'. "
                    f"Substitution par : '{chosen_term}'"
                )

        elif tool_name == "query_simulation_events":
            # Si aucun critère n'est passé du tout, éviter un appel non guidé
            if not any(not _is_empty_or_trivial(v) for v in params.values()):
                if section_title:
                    params["query"] = section_title.strip()
                    modified = True
                    logger.info(
                        f"[ToolShield] Aucun filtre fourni pour 'query_simulation_events'. "
                        f"Injection de query='{params['query']}'"
                    )

        return params, modified

    @classmethod
    def execute_with_shield(
        cls,
        tool_name: str,
        parameters: Dict[str, Any],
        executor: Callable[[str, Dict[str, Any]], str],
        fallback_query: str = "",
        section_title: str = "",
        simulation_requirement: str = "",
    ) -> str:
        """Exécute un outil sous la protection du ToolShield (C3, NFR-04)."""
        safe_params, was_sanitized = cls.sanitize_parameters(
            tool_name=tool_name,
            parameters=parameters,
            fallback_query=fallback_query,
            section_title=section_title,
            simulation_requirement=simulation_requirement,
        )

        try:
            return executor(tool_name, safe_params)
        except Exception as e:
            error_msg = str(e)
            logger.warning(
                f"[ToolShield] Exception interceptée lors de l'exécution de '{tool_name}': {error_msg}"
            )
            # Fournir une réponse constructive pour que le LLM puisse poursuivre son raisonnement
            from ..utils.graph_store import GraphValidationError, GraphStoreError
            if isinstance(e, (GraphValidationError, GraphStoreError)):
                return (
                    f"【ToolShield - Avertissement】 L'outil '{tool_name}' a rencontré une contrainte "
                    f"de validation : {error_msg}. Essayez de reformuler vos critères ou d'utiliser "
                    f"un autre outil de recherche."
                )
            return (
                f"【ToolShield - Erreur gérée】 Impossible d'exécuter l'outil '{tool_name}' ({error_msg}). "
                f"Poursuivez la rédaction de la section avec les faits déjà collectés."
            )
