"""Routes de gestion de la politique et du journal ontologiques."""

from flask import Blueprint, jsonify, request

from ..services.ontology_policy import OntologyPolicyService
from ..utils.graph_store import get_graph_store
from ..utils.graph_store.errors import GraphNotFoundError, GraphValidationError

project_bp = Blueprint("project", __name__)


@project_bp.patch("/<project_id>/ontology/policy")
def update_ontology_policy(project_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"strict_ontology"}:
        return jsonify({"success": False, "error": "Le corps doit être exactement {'strict_ontology': bool}"}), 400
    if type(payload["strict_ontology"]) is not bool:
        return jsonify({"success": False, "error": "strict_ontology doit être un booléen JSON"}), 400
    try:
        project = OntologyPolicyService.update(project_id, payload["strict_ontology"], store_factory=get_graph_store)
    except GraphNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except GraphValidationError as exc:
        if "pendant une ingestion" in str(exc):
            return jsonify({"success": False, "error": str(exc)}), 409
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({
        "success": True,
        "data": {
            "project_id": project.project_id,
            "strict_ontology": project.strict_ontology,
        },
    }), 200


@project_bp.get("/<project_id>/ontology/warnings")
def get_ontology_warnings(project_id: str):
    since = request.args.get("since")
    try:
        warnings = OntologyPolicyService.warnings(
            project_id, since=since, store_factory=get_graph_store,
        )
    except GraphNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except GraphValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({
        "success": True,
        "data": [warning.to_dict() for warning in warnings],
    }), 200
