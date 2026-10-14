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


@project_bp.get("/<project_id>/ontology")
def get_project_ontology(project_id: str):
    """Retourne la version courante d'ontologie appliquée au projet (AC6, AC7, PRD Q4)."""
    from ..models.project import ProjectManager
    from ..services.ontology_policy import OntologyPolicyService

    project = ProjectManager.get_project(project_id)
    if project is None:
        return jsonify({"success": False, "error": f"Projet introuvable : {project_id}"}), 404

    version = project.get_applied_ontology()
    if version is None:
        return jsonify({
            "success": False,
            "error": f"Aucune ontologie appliquée au projet : {project_id}",
        }), 404

    data = version.to_dict()

    # Enrichissement avec la politique et statistiques optionnelles pour l'audit et l'IHM (AC7)
    warnings_count = 0
    try:
        warns = OntologyPolicyService.warnings(project.project_id)
        warnings_count = len(warns)
    except Exception:
        pass

    data["policy"] = {
        "strict_ontology": bool(project.strict_ontology),
        "warnings_count": warnings_count,
    }

    # Statistiques optionnelles si demandé (include_counts=true)
    include_counts_param = request.args.get("include_counts", "false")
    include_counts = include_counts_param.lower() in ["true", "1", "yes"]
    if include_counts:
        data["statistics"] = {
            "entity_counts": {},
            "edge_counts": {},
            "total_nodes": 0,
            "total_edges": 0,
        }
        if project.graph_id:
            from ..utils.graph_store.factory import release_graph_store
            store = None
            try:
                store = get_graph_store()
                nodes = store.get_all_nodes(project.graph_id)
                entity_counts = {}
                for n in nodes:
                    for label in getattr(n, "labels", []):
                        if label not in ["Entity", "Node"]:
                            entity_counts[label] = entity_counts.get(label, 0) + 1

                edges = store.get_all_edges(project.graph_id, include_temporal=False)
                edge_counts = {}
                for e in edges:
                    name = getattr(e, "name", None) or getattr(e, "relation_type", None)
                    if name:
                        edge_counts[name] = edge_counts.get(name, 0) + 1

                data["statistics"] = {
                    "entity_counts": entity_counts,
                    "edge_counts": edge_counts,
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                }
            except Exception:
                pass
            finally:
                if store is not None:
                    release_graph_store(store)

    return jsonify({
        "success": True,
        "data": data,
    }), 200


@project_bp.post("/<project_id>/ontology/regenerate")
def regenerate_project_ontology(project_id: str):
    """Force la régénération explicite de l'ontologie du projet (AC5, E3)."""
    from ..services.ontology_events import OntologyEventService

    try:
        version = OntologyEventService.regenerate_on_demand(
            project_id=project_id,
            store_factory=get_graph_store,
        )
    except GraphNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except GraphValidationError as exc:
        msg = str(exc)
        if "déjà en cours" in msg:
            return jsonify({"success": False, "error": msg}), 409
        return jsonify({"success": False, "error": msg}), 422
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({
        "success": True,
        "data": version.to_dict(),
    }), 200


@project_bp.post("/<project_id>/documents")
def add_document_and_regenerate(project_id: str):
    """Ajoute un document textuel au projet et déclenche l'événement E1 (AC3, C4)."""
    from ..services.ontology_events import OntologyEventService

    payload = request.get_json(silent=True) or {}
    text = payload.get("text") or request.form.get("text")
    filename = payload.get("filename") or request.form.get("filename") or "document.txt"
    document_id = payload.get("document_id") or request.form.get("document_id")

    if not text or not isinstance(text, str) or not text.strip():
        # Vérification si un fichier multipart a été envoyé
        if "file" in request.files:
            file_obj = request.files["file"]
            if file_obj and file_obj.filename:
                filename = file_obj.filename
                text = file_obj.read().decode("utf-8", errors="replace")

    if not text or not text.strip():
        return jsonify({"success": False, "error": "Le contenu textuel du document est requis"}), 400

    import uuid
    doc_id = document_id or f"doc_{uuid.uuid4().hex[:8]}"

    try:
        version = OntologyEventService.on_document_added(
            project_id=project_id,
            document_id=doc_id,
            document_text=text,
            filename=filename,
            store_factory=get_graph_store,
        )
    except GraphNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except GraphValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({
        "success": True,
        "data": {
            "document_id": doc_id,
            "filename": filename,
            "ontology_version": version.to_dict(),
        },
    }), 200


@project_bp.patch("/<project_id>/brief")
def update_project_brief(project_id: str):
    """Met à jour le brief et déclenche E2 si difflib.SequenceMatcher.ratio() < 0.95 (AC4)."""
    from ..services.ontology_events import OntologyEventService

    payload = request.get_json(silent=True) or {}
    brief_text = payload.get("simulation_requirement") or payload.get("brief")
    if not brief_text or not isinstance(brief_text, str) or not brief_text.strip():
        return jsonify({"success": False, "error": "Le champ simulation_requirement (ou brief) est requis"}), 400

    try:
        regenerated, version = OntologyEventService.on_brief_changed(
            project_id=project_id,
            new_brief_text=brief_text.strip(),
            store_factory=get_graph_store,
        )
    except GraphNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except GraphValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify({
        "success": True,
        "data": {
            "regenerated": regenerated,
            "ontology_version": version.to_dict() if version else None,
        },
    }), 200
