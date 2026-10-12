#!/usr/bin/env python3
"""Épreuve de faisabilité 007-2, indépendante du code produit.

Neo4j et Graphiti réels ; LLM/embeddings déterministes ; HTTP Zep intercepté.
Les classes ci-dessous sont un prototype de contrôle, pas son implémentation.
"""

# ruff: noqa: E402

import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
os.environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"

import httpx
from importlib.metadata import version
from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts.extract_nodes import ExtractedEntities
from graphiti_core.utils.maintenance import node_operations
from zep_cloud.client import Zep
from zep_cloud.types import Episode, BatchSummary

from app.utils.graph_store.errors import GraphValidationError
from app.utils.graph_store.graphiti_store import (
    GraphitiGraphStore,
    LocalPassthroughCrossEncoder,
)


class ProbeEmbedder(EmbedderClient):
    """Vecteurs locaux, aucun modèle ni téléchargement."""

    async def create(self, input_data):
        return [1.0] + [0.0] * 383

    async def create_batch(self, input_data_list):
        return [await self.create(text) for text in input_data_list]


class ProbeLLM(LLMClient):
    """Réponses brutes adversariales, avant normalisation de Graphiti."""

    def __init__(self, type_ids, strict, enabled):
        super().__init__(LLMConfig(api_key="probe-local", model="probe-local"))
        self.type_ids = iter(type_ids)
        self.strict = strict
        self.enabled = enabled
        self.warnings = []
        self.current_name = ""
        self.raw_calls = 0

    async def _generate_response(
        self, messages, response_model=None, max_tokens=None, model_size=None, **kwargs
    ):
        name = getattr(response_model, "__name__", "")
        if response_model is ExtractedEntities:
            type_id = next(self.type_ids)
            self.raw_calls += 1
            self.current_name = f"preuve_{uuid.uuid4().hex}"
            # L'ontologie de cette sonde contient un seul type déclaré (ID 1).
            # 0 = générique ; 999 = hors plage, que Graphiti ramène à Entity.
            if self.enabled and type_id != 1:
                if self.strict:
                    raise GraphValidationError(f"Type extrait refusé : id={type_id}")
                self.warnings.append(f"id={type_id}")
                type_id = 0
            return {"extracted_entities": [{
                "name": self.current_name,
                "entity_type_id": type_id,
                "episode_indices": [0],
            }]}
        if name == "SummarizedEntities":
            return {"summaries": [{"name": self.current_name, "summary": "Preuve."}]}
        if name == "EntitySummary":
            return {"summary": "Preuve."}
        if name == "ExtractedEdges":
            return {"edges": []}
        if name == "NodeResolutions":
            return {"entity_resolutions": []}
        return {}


class ProbeGraphiti(Graphiti):
    """Intercepte le point pré-sauvegarde existant sans recopier le pipeline."""

    def __init__(self, *, strict, final_fault=False, **kwargs):
        super().__init__(**kwargs)
        self.strict = strict
        self.final_fault = final_fault
        self.gate_calls = 0
        self.delegated_saves = 0
        self.warnings = []

    async def _process_episode_data(self, *args, **kwargs):
        bound = inspect.signature(Graphiti._process_episode_data).bind(self, *args, **kwargs)
        nodes = bound.arguments["nodes"]
        self.gate_calls += 1
        if self.final_fault:
            # Injection adversariale juste avant contrôle final : représente
            # un type réintroduit par hydratation/déduplication, pas par le LLM.
            for node in nodes:
                node.labels.append("UnknownType")
                node.attributes["entity_type"] = "UnknownType"
        for node in nodes:
            unknown = set(node.labels) - {"Entity", "Person"}
            if unknown:
                if self.strict:
                    raise GraphValidationError(f"Type final refusé : {sorted(unknown)}")
                self.warnings.extend(sorted(unknown))
                node.labels = ["Entity"]
                for key in ("entity_type", "type", "category"):
                    node.attributes.pop(key, None)
        self.delegated_saves += 1
        return await super()._process_episode_data(*args, **kwargs)


def zep_probe():
    """Observe le JSON produit par le vrai SDK ; aucune preuve serveur."""
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append({"path": request.url.path, "body": body})
        payload = {"batch_id": "probe"} if "/batch" in request.url.path else {
            "uuid": "probe", "processed": False, "content": "preuve",
            "created_at": "2026-10-12T00:00:00Z",
        }
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = Zep(api_key="probe-local", httpx_client=transport)
        assert "strict_ontology" in inspect.signature(client.graph.add).parameters
        client.graph.add(graph_id="probe", data="preuve", type="text", strict_ontology=True)
        assert requests[-1]["body"]["strict_ontology"] is True
        try:
            client.batch.create(strict_ontology=True)
        except TypeError:
            batch_typed = False
        else:
            raise AssertionError("Le SDK verrouillé a changé : réexaminer les lots")
        client.batch.create(request_options={
            "additional_body_parameters": {"strict_ontology": True},
        })
        assert requests[-1]["body"]["strict_ontology"] is True
        assert not any("warning" in field or "rejected" in field for field in Episode.model_fields)
        assert not any("warning" in field or "rejected" in field for field in BatchSummary.model_fields)
        return {
            "graph_add_strict_serialize": True,
            "batch_create_strict_typed": batch_typed,
            "batch_create_strict_additional_body_serialize": True,
            "rejets_par_entite_dans_modeles_sdk": False,
            "preuve_serveur": False,
            "requêtes_interceptees": requests,
        }


def graphiti_probe():
    results = []
    cases = [
        # nom, IDs bruts, mode strict, contrôle brut, faute finale, lot, attendus
        ("temoin_type_declare", [1], False, True, False, False, 1, 1, False, 0),
        ("temoin_hors_plage_silencieux", [999], False, False, False, False, 1, 1, False, 0),
        ("brut_hors_plage_strict", [999], True, True, False, False, 0, 0, True, 0),
        ("brut_generique_strict", [0], True, True, False, False, 0, 0, True, 0),
        ("brut_hors_plage_permissif", [999], False, True, False, False, 1, 1, False, 1),
        ("controle_final_strict", [1], True, True, True, False, 0, 0, True, 0),
        ("controle_final_permissif", [1], False, True, True, False, 1, 1, False, 1),
        ("lot_mixte_strict", [1, 999], True, True, False, True, 1, 1, True, 0),
        ("lot_mixte_permissif", [1, 999], False, True, False, True, 2, 2, False, 1),
        ("lot_controle_final_strict", [1, 1], True, True, True, True, 0, 0, True, 0),
        ("lot_controle_final_permissif", [1, 1], False, True, True, True, 2, 2, False, 2),
    ]
    for name, ids, strict, enabled, fault, batch, node_count, episode_count, rejection, warning_count in cases:
        graph_id = f"dor0072_{uuid.uuid4().hex}"
        llm = ProbeLLM(ids, strict, enabled)
        driver = Neo4jDriver(
            uri=os.environ["NEO4J_URI"], user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ["NEO4J_PASSWORD"],
        )
        embedder = ProbeEmbedder()
        encoder = LocalPassthroughCrossEncoder()
        engine = ProbeGraphiti(strict=strict, final_fault=fault, graph_driver=driver,
                               llm_client=llm, embedder=embedder, cross_encoder=encoder)
        store = GraphitiGraphStore(driver=driver, graphiti=engine, llm_client=llm,
                                  embedder=embedder, cross_encoder=encoder)
        try:
            store.set_ontology(graph_id, {"entity_types": [{"name": "Person", "description": "Personne."}],
                                          "edge_types": []}, strict=strict)
            rejected = False
            rejection_message = ""
            try:
                if batch:
                    store.add_text_batch(graph_id, [f"Fragment {i}" for i in range(len(ids))])
                else:
                    store.add_episode(graph_id, "Texte de preuve.")
            except GraphValidationError as exc:
                rejection_message = str(exc)
                rejected = True
            records = store._extract_records(store._run_async(store._execute_cypher(
                "MATCH (n {group_id: $gid}) RETURN labels(n) AS labels, properties(n) AS props",
                {"gid": graph_id},
            )))
            nodes = [record for record in records if "Entity" in record["labels"]]
            episodes = [record for record in records if "Episodic" in record["labels"]]
            relations = store._extract_records(store._run_async(store._execute_cypher(
                "MATCH (n {group_id: $gid})-[r]->() RETURN type(r) AS type",
                {"gid": graph_id},
            )))
            assert len(relations) == node_count, (name, relations)
            assert all(record["type"] == "MENTIONS" for record in relations), name
            assert rejected == rejection, (name, rejection_message)
            if rejection:
                assert "Type extrait refusé" in rejection_message or "Type final refusé" in rejection_message, (name, rejection_message)
            assert len(nodes) == node_count, (name, records)
            assert len(episodes) == episode_count, name
            assert engine.delegated_saves == episode_count, name
            warnings = llm.warnings + engine.warnings
            assert len(warnings) == warning_count, (name, warnings)
            assert all(set(node["labels"]) <= {"Entity", "Person"} for node in nodes), name
            if fault and not strict:
                assert all(node["labels"] == ["Entity"] for node in nodes), name
                assert all("entity_type" not in node["props"] for node in nodes), name
            if 999 in ids and not strict:
                assert any(node["labels"] == ["Entity"] for node in nodes), name
            results.append({"cas": name, "refus": rejected, "noeuds": len(nodes),
                            "episodes": len(episodes), "relations": len(relations), "warnings": warnings,
                            "controles_finaux": engine.gate_calls,
                            "delegations_sauvegarde": engine.delegated_saves,
                            "message_refus": rejection_message})
        finally:
            # Uniquement le graphe aléatoire créé par CE cas. Aucun volume effacé.
            store._run_async(store._execute_cypher(
                "MATCH (n {group_id: $gid}) DETACH DELETE n", {"gid": graph_id},
            ))
            remaining = store._extract_records(store._run_async(store._execute_cypher(
                "MATCH (n {group_id: $gid}) RETURN count(n) AS count", {"gid": graph_id},
            )))
            assert remaining[0]["count"] == 0, (name, "Nettoyage incomplet")
            store._run_async(driver.close())
            store.close()
    return results


if __name__ == "__main__":
    assert version("graphiti-core") == "0.30.2"
    assert version("zep-cloud") == "3.25.0"
    sources = [inspect.getfile(Graphiti), inspect.getfile(node_operations)]
    from zep_cloud.graph.raw_client import RawGraphClient
    from zep_cloud.batch.raw_client import RawBatchClient
    sources += [inspect.getfile(RawGraphClient), inspect.getfile(RawBatchClient)]
    report = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "versions": {name: version(name) for name in ("graphiti-core", "zep-cloud", "neo4j")},
        "sources_sha256": {Path(path).as_posix().split("/site-packages/")[-1]: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                           for path in sources},
        "zep": zep_probe(),
        "graphiti": graphiti_probe(),
        "verdict_dor_contractuel": "NO-GO : C2 Zep non démontré",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
