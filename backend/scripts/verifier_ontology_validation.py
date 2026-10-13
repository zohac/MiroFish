#!/usr/bin/env python3
"""Qualification C2 du store livré : Neo4j réel, LLM et vecteurs locaux."""

# ruff: noqa: E402
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from graphiti_core import Graphiti
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.extract_nodes import ExtractedEntities

from app.config import Config
from app.utils.graph_store import GraphValidationError
from app.utils.graph_store.graphiti_store import GraphitiGraphStore, _OntologyValidatingGraphiti

ONTOLOGY = {
    "entity_types": [{"name": "Person"}, {"name": "Company"}],
    "edge_types": [],
}


class DeterministicEmbedder(EmbedderClient):
    """Vecteurs fixes, sans téléchargement ni appel réseau."""

    async def create(self, input_data):
        return [1.0] + [0.0] * 383

    async def create_batch(self, input_data_list):
        return [await self.create(text) for text in input_data_list]


class DeterministicLLM(LLMClient):
    """Produit des candidats adversariaux ; aucune validation dans la doublure."""

    def __init__(self, type_ids):
        super().__init__(LLMConfig(api_key="qualification-locale", model="deterministe"))
        self.type_ids = iter(type_ids)
        self.name = ""
        self.calls = 0

    async def _generate_response(self, messages, response_model=None, max_tokens=None, model_size=None, **kwargs):
        name = getattr(response_model, "__name__", "")
        if response_model is ExtractedEntities:
            self.calls += 1
            self.name = f"acteur_{self.calls}"
            return {"extracted_entities": [{"name": self.name, "entity_type_id": next(self.type_ids), "episode_indices": [0]}]}
        if name == "SummarizedEntities":
            return {"summaries": [{"name": self.name, "summary": "Preuve locale."}]}
        if name == "EntitySummary":
            return {"summary": "Preuve locale."}
        if name == "ExtractedEdges":
            return {"edges": []}
        if name == "NodeResolutions":
            return {"entity_resolutions": []}
        return {}


def inject_final_candidate(engine, *, labels=None, attributes=None, node_uuid=None):
    """Injecte une faute à l'entrée de la frontière livrée, sans la remplacer."""
    original = engine._process_episode_data

    async def process(*args, **kwargs):
        bound = inspect.signature(Graphiti._process_episode_data).bind(engine, *args, **kwargs)
        for node in bound.arguments["nodes"]:
            if labels is not None:
                node.labels = list(labels)
            if attributes is not None:
                node.attributes.update(attributes)
            if node_uuid is not None:
                old_uuid = node.uuid
                node.uuid = node_uuid
                index_map = bound.arguments.get("node_episode_index_map")
                if index_map is not None and old_uuid in index_map:
                    index_map[node.uuid] = index_map.pop(old_uuid)
        return await original(*bound.args[1:], **bound.kwargs)
    engine._process_episode_data = process


def qualify():
    import uuid

    results = []
    cases = [
        ("declare", [1], False, None, None, False, 1, 0),
        ("id_inconnu_strict", [999], True, None, None, True, 0, 0),
        ("generique_strict", [0], True, None, None, True, 0, 0),
        ("id_inconnu_permissif", [999], False, None, None, False, 1, 1),
        ("final_inconnu_strict", [1], True, ["Entity", "Unknown"], None, True, 0, 0),
        ("final_inconnu_permissif", [1], False, ["Entity", "Person", "Unknown"], {"entity_type": "Unknown"}, False, 1, 1),
        ("contradiction_stricte", [1], True, ["Entity", "Person", "Company"], None, True, 0, 0),
        ("contradiction_permissive", [1], False, ["Entity", "Person", "Company"], None, False, 1, 1),
        ("attribut_generique", [999], False, ["Entity"], {"entity_type": "Unknown"}, False, 1, 2),
        ("lot_mixte_strict", [1, 999], True, None, None, True, 1, 0),
        ("lot_mixte_permissif", [1, 999], False, None, None, False, 2, 1),
        ("noeud_existant_retrograde", [1], False, ["Entity", "Person", "Unknown"], None, False, 1, 1),
    ]
    original_folder = Config.UPLOAD_FOLDER
    with tempfile.TemporaryDirectory(prefix="qualification-007-2-") as folder:
        Config.UPLOAD_FOLDER = folder
        try:
            for name, ids, strict, labels, attributes, rejected_expected, count, warning_count in cases:
                gid = f"qualification0072_{uuid.uuid4().hex}"
                llm = DeterministicLLM(ids)
                store = GraphitiGraphStore(llm_client=llm, embedder=DeterministicEmbedder())
                assert isinstance(store._graphiti, _OntologyValidatingGraphiti)
                try:
                    store.create_graph(name, graph_id=gid)
                    store.set_ontology(gid, ONTOLOGY, strict=strict)
                    existing_uuid = None
                    if name == "noeud_existant_retrograde":
                        existing_uuid = str(uuid.uuid4())
                        store._run_async(store._execute_cypher(
                            "CREATE (:Entity:Person:Unknown {uuid: $uuid, group_id: $gid, name: 'ancien'})",
                            {"uuid": existing_uuid, "gid": gid},
                        ))
                    if labels is not None:
                        inject_final_candidate(store._graphiti, labels=labels, attributes=attributes, node_uuid=existing_uuid)
                    rejected = False
                    try:
                        if len(ids) > 1:
                            store.add_text_batch(gid, [f"Fragment {i}" for i in range(len(ids))])
                        else:
                            store.add_episode(gid, "Texte de qualification.")
                    except GraphValidationError as exc:
                        assert gid in str(exc), str(exc)
                        rejected = True
                    nodes = store.get_all_nodes(gid)
                    records = store._extract_records(store._run_async(store._execute_cypher(
                        "MATCH (n {group_id: $gid}) RETURN labels(n) AS labels", {"gid": gid},
                    )))
                    episodes = [r for r in records if "Episodic" in r["labels"]]
                    mentions = store._extract_records(store._run_async(store._execute_cypher(
                        "MATCH (n:Episodic {group_id: $gid})-[r:MENTIONS]->() RETURN count(r) AS count", {"gid": gid},
                    )))[0]["count"]
                    warnings = store.get_ontology_warnings(gid)
                    assert rejected == rejected_expected, name
                    assert len(nodes) == count, (name, nodes)
                    assert len(episodes) == count, name
                    assert mentions == count, name
                    assert len(warnings) == warning_count, (name, warnings)
                    assert all(set(n.labels) <= {"Entity", "Person", "Company"} for n in nodes), name
                    if labels is not None and not strict:
                        assert all(n.labels == ["Entity"] for n in nodes), name
                        assert all(not any(k in n.attributes for k in ("entity_type", "type", "category")) for n in nodes), name
                    # Lecture par une nouvelle instance : journal et politique survivent.
                    reader = GraphitiGraphStore(llm_client=DeterministicLLM([]), embedder=DeterministicEmbedder())
                    try:
                        assert reader.get_applied_ontology(gid).strict is strict
                        assert reader.get_ontology_warnings(gid) == warnings
                    finally:
                        reader.close()
                    results.append({"cas": name, "refus": rejected, "noeuds": len(nodes), "episodes": len(episodes), "mentions": mentions, "warnings": len(warnings)})
                finally:
                    store.delete_graph(gid)
                    assert store.get_all_nodes(gid) == []
                    store.close()
        finally:
            Config.UPLOAD_FOLDER = original_folder
    sources = [Path(inspect.getfile(GraphitiGraphStore)), Path(__file__)]
    return {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "versions": {name: version(name) for name in ("graphiti-core", "neo4j")},
        "sources_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "moteur": "_OntologyValidatingGraphiti livré, sans substitution",
        "limites": "LLM/vecteurs déterministes ; MENTIONS réels, relations métier non générées ; aucune qualification Zep distante",
        "cas": results,
        "verdict": "GO C2 Graphiti",
    }


if __name__ == "__main__":
    # Les handlers sont créés à l'import : leur stream doit être changé
    # explicitement pour garder stdout comme artefact JSON machine-readable.
    for logger in [logging.getLogger(), *logging.Logger.manager.loggerDict.values()]:
        if isinstance(logger, logging.Logger):
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
                    handler.setStream(sys.stderr)
    report = qualify()
    print(json.dumps(report, ensure_ascii=False, indent=2))
