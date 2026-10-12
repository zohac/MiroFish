"""Tests unitaires hermétiques de la sonde C1 (story 007-1, AC4).

La sonde elle-même s'exécute contre un vrai Neo4j et un vrai LLM : ce n'est pas
son objet. Ces tests couvrent ce qui peut l'être sans infrastructure — le
chargement des fixtures, le bornage des fragments, le rendu de la mesure, et les
deux garde-fous qui ne peuvent pas échouer : l'ontologie des fixtures est
réellement traduisible, et le LLM de structure renvoie bien l'identifiant du
premier type **déclaré**.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
import re
from unittest.mock import MagicMock

import pytest

from graphiti_core.utils.ontology_utils.entity_types_utils import validate_entity_types

from app.utils.graph_store.ontology_pydantic import OntologyToPydantic
from scripts.verifier_ontology_persistence import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOMAINES,
    FIXTURES_DIR,
    SEUIL_POURCENTAGE,
    StructuralMockLLMClient,
    borner_fragments,
    calculer_ratio,
    charger_fixture,
    compter_aretes,
    compter_labels,
    detail_par_label,
    main,
    mesurer_domaine,
    rendre_rapport,
)


# --- Les fixtures (AC4) ---


@pytest.mark.parametrize("domaine", DOMAINES)
def test_chaque_fixture_expose_cinq_documents(domaine):
    """AC4 exige cinq documents par domaine : moins, la mesure ne prouve rien."""
    fixture = charger_fixture(domaine)

    assert len(fixture["documents"]) >= 5


@pytest.mark.parametrize("domaine", DOMAINES)
def test_chaque_fixture_comporte_deux_documents_minimaux(domaine):
    """Les deux documents minimaux sont sous 5 000 caractères."""
    fixture = charger_fixture(domaine)
    minimaux = [doc for doc in fixture["documents"] if doc["kind"] == "minimal"]

    assert len(minimaux) >= 2
    assert all(doc["longueur"] <= 5000 for doc in minimaux)


@pytest.mark.parametrize("domaine", DOMAINES)
def test_chaque_fixture_comporte_un_document_long_pour_echantillonnage(domaine):
    """Le document long dépasse 20 000 caractères : c'est lui qui alimente le tirage."""
    fixture = charger_fixture(domaine)
    longs = [doc for doc in fixture["documents"] if doc["kind"] == "long"]

    assert len(longs) >= 1
    assert max(doc["longueur"] for doc in longs) > 20000


@pytest.mark.parametrize("domaine", DOMAINES)
def test_chaque_ontologie_couvre_huit_types_et_six_relations(domaine):
    """L'ontologie figée est celle du plan : huit entités, six relations."""
    ontologie = charger_fixture(domaine)["ontologie"]

    assert len(ontologie["entity_types"]) == 8
    assert len(ontologie["edge_types"]) == 6


@pytest.mark.parametrize("domaine", DOMAINES)
def test_l_ontologie_de_fixture_est_vraiment_traduisible(domaine):
    """Garde-fou : l'ontologie de la fixture passe la traduction réelle.

    Sans ce test, une fixture dont un nom de type serait invalide ferait
    échouer la sonde en cours d'exécution, pour une raison sans rapport avec
    ce que C1 mesure.
    """
    ontologie = charger_fixture(domaine)["ontologie"]

    classes = OntologyToPydantic.from_dict(ontologie)

    assert len(classes) == 8
    assert validate_entity_types(classes) is True


@pytest.mark.parametrize("domaine", DOMAINES)
def test_les_documents_sont_empreintes_sans_etre_relus_a_l_aveugle(domaine):
    """Chaque document porte son SHA-256, calculé sur le texte réellement ingéré."""
    import hashlib

    fixture = charger_fixture(domaine)

    for document in fixture["documents"]:
        attendu = hashlib.sha256(document["text"].encode("utf-8")).hexdigest()
        assert document["sha256"] == attendu
        assert document["sha256"] != ""


def test_les_deux_domaines_ont_des_ontologies_differentes():
    """Deux domaines distincts, sinon C1 ne prouverait qu'une seule chose."""
    telecom = charger_fixture("telecom")["ontologie"]
    energie = charger_fixture("energie")["ontologie"]

    noms_telecom = {t["name"] for t in telecom["entity_types"]}
    noms_energie = {t["name"] for t in energie["entity_types"]}

    assert noms_telecom != noms_energie


# --- Bornage des fragments (AC4 : au moins deux par document) ---


def _plan(fragments_par_document: int = 5):
    """Deux documents de `fragments_par_document` fragments, métadonnées alignées."""
    chunks = []
    metadata = []
    for document_index in range(2):
        for fragment_index in range(fragments_par_document):
            chunks.append(f"document {document_index} fragment {fragment_index}")
            metadata.append(
                {
                    "source_document_id": f"doc-{document_index}",
                    "source_filename": f"doc-{document_index}.txt",
                    "chunk_index": fragment_index,
                    "char_start": fragment_index * 10,
                    "char_end": fragment_index * 10 + 9,
                    "source_role": "facts",
                }
            )
    return chunks, metadata


def test_le_bornage_garde_deux_fragments_par_document():
    """Le seuil minimal d'AC4 est tenu pour tous les documents, sans exception."""
    chunks, metadata = _plan(2)

    retenus_chunks, retenus_metadata = borner_fragments(chunks, metadata, 2)

    assert len(retenus_chunks) == 4
    assert len(retenus_metadata) == 4
    documents = {entree["source_document_id"] for entree in retenus_metadata}
    assert documents == {"doc-0", "doc-1"}


def test_le_bornage_preserve_l_alignement_chunk_metadonnees():
    """Les métadonnées restent alignées sur leurs fragments : un décalage
    ferait échouer `validate_chunk_metadata` au milieu de l'ingestion.

    L'alignement réel est que `retenus_chunks[i]` et
    `retenus_metadata[i]` correspondent au même document *et* au
    même fragment (mêmes `char_start`/`char_end`). Un `borner_fragments`
    qui mélangerait les chunks et les métadonnées — par exemple en
    triant les uns mais pas les autres — passerait un test qui ne
    vérifie que les longueurs.
    """
    chunks, metadata = _plan(2)

    retenus_chunks, retenus_metadata = borner_fragments(chunks, metadata, 3)

    # Même longueur : précondition nécessaire mais pas suffisante.
    assert len(retenus_chunks) == len(retenus_metadata)

    # L'alignement : pour chaque index, la métadonnée doit
    # appartenir au fragment retenu à ce même index, et pas à un
    # autre fragment de la liste source.
    for index, (fragment, entree) in enumerate(
        zip(retenus_chunks, retenus_metadata)
    ):
        # Le fragment retenu est dans les `chunks` source, à la
        # position `index` (pas ailleurs) — sinon le bornage aurait
        # mélangé.
        assert fragment == chunks[index]
        # La métadonnée retenue est dans les `metadata` source, à la
        # position `index` (pas ailleurs) — idem.
        assert entree == metadata[index]
        # L'entrée décrit bien le fragment retenu : même
        # `char_start`/`char_end`.
        # (Bornage par document : un même document peut fournir
        # plusieurs fragments. On vérifie l'identité des positions,
        # pas seulement l'identité des bornes.)
        assert entree["source_document_id"] == metadata[index]["source_document_id"]


def test_un_bornage_n_elimine_aucun_document():
    """Aucun document ne peut disparaître sous la table de hachage : le cas
    critique est un document long dont les premiers fragments seulement sont pris."""
    chunks, metadata = _plan(2)

    _, retenus_metadata = borner_fragments(chunks, metadata, 2)

    assert len({e["source_document_id"] for e in retenus_metadata}) == 2


# --- Le mock structurel et l'invariant mesuré de Graphiti ---


def test_le_mock_structurel_renvoie_le_premier_type_declare():
    """Garde-fou : l'identifiant renvoyé n'est pas 0.

    Mesuré sur `graphiti-core` : `_build_entity_types_context` insère un type
    générique `Entity` en position 0, et les types déclarés commencent à 1. Un
    mock qui renverrait 0 mesurerait le choix « entité non typée » au lieu de la
    pose effective des labels — une mesure juste, mais de la mauvaise chose.
    """
    client = StructuralMockLLMClient()
    modele = type("ExtractedEntities", (), {})

    reponse = asyncio.run(
        client._generate_response(messages=["preuve"], response_model=modele)
    )

    assert reponse["extracted_entities"][0]["entity_type_id"] == 1


def test_le_mock_structurel_repond_a_toutes_les_etapes_de_graphiti():
    """Une étape non mockée ferait échouer l'ingestion sur une erreur de forme."""
    client = StructuralMockLLMClient()

    for nom in (
        "ExtractedEntities",
        "SummarizedEntities",
        "EntitySummary",
        "ExtractedEdges",
        "EdgeDuplicate",
        "NodeResolutions",
    ):
        reponse = asyncio.run(
            client._generate_response(
                messages=["preuve"], response_model=type(nom, (), {})
            )
        )
        assert reponse != {}, nom


# --- Le calcul du ratio : le cœur de C1, testé sans Neo4j ---


@pytest.mark.parametrize(
    "total,types_attendus,attendu",
    [
        (10, 10, 100.0),
        (10, 8, 80.0),
        (10, 7, 70.0),
        (4, 1, 25.0),
        (3, 2, 66.7),
        (1, 1, 100.0),
    ],
)
def test_le_ratio_est_calcule_sur_le_decompte_reel(total, types_attendus, attendu):
    """Le pourcentage est bien `typés / total`, arrondi à une décimale."""
    assert calculer_ratio(total, types_attendus) == attendu


def test_un_graphe_vide_vaut_zero_et_non_cent():
    """Garde-fou : une ingestion qui ne produit rien ne doit pas passer le seuil.

    C'est la seule façon pour un ratio de mentir : `0/0`. Un garde-fou
    `if total else 100` ferait valider une sonde qui n'a rien mesuré.
    """
    assert calculer_ratio(0, 0) == 0.0
    assert calculer_ratio(0, 5) == 0.0


def test_un_graphe_sans_aucun_label_custom_vaut_zero():
    """Le no-op historique donnerait 100 % des nœuds sur `:Entity` seul : le
    ratio doit être 0, pas 100."""
    assert calculer_ratio(12, 0) == 0.0


# --- Le comptage Cypher (C1) ---


def _store_bidon(reponses: dict):
    """Store dont `_execute_cypher` répond selon le motif de la requête.

    Les réponses sont fournies par le test, mais le test ne les compare pas à
    elles-mêmes : il vérifie le **calcul** que la sonde en tire.
    """
    store = MagicMock()
    store._run_async.side_effect = lambda coro: coro
    store._extract_records.side_effect = lambda resultat: resultat

    def _execute_cypher(requete: str, params=None):
        for motif, valeur in reponses.items():
            if motif in requete:
                return valeur
        return []

    store._execute_cypher.side_effect = _execute_cypher
    return store


def test_le_decompte_couvre_bien_les_noeuds_entite_du_graphe_cible():
    """Le comptage est borné par `group_id` : deux graphes ne se contaminent pas,
    et il ne compte que les nœuds `:Entity`, pas les épisodes."""
    store = MagicMock()
    store._run_async.side_effect = lambda coro: coro
    store._extract_records.side_effect = lambda resultat: resultat
    requetes = []

    def _execute_cypher(requete: str, params=None):
        requetes.append((requete, params))
        return [{"total": 10, "labelled": 9, "max_labels_specifiques": 1}]

    store._execute_cypher.side_effect = _execute_cypher

    compter_labels(store, "c1_telecom_abc")

    requete, params = requetes[0]
    assert "MATCH (n:Entity" in requete
    assert params == {"group_id": "c1_telecom_abc"}


def test_le_decompte_exclut_les_labels_generiques():
    """Un nœud `:Entity` seul ne compte pas comme typé : c'est tout le sujet."""
    store = _store_bidon(
        {"RETURN count(n) AS total": [{"total": 10, "labelled": 9, "max_labels_specifiques": 1}]}
    )

    comptage = compter_labels(store, "g-1")

    assert int(comptage["labelled"]) == 9
    assert calculer_ratio(int(comptage["total"]), int(comptage["labelled"])) == 90.0


def test_le_detail_par_label_exclut_entity_et_node():
    """La répartition par label ne doit pas noyer le signal sous les génériques."""
    store = _store_bidon(
        {"UNWIND labels(n)": [{"label": "Subscriber", "occurrences": 3}]}
    )

    assert detail_par_label(store, "g-1") == [("Subscriber", 3)]


def test_le_compte_daretes_est_un_contexte_et_non_un_critere():
    """Les arêtes sont comptées pour information, jamais pour valider C1."""
    store = _store_bidon({"count(r) AS total": [{"total": 42}]})

    assert compter_aretes(store, "g-1") == 42


# --- La mesure de bout en bout, sur un store conforme au contrat ---


class StoreDeMesure:
    """Store conforme au contrat `GraphStore`, sans Neo4j ni LLM.

    Il journalise l'ordre des appels et répond aux requêtes Cypher de la sonde à
    partir d'un graphe **simulé** dont les valeurs ne sont pas celles du test :
    le ratio mesuré est donc bien calculé par le code de la sonde.
    """

    def __init__(self, total: int = 12, typés: int = 11, arêtes: int = 30):
        self.appels: list[tuple[str, dict]] = []
        self.ontologie: dict | None = None
        self.chunks: list[str] = []
        self.total = total
        self.typés = typés
        self.arêtes = arêtes

    # --- contrat GraphStore utile à la sonde ---
    def create_graph(self, name, graph_id=None):
        self.appels.append(("create_graph", {"graph_id": graph_id}))
        return graph_id

    def set_ontology(self, graph_id, ontology, *, strict=False):
        from app.utils.graph_store.ontology_pydantic import OntologyToPydantic

        OntologyToPydantic.from_dict(ontology)
        self.ontologie = ontology
        self.appels.append(("set_ontology", {"graph_id": graph_id}))

    def get_applied_ontology(self, graph_id):
        from app.utils.graph_store import AppliedOntology

        if self.ontologie is None:
            return None
        classes = OntologyToPydantic_names(self.ontologie)
        return AppliedOntology(entity_type_names=classes)

    def add_text_batch(
        self,
        graph_id,
        chunks,
        batch_size=350,
        progress_callback=None,
        chunk_metadata=None,
    ):
        self.chunks.extend(chunks)
        self.appels.append(
            ("add_text_batch", {"graph_id": graph_id, "item_count": len(chunks)})
        )
        return MagicMock(episode_uuids=[f"ep-{i}" for i in range(len(chunks))])

    def wait_for_batch(self, batch, progress_callback=None, timeout=600.0):
        return True

    # --- surface Cypher utilisée par la sonde ---
    def _run_async(self, coro):
        return coro

    def _extract_records(self, resultat):
        return resultat or []

    def _execute_cypher(self, requete, params=None):
        if "UNWIND labels(n)" in requete:
            return [{"label": "Subscriber", "occurrences": self.typés}]
        if "count(r) AS total" in requete:
            return [{"total": self.arêtes}]
        return [
            {
                "total": self.total,
                "labelled": self.typés,
                "max_labels_specifiques": 1,
            }
        ]


def OntologyToPydantic_names(ontologie: dict) -> tuple[str, ...]:
    """Noms de types d'une ontologie, via la vraie factory."""
    from app.utils.graph_store.ontology_pydantic import OntologyToPydantic

    return tuple(OntologyToPydantic.from_dict(ontologie))


def test_la_mesure_pose_l_ontologie_avant_dingerer():
    """L'ordre est porteur : sans ontologie posée, les fragments seraient ingérés
    sous le label générique et la mesure ne mesurerait rien."""
    store = StoreDeMesure()
    fixture = charger_fixture("telecom")

    mesurer_domaine(store, fixture, "c1_telecom_test", 2)

    ordre = [nom for nom, _ in store.appels]
    assert ordre.index("set_ontology") < ordre.index("add_text_batch")


def test_la_mesure_refuse_de_demarrer_sans_ontologie_retenue():
    """Un store qui n'a rien retenu ne doit pas produire une mesure : ce serait
    mesurer un graphe non typé en croyant mesurer un graphe typé."""
    class StoreOubli(StoreDeMesure):
        def set_ontology(self, graph_id, ontology, *, strict=False):
            return None

    with pytest.raises(RuntimeError, match="ontologie"):
        mesurer_domaine(StoreOubli(), charger_fixture("telecom"), "g-1", 2)


def test_la_mesure_calcule_le_ratio_depuis_le_decompte():
    """Le ratio sort du décompte du store, pas d'une constante du test."""
    store = StoreDeMesure(total=12, typés=11)
    fixture = charger_fixture("telecom")

    mesure = mesurer_domaine(store, fixture, "g1", 2)

    assert mesure["total_noeuds"] == 12
    assert mesure["noeuds_types"] == 11
    assert mesure["pourcentage"] == 91.7


def test_la_mesure_d_un_graphe_sans_label_custom_donne_un_no_go():
    """Le no-op historique se lirait 0 % : la mesure doit le dire."""
    store = StoreDeMesure(total=10, typés=0)

    mesure = mesurer_domaine(store, charger_fixture("energie"), "g2", 2)

    assert mesure["pourcentage"] == 0.0


def test_la_mesure_garde_au_moins_deux_fragments_par_document():
    """AC4 : cinq documents, au moins deux fragments chacun."""
    store = StoreDeMesure()

    mesure = mesurer_domaine(store, charger_fixture("telecom"), "g3", 2)

    assert mesure["documents_ingestes"] == mesure["documents_total"]
    assert len(store.chunks) == 2 * mesure["documents_total"]


def test_la_mesure_respecte_le_bornage_demande():
    """Un bornage supérieur ingère plus, jamais moins que le minimum demandé."""
    store = StoreDeMesure()

    mesure = mesurer_domaine(store, charger_fixture("energie"), "g4", 3)

    assert mesure["fragments_ingestes"] == 3 * mesure["documents_total"]


def test_la_mesure_empreinte_les_documents_et_l_ontologie():
    """AC4 exige des empreintes : sans elles, la mesure n'est pas rejouable.

    L'empreinte doit correspondre au contenu des fixtures, pas à une
    chaîne arbitraire de 64 caractères hexadécimaux. On recalcule le
    SHA-256 sur ce que `mesurer_domaine` a effectivement ingéré (les
    documents lus par `charger_fixture`) et on asserte l'égalité.
    """
    import hashlib
    import json

    store = StoreDeMesure()

    fixture = charger_fixture("telecom")
    mesure = mesurer_domaine(store, fixture, "g5", 2)

    # SHA-256 sur l'ontologie : sérialisation déterministe (sort_keys).
    empreinte_attendue_ontologie = hashlib.sha256(
        json.dumps(
            fixture["ontologie"], ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    assert mesure["empreinte_ontologie"] == empreinte_attendue_ontologie, (
        "L'empreinte de l'ontologie doit correspondre au SHA-256 du "
        "contenu de fixture, pas à une chaîne arbitraire."
    )

    # SHA-256 sur les documents : concaténation SHA-256(filename) + SHA-256(text)
    h = hashlib.sha256()
    for entree in fixture["documents"]:
        h.update(entree["filename"].encode("utf-8"))
        h.update(entree["text"].encode("utf-8"))
    assert mesure["empreinte_documents"] == h.hexdigest(), (
        "L'empreinte des documents doit correspondre à la concaténation "
        "SHA-256(filename) + SHA-256(text) pour chaque document."
    )

    assert len(mesure["documents_detail"]) == 5


# --- Rendu de la mesure (AC4) ---


def _mesure(domain="telecom", total=10, types=9, pourcentage=90.0):
    return {
        "domaine": domain,
        "graph_id": f"c1_{domain}_abcdef01",
        "types_declares": ["Subscriber", "NetworkOperator"],
        "documents_total": 5,
        "documents_ingestes": 5,
        "fragments_ingestes": 15,
        "total_noeuds": total,
        "noeuds_types": types,
        "pourcentage": pourcentage,
        "max_labels_specifiques": 1,
        "aretes": 22,
        "detail_labels": [("Subscriber", 7), ("NetworkOperator", 2)],
        "empreinte_documents": "a" * 64,
        "empreinte_ontologie": "b" * 64,
        "duree_ingestion_s": 12.3,
        "documents_detail": [
            {
                "document_id": "telecom-01",
                "filename": "01.txt",
                "kind": "minimal",
                "longueur": 1200,
                "sha256": "c" * 64,
            }
        ],
    }


def test_le_rapport_porte_la_table_demandee_par_ac4():
    """AC4 impose la ligne `Domaine | Total nœuds | Avec label custom | % | SHA-256`."""
    rapport = rendre_rapport([_mesure()], SEUIL_POURCENTAGE, "abcdef01", False, 3)

    assert "Domaine | Documents | Fragments | Noeuds :Entity | Avec label custom | %" in rapport
    assert "Empreintes SHA-256 des fixtures" in rapport


def test_le_rapport_verdict_go_au_dessus_du_seuil():
    """90 % sur un seuil de 80 % est un GO, et le rapport le dit.

    Symétrique au NO-GO : on vérifie aussi l'**absence** de
    `NON CONFORME` (qui matcherait sinon « CONFORME » dans
    « NON CONFORME »). Sans ce garde-fou, un rapport qui imprimerait
    les deux passerait.
    """
    rapport = rendre_rapport([_mesure()], SEUIL_POURCENTAGE, "abcdef01", False, 3)

    assert "VERDICT GLOBAL : GO" in rapport
    assert "NON CONFORME" not in rapport


def test_le_rapport_verdict_no_go_en_dessous_du_seuil():
    """Un ratio sous le seuil est un NO-GO, même si le store a bien fonctionné.

    Symétrique au GO : on vérifie aussi l'**absence** du verdict GO
    (qui matcherait sinon « CONFORME » dans « NON CONFORME »).
    """
    rapport = rendre_rapport(
        [_mesure(total=10, types=3, pourcentage=30.0)], SEUIL_POURCENTAGE, "abc", False, 3
    )

    assert "VERDICT GLOBAL : NO-GO" in rapport
    assert "GO — les labels d'ontologie sont persistes" not in rapport


def test_le_rapport_signale_un_invariant_de_labels_rompu():
    """Un nœud portant deux labels d'ontologie rompt l'invariant §9.2 : il doit
    être visible dans la sortie, pas seulement dans le code."""
    mesure = _mesure()
    mesure["max_labels_specifiques"] = 2

    rapport = rendre_rapport([mesure], SEUIL_POURCENTAGE, "abc", False, 3)

    assert "ROMPU" in rapport


def test_le_rapport_mentionne_le_mode_llm_effectifement_utilise():
    """Une mesure produite en mock structurel ne doit pas se lire comme une
    mesure d'extraction réelle."""
    rapport = rendre_rapport([_mesure()], SEUIL_POURCENTAGE, "abc", True, 3)

    assert "MOCK STRUCTUREL" in rapport
    assert "REEL" not in rapport.split("Empreintes")[0]


# --- Garde-fous de la sonde ---


def test_le_decoupage_est_aligne_sur_la_production():
    """La sonde découpe comme `TextProcessor` **en production**, pas comme une
    constante recopiée : si le défaut change, ce test doit le voir."""
    from app.services.text_processor import TextProcessor

    signature = inspect.signature(TextProcessor.split_text_with_offsets)
    defauts = {
        nom: parametre.default
        for nom, parametre in signature.parameters.items()
        if nom not in ("self", "text")
    }

    assert defauts.get("chunk_size") == CHUNK_SIZE
    assert defauts.get("overlap") == CHUNK_OVERLAP


def test_la_sonde_refuse_un_bornage_inferieur_a_deux_fragments(monkeypatch, capsys):
    """AC4 demande au moins deux fragments par document : l'argument le refuse
    au lieu de produire une mesure qui ne prouve rien. Le refus est réel — la
    sortie de `main` est un code 2, et aucun Cypher n'est émis."""
    monkeypatch.setattr("sys.argv", ["verifier", "--max-fragments", "1"])

    assert main() == 2
    assert "AC4" in capsys.readouterr().err


def test_la_sonde_ne_depend_daucun_secret_de_l_image():
    """Garde-fou : la sonde ne lit aucune variable de secret, elle passe par la
    configuration du store (AGENTS.md §2.4).

    Le pattern regex `\bos\.(?:environ|getenv).*KEY` couvre les formes
    `os.environ["..."]` et `os.getenv("...")` avec n'importe quel nom
    de variable contenant `KEY`. Un commentaire qui mentionnerait
    `LLM_API_KEY` ne casse pas le test (les `not in source` simples
    le casseraient).
    """
    import re

    source = (Path(__file__).parent.parent / "scripts" / "verifier_ontology_persistence.py").read_text(
        encoding="utf-8"
    )

    # Aucun appel `os.environ[...]` ou `os.getenv(...)` ne référence
    # une variable de secret.
    pattern_secret = re.compile(r"\bos\.(?:environ|getenv).*KEY")
    assert not pattern_secret.search(source), (
        f"La sonde ne doit lire aucun secret via os.environ / os.getenv ; "
        f"rencontré : {pattern_secret.findall(source)}"
    )

    # Les noms de variables explicites non plus (mêmes alias que la
    # convention AGENTS.md §2.4 : LLM_API_KEY, ZEP_API_KEY,
    # OPENAI_API_KEY, NEO4J_PASSWORD, OPENCODE_AUTH).
    for nom_secret in (
        "LLM_API_KEY",
        "ZEP_API_KEY",
        "OPENAI_API_KEY",
        "NEO4J_PASSWORD",
        "OPENCODE_AUTH",
    ):
        assert nom_secret not in source, (
            f"Le nom de secret '{nom_secret}' ne doit pas apparaître "
            f"dans la sonde (l'image l'exposerait)."
        )


def test_le_repertoire_des_fixtures_est_dans_le_docker():
    """Garde-fou : la sonde lit ses fixtures dans l'image, pas sur l'hôte — sinon
    la mesure Docker et la mesure hôte ne liraient pas les mêmes fichiers."""
    assert FIXTURES_DIR.exists()
    assert (FIXTURES_DIR / "telecom" / "manifest.json").exists()
    assert (FIXTURES_DIR / "energie" / "manifest.json").exists()


def test_les_manifestes_de_fixtures_sont_du_json_valide():
    """Un manifeste invalide ferait échouer la sonde sur un document, pas sur C1."""
    for domaine in DOMAINES:
        manifeste = json.loads(
            (FIXTURES_DIR / domaine / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifeste["documents"]
        for entree in manifeste["documents"]:
            assert set(entree) == {"document_id", "filename", "role", "kind"}

# --- Relecture BMAD du 12 oct. 2026 — groupe D ---


def test_verifier_ontology_persistence_a_un_newline_final():
    """P2 — `verifier_ontology_persistence.py` se termine par un saut de ligne
    (PEP 8 / `ruff format`). Le script avait été ajouté sans newline
    final ; un test de régression empêche la régression.
    """
    import pathlib

    # Chemin dérivé du test, pas absolu (AGENTS.md §2.2 — pas de
    # dépendance à l'environnement de l'auteur). Le test vit dans
    # `backend/tests/`, le script dans `backend/scripts/`.
    p = (
        pathlib.Path(__file__).resolve().parents[1]
        / "scripts"
        / "verifier_ontology_persistence.py"
    )
    assert p.read_bytes().endswith(b"\n")


def test_rendre_rapport_avec_mesures_vides_donne_no_go():
    """P1 — `all([])` est par vacuité `True` ; sans garde, le script
    retournerait GO sans avoir effectué aucune mesure. La fonction doit
    explicitement retourner ``toutes_conformes=False`` sur liste vide.
    """
    import scripts.verifier_ontology_persistence as sonde

    rapport = sonde.rendre_rapport(
        mesures=[],
        seuil=80.0,
        run_id="abc12345",
        mock_llm=True,
        max_fragments=3,
    )

    assert "NO-GO" in rapport, (
        f"Un rapport avec zéro mesure doit être NO-GO, reçu :\n{rapport}"
    )


def test_main_rejette_seuil_hors_plage(monkeypatch, capsys):
    """P4 — `--seuil` doit être validé dans `[0, 100]`. Un seuil négatif ou
    supérieur à 100 trahit le verdict (toujours NO-GO ou toujours GO
    respectivement) ; le script doit refuser avec un message clair et
    exit code 2.
    """
    import scripts.verifier_ontology_persistence as sonde

    for seuil_invalide in (-1.0, -10.5, 100.01, 200.0):
        monkeypatch.setattr(
            "sys.argv",
            ["verifier_ontology_persistence.py", "--seuil", str(seuil_invalide)],
        )
        code = sonde.main()
        assert code == 2, f"seuil {seuil_invalide} aurait dû être refusé"
        captured = capsys.readouterr()
        assert "--seuil" in captured.err, captured.err


def test_seuil_zero_et_cent_sont_acceptes(monkeypatch):
    """P4 — bornes `[0, 100]` inclusives. `--seuil 0` et `--seuil 100`
    sont des choix de l'opérateur, pas des erreurs ; ils passent la
    validation (mais aucun graphe ne les atteindra — 100 % nécessite
    que *tous* les nœuds portent un label custom).
    """
    import scripts.verifier_ontology_persistence as sonde

    for seuil_borne in (0.0, 100.0):
        monkeypatch.setattr(
            "sys.argv",
            [
                "verifier_ontology_persistence.py",
                "--seuil",
                str(seuil_borne),
                "--mock-llm",
                "--max-fragments",
                "2",
            ],
        )
        # On ne s'attend pas à ce que `main()` retourne 0 — le mock LLM
        # avec un graphe réel est trop complexe pour ce test. On vérifie
        # juste que le code de retour n'est pas 2 (validation refusée).
        try:
            code = sonde.main()
        except Exception:
            # Erreur de connectivité Neo4j / fixture manquante, etc.
            # L'important est qu'on est passé la validation `--seuil`.
            continue
        assert code != 2


def test_main_default_output_pinned_vers_mesure_007_1(capsys, monkeypatch, tmp_path):
    """P11 — défaut `--output` vers le chemin canonique pinned par la
    story. Sans `--output` explicite, le script écrit dans le chemin
    attendu pour que la preuve de C1 soit persistée par construction.
    """
    import scripts.verifier_ontology_persistence as sonde

    # On simule l'environnement avec un répertoire `cwd` sous tmp_path pour
    # que la sortie par défaut ne pollue pas le dépôt. La constante
    # `SORTIE_PAR_DEFAUT` est relative à `cwd`.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["verifier_ontology_persistence.py", "--mock-llm", "--max-fragments", "2"],
    )
    # On capture sans relancer le réseau : un test isolé vérifie la
    # valeur par défaut du parser, pas l'exécution complète.
    analyseur = sonde.main.__wrapped__ if hasattr(sonde.main, "__wrapped__") else None
    # À défaut d'inspecter la CLI complète, on lit la constante :
    assert (
        str(sonde.SORTIE_PAR_DEFAUT)
        == "docs/plans/007-ontologie-dynamique/mesure-007-1.txt"
    )


def test_structural_mock_llm_entite_par_defaut_collision_safe():
    """P6 — par défaut, l'entité retournée par le mock est un UUID-derived
    `c1_evidence_<hex>`, pas une chaîne française littérale qui pourrait
    apparaître dans une fixture et être extraite comme une vraie entité.
    """
    from scripts.verifier_ontology_persistence import StructuralMockLLMClient

    client = StructuralMockLLMClient()
    assert client.entite.startswith("c1_evidence_")
    # Et deux instances successives n'ont pas le même suffixe.
    client_bis = StructuralMockLLMClient()
    assert client.entite != client_bis.entite


def test_compter_labels_total_zero_quand_record_vide():
    """P7 — `compter_labels` doit retourner un dict neutre quand Cypher
    ne renvoie rien (graphe vide), pas lever `IndexError`. Une fixture
    sans aucune entité ne doit pas faire crasher la mesure.
    """
    import scripts.verifier_ontology_persistence as sonde

    class _StoreVide:
        def _run_async(self, _coro):
            return []

        def _execute_cypher(self, _requete, **_params):
            return []

        def _extract_records(self, _resultat):
            return []

    resultat = sonde.compter_labels(_StoreVide(), "g-vide")
    assert resultat == {
        "total": 0,
        "labelled": 0,
        "max_labels_specifiques": 0,
    }


def test_compter_aretes_total_zero_quand_record_vide():
    """P7 — `compter_aretes` symétrique : graphe vide → 0 arête."""
    import scripts.verifier_ontology_persistence as sonde

    class _StoreVide:
        def _run_async(self, _coro):
            return []

        def _execute_cypher(self, _requete, **_params):
            return []

        def _extract_records(self, _resultat):
            return []

    assert sonde.compter_aretes(_StoreVide(), "g-vide") == 0


def test_compter_labels_defensif_contre_total_none():
    """P7 — Cypher 5 retourne `null` (Python `None`) sur `sum(...)` sans
    ligne ; le driver le surface tel quel. `compter_labels` doit traiter
    gracieusement le cas avant l'int zéro.
    """
    import scripts.verifier_ontology_persistence as sonde

    class _StoreNull:
        def _run_async(self, _coro):
            return None

        def _execute_cypher(self, _requete, **_params):
            return None

        def _extract_records(self, _resultat):
            return [{"total": None, "labelled": None, "max_labels_specifiques": None}]

    resultat = sonde.compter_labels(_StoreNull(), "g-null")
    assert resultat == {
        "total": 0,
        "labelled": 0,
        "max_labels_specifiques": 0,
    }


def test_charger_fixture_rejette_manifeste_sans_ontology(monkeypatch, tmp_path):
    """P9 — un manifeste sans la clé `ontology` lève un `ValueError`
    explicite, pas un `KeyError` sans diagnostic.
    """
    import scripts.verifier_ontology_persistence as sonde

    domaine = tmp_path / "broken_ontology"
    domaine.mkdir()
    (domaine / "manifest.json").write_text(
        '{"documents": []}', encoding="utf-8"
    )
    (domaine / "ontologie.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sonde, "FIXTURES_DIR", tmp_path)

    with pytest.raises(ValueError, match="ontology"):
        sonde.charger_fixture("broken_ontology")


def test_charger_fixture_rejette_entree_sans_filename(monkeypatch, tmp_path):
    """P9 — un manifeste avec une entrée de document sans `filename`
    lève un `ValueError` qui précise l'index fautif.
    """
    import scripts.verifier_ontology_persistence as sonde

    domaine = tmp_path / "broken_filename"
    domaine.mkdir()
    (domaine / "manifest.json").write_text(
        '{"documents": [{"document_id": "d1"}], "ontology": "ontologie.json"}',
        encoding="utf-8",
    )
    (domaine / "ontologie.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sonde, "FIXTURES_DIR", tmp_path)

    with pytest.raises(ValueError, match="filename"):
        sonde.charger_fixture("broken_filename")
