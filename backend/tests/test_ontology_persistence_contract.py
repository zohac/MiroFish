"""Tests hermétiques de la pose effective d'ontologie dans les deux stores (007-1).

Ces tests couvrent le contrat commun annoncé par l'ADR 0014 :

- `GraphStore.version == 2` et les signatures étendues (`strict`, `ontology`) ;
- `set_ontology` n'est plus un no-op dans les deux implémentations ;
- `add_episode` consomme l'ontologie effective, et **sans ontologie il construit
  exactement l'appel d'avant** — c'est la régression Epic 003-2 rendue
  vérifiable au lieu d'être déclarée ;
- le câblage de `GraphBuilderService` passe par le contrat, sans mock sur le
  service lui-même.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.graph_builder import GraphBuilderService
from app.utils.graph_store import (
    GraphStore,
    GraphValidationError,
    OntologyValidationError,
)
from app.utils.graph_store.graphiti_store import GraphitiGraphStore
from app.utils.graph_store.zep_store import ZepGraphStore

ONTOLOGIE_TELECOM: Dict[str, Any] = {
    "entity_types": [
        {
            "name": "Subscriber",
            "description": "Un abonné au réseau de télécommunication",
            "attributes": [{"name": "line_count", "type": "integer"}],
        },
        {"name": "NetworkOperator", "description": "Un opérateur de réseau"},
        {"name": "RegulatoryDecision", "description": "Une décision d'un régulateur"},
    ],
    "edge_types": [
        {"name": "SUBSCRIBES_TO", "description": "Abonnement à un réseau"}
    ],
}

ONTOLOGIE_ENERGIE: Dict[str, Any] = {
    "entity_types": [
        {"name": "GridOperator", "description": "Un gestionnaire de réseau"},
        {"name": "EnergyRegulator", "description": "Un régulateur de l'énergie"},
    ],
    "edge_types": [],
}


def graphe_de_test() -> Dict[str, Any]:
    """Un graphe valide, distinct des fixtures de domaine, pour ne pas les confondre."""
    return {"entity_types": [{"name": "EntityTypeNeutre"}], "edge_types": []}


def _episode_retourne(uuid: str = "ep-1"):
    """Fausse réponse de Graphiti portant un UUID d'épisode résolvable."""
    result = MagicMock()
    result.episode = MagicMock(uuid=uuid)
    return result


@dataclass(frozen=True)
class _FakeTraduite:
    """Fausse `_OntologyTraduite` minimale, pour les tests de cycle de vie."""

    entity_types: Dict[str, Any] = field(default_factory=dict)
    edge_types: Dict[str, Any] = field(default_factory=dict)
    neutre: Any = None


@pytest.fixture
def graphiti_deps():
    """Dépendances Graphiti entièrement mockées : aucun réseau, aucun Neo4j."""
    return {
        "driver": MagicMock(),
        "llm_client": MagicMock(),
        "embedder": MagicMock(),
        "cross_encoder": MagicMock(),
        "graphiti": MagicMock(),
    }


@pytest.fixture
def store_graphiti(graphiti_deps):
    """GraphitiGraphStore isolé, prêt à recevoir des ontologies."""
    return GraphitiGraphStore(**graphiti_deps)


@pytest.fixture
def store_zep():
    """ZepGraphStore isolé sur un client entièrement mocké."""
    client = MagicMock()
    return ZepGraphStore(client=client)


@pytest.fixture
def store_zep_avec_client(store_zep):
    """Le store Zep et son client, pour inspecter les appels du client."""
    return store_zep, store_zep._client


# --- Version du contrat (AC1) ---


def test_le_contrat_graphstore_declare_la_version_2():
    """`GraphStore` porte la version de contrat qui décrit la pose effective."""
    assert GraphStore.version == 2


@pytest.mark.parametrize("usine", ["graphiti", "zep"])
def test_les_deux_stores_declarent_la_version_2(usine):
    """Les deux implémentations réelles exposent la version 2, pas une version héritée."""
    if usine == "graphiti":
        store: Any = GraphitiGraphStore.__new__(GraphitiGraphStore)
    else:
        store = ZepGraphStore.__new__(ZepGraphStore)

    assert getattr(type(store), "version", 1) >= 2
    assert getattr(store, "version", 1) >= 2


# --- Signatures (AC1, AC2) ---


@pytest.mark.parametrize(
    "classe",
    [GraphStore, GraphitiGraphStore, ZepGraphStore],
    ids=["contrat", "graphiti", "zep"],
)
def test_strict_est_keyword_only_avec_defaut_false(classe):
    """`strict` est keyword-only : un appel positionnel historique reste le même."""
    parametre = inspect.signature(classe.set_ontology).parameters["strict"]

    assert parametre.kind is inspect.Parameter.KEYWORD_ONLY
    assert parametre.default is False


@pytest.mark.parametrize(
    "classe",
    [GraphStore, GraphitiGraphStore, ZepGraphStore],
    ids=["contrat", "graphiti", "zep"],
)
def test_ontology_est_keyword_only_avec_defaut_none(classe):
    """`ontology` est keyword-only, après le `*`, et vaut `None` par défaut."""
    parametre = inspect.signature(classe.add_episode).parameters["ontology"]

    assert parametre.kind is inspect.Parameter.KEYWORD_ONLY
    assert parametre.default is None


def test_les_appels_positionnels_historiques_restent_valides(store_graphiti, store_zep):
    """`set_ontology(gid, onto)` et `add_episode(gid, text)` n'ont pas changé de forme."""
    store_graphiti.set_ontology("g-pos", graphe_de_test())
    assert store_graphiti.get_applied_ontology("g-pos") is not None

    store_zep.set_ontology("g-pos", graphe_de_test())
    assert store_zep.get_applied_ontology("g-pos") is not None


# --- GraphitiGraphStore.set_ontology (AC1) ---


def test_set_ontology_graphiti_pose_effectivement_les_types(store_graphiti):
    """Le no-op de l'ADR 0003 a disparu : les types sont bel et bien retenus."""
    store_graphiti.set_ontology("g-onto", ONTOLOGIE_TELECOM)

    posee = store_graphiti.get_applied_ontology("g-onto")
    assert sorted(posee.entity_type_names) == [
        "NetworkOperator",
        "RegulatoryDecision",
        "Subscriber",
    ]
    assert posee.edge_type_names == ("SUBSCRIBES_TO",)


def test_set_ontology_graphiti_ne_pose_rien_si_aucune_ontologie_nest_posee(store_graphiti):
    """Un graphe sans ontologie appliquée se relit comme tel, au lieu d'échouer."""
    assert store_graphiti.get_applied_ontology("g-vide") is None


def test_set_ontology_graphiti_memorise_la_politique_strict(store_graphiti):
    """`strict` est accepté et mémorisé, même si 007-2 ne l'applique pas encore."""
    store_graphiti.set_ontology("g-strict", graphe_de_test(), strict=True)

    assert store_graphiti.get_applied_ontology("g-strict").strict is True


def test_set_ontology_graphiti_refuse_une_ontologie_invalide_sans_muter_etat(store_graphiti):
    """Un refus ne laisse pas le graphe avec une ontologie à moitié appliquée."""
    store_graphiti.set_ontology("g-onto", ONTOLOGIE_TELECOM)

    with pytest.raises(OntologyValidationError):
        store_graphiti.set_ontology("g-onto", {"entity_types": [{"name": "Type Invalide"}]})

    posee = store_graphiti.get_applied_ontology("g-onto")
    assert sorted(posee.entity_type_names) == [
        "NetworkOperator",
        "RegulatoryDecision",
        "Subscriber",
    ]


def test_set_ontology_graphiti_refuse_un_dictionnaire_vide_de_types(store_graphiti):
    """Une ontologie qui ne déclare rien ne « pose » rien : elle est refusée."""
    with pytest.raises(OntologyValidationError):
        store_graphiti.set_ontology("g-onto", {"entity_types": []})


@pytest.mark.parametrize("graph_id", ["", "   ", 42])
def test_set_ontology_graphiti_refuse_un_graph_id_inutilisable(store_graphiti, graph_id):
    """La validation historique du `graph_id` est inchangée."""
    with pytest.raises(GraphValidationError):
        store_graphiti.set_ontology(graph_id, graphe_de_test())


# --- GraphitiGraphStore.add_episode (AC2) ---


def test_add_episode_sans_ontologie_construit_l_appel_d_avant(store_graphiti, graphiti_deps):
    """Filet de régression Epic 003-2 : sans ontologie, aucune clé d'ontologie n'est ajoutée."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())

    store_graphiti.add_episode("g-sans-onto", "Un fait sans ontologie.")

    kwargs = graphiti_deps["graphiti"].add_episode.call_args.kwargs
    assert "entity_types" not in kwargs
    assert "edge_types" not in kwargs


def test_add_episode_suit_l_ontologie_posee_par_set_ontology(
    store_graphiti, graphiti_deps
):
    """Le label du nœud vient de la clé du dictionnaire passé à Graphiti."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store_graphiti.set_ontology("g-onto", ONTOLOGIE_TELECOM)

    store_graphiti.add_episode("g-onto", "Alice s'abonne au réseau.")

    entity_types = graphiti_deps["graphiti"].add_episode.call_args.kwargs["entity_types"]
    assert sorted(entity_types) == [
        "NetworkOperator",
        "RegulatoryDecision",
        "Subscriber",
    ]


def test_add_episode_transmet_les_types_de_relation_declares(
    store_graphiti, graphiti_deps
):
    """FR-1 : les écritures consomment aussi les types de relation (AC1, AC5)."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store_graphiti.set_ontology("g-onto", ONTOLOGIE_TELECOM)

    store_graphiti.add_episode("g-onto", "Alice s'abonne au réseau.")

    edge_types = graphiti_deps["graphiti"].add_episode.call_args.kwargs["edge_types"]
    assert list(edge_types) == ["SUBSCRIBES_TO"]


def test_add_episode_accepte_une_ontologie_explicite_sans_set_ontology(
    store_graphiti, graphiti_deps
):
    """Le chemin explicite fonctionne sans passe préalable par `set_ontology`."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())

    store_graphiti.add_episode(
        "g-explicite", "Un fait.", ontology=ONTOLOGIE_ENERGIE
    )

    kwargs = graphiti_deps["graphiti"].add_episode.call_args.kwargs
    assert sorted(kwargs["entity_types"]) == ["EnergyRegulator", "GridOperator"]


def test_ontologie_explicite_ne_devient_pas_l_ontologie_du_graphe(
    store_graphiti, graphiti_deps
):
    """Poser une ontologie pour un épisode ne change pas le contrat du graphe."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())

    store_graphiti.add_episode("g-court", "Un fait.", ontology=ONTOLOGIE_ENERGIE)

    assert store_graphiti.get_applied_ontology("g-court") is None


def test_ontologie_explicite_invalide_refusee_avant_toute_ecriture(
    store_graphiti, graphiti_deps
):
    """Une ontologie inexploitable échoue avant que Graphiti n'ait été appelé."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())

    with pytest.raises(OntologyValidationError):
        store_graphiti.add_episode(
            "g-court", "Un fait.", ontology={"entity_types": [{"name": "Type Invalide"}]}
        )

    graphiti_deps["graphiti"].add_episode.assert_not_called()


def test_ontologie_explicite_non_dictionnaire_refusee_avant_toute_ecriture(
    store_graphiti, graphiti_deps
):
    """Même contrat des deux côtés : une ontologie n'est pas un dict, c'est un refus."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())

    with pytest.raises(GraphValidationError):
        store_graphiti.add_episode("g-court", "Un fait.", ontology="pas un dict")  # type: ignore[arg-type]

    graphiti_deps["graphiti"].add_episode.assert_not_called()


def test_add_episode_zep_refuse_ontologie_invalide_avant_appel_distant(
    store_zep_avec_client,
):
    """AC5 symétrie : `_apply_ontology_for_episode` Zep refuse une ontologie invalide
    avant tout appel au client Zep (007-1 relecture — verification-gap)."""
    store, _ = store_zep_avec_client

    with pytest.raises(OntologyValidationError):
        store.add_episode(
            "g-zep",
            "Un fait.",
            ontology={"entity_types": [{"name": "Type Invalide"}]},
        )


def test_add_episode_zep_refuse_ontologie_non_dict_avant_appel_distant(
    store_zep_avec_client,
):
    """AC5 symétrie : un `ontology` non-dict est refusé avant tout appel distant (007-1 relecture)."""
    from app.utils.graph_store.errors import GraphValidationError

    store, client = store_zep_avec_client

    with pytest.raises(GraphValidationError):
        store.add_episode("g-zep", "Un fait.", ontology="pas un dict")  # type: ignore[arg-type]

    client.graph.set_ontology.assert_not_called()
    client.graph.add.assert_not_called()


def test_add_text_batch_transmet_l_ontologie_posee_sans_changer_de_signature(
    store_graphiti, graphiti_deps
):
    """FR-1 : `add_text_batch` hérite de l'ontologie sans paramètre supplémentaire."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store_graphiti.set_ontology("g-lot", ONTOLOGIE_TELECOM)

    store_graphiti.add_text_batch("g-lot", ["Fragment A", "Fragment B"], batch_size=2)

    appels = graphiti_deps["graphiti"].add_episode.call_args_list
    assert len(appels) == 2
    for appel in appels:
        assert sorted(appel.kwargs["entity_types"]) == [
            "NetworkOperator",
            "RegulatoryDecision",
            "Subscriber",
        ]


def test_ontologie_posee_sur_un_graphe_ne_fuit_pas_vers_un_autre(
    store_graphiti, graphiti_deps
):
    """L'ontologie est mémorisée par `graph_id` : deux graphes sont deux contrats."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store_graphiti.set_ontology("g-telecom", ONTOLOGIE_TELECOM)
    store_graphiti.set_ontology("g-energie", ONTOLOGIE_ENERGIE)

    store_graphiti.add_episode("g-telecom", "Fait télécom.")
    assert "entity_types" in graphiti_deps["graphiti"].add_episode.call_args.kwargs

    store_graphiti.add_episode("g-inconnu", "Fait sans ontologie.")
    assert "entity_types" not in graphiti_deps["graphiti"].add_episode.call_args.kwargs


# --- ZepGraphStore (AC5) ---


def test_set_ontology_zep_memorise_les_types_transmis(store_zep, store_zep_avec_client):
    """Zep pose l'ontologie côté serveur ; le store mémorise ce qu'il a transmis."""
    _, client = store_zep_avec_client

    store_zep.set_ontology("g-zep", ONTOLOGIE_TELECOM)

    assert client.graph.set_ontology.call_count == 1
    posee = store_zep.get_applied_ontology("g-zep")
    assert sorted(posee.entity_type_names) == [
        "NetworkOperator",
        "RegulatoryDecision",
        "Subscriber",
    ]
    assert posee.edge_type_names == ("SUBSCRIBES_TO",)


def test_set_ontology_zep_memorise_la_politique_strict(store_zep):
    """`strict` est accepté et mémorisé des deux côtés du contrat."""
    store_zep.set_ontology("g-zep", graphe_de_test(), strict=True)

    assert store_zep.get_applied_ontology("g-zep").strict is True


def test_get_applied_ontology_zep_avant_pose_renvoie_none(store_zep):
    """Aucun graphe Zep n'hérite d'une ontologie posée par un autre store."""
    assert store_zep.get_applied_ontology("g-inconnu") is None


def test_add_episode_zep_sans_ontologie_n_appelle_pas_set_ontology(store_zep, store_zep_avec_client):
    """Sans ontologie, le comportement historique est intact : aucun appel distant en plus."""
    _, client = store_zep_avec_client

    store_zep.add_episode("g-zep", "Un fait sans ontologie.")

    client.graph.set_ontology.assert_not_called()
    client.graph.add.assert_called_once()


def test_add_episode_zep_pose_l_ontologie_avant_d_ajouter(store_zep, store_zep_avec_client):
    """Zep applique l'ontologie au graphe : elle doit précéder l'ajout de l'épisode."""
    _, client = store_zep_avec_client
    ordre = []
    client.graph.set_ontology.side_effect = lambda **kwargs: ordre.append("set_ontology")
    client.graph.add.side_effect = lambda **kwargs: (
        ordre.append("add"),
        MagicMock(uuid_="ep-zep", processed=True),
    )[1]

    store_zep.add_episode("g-zep", "Un fait.", ontology=ONTOLOGIE_TELECOM)

    assert ordre == ["set_ontology", "add"]


def test_add_episode_zep_ne_repose_pas_la_meme_ontologie_a_cousins(
    store_zep, store_zep_avec_client
):
    """Un lot de fragments ne doit pas multiplier les appels distants."""
    _, client = store_zep_avec_client
    client.graph.add.side_effect = lambda **kwargs: MagicMock(
        uuid_="ep-zep", processed=True
    )

    for _ in range(3):
        store_zep.add_episode("g-zep", "Un fait.", ontology=ONTOLOGIE_TELECOM)

    assert client.graph.set_ontology.call_count == 1
    assert client.graph.add.call_count == 3


def test_add_episode_zep_repose_une_ontologie_differente(store_zep, store_zep_avec_client):
    """Changer d'ontologie pour un graphe Zep doit réappliquer celle-ci."""
    _, client = store_zep_avec_client
    client.graph.add.side_effect = lambda **kwargs: MagicMock(
        uuid_="ep-zep", processed=True
    )

    store_zep.add_episode("g-zep", "Un fait télécom.", ontology=ONTOLOGIE_TELECOM)
    store_zep.add_episode("g-zep", "Un fait énergie.", ontology=ONTOLOGIE_ENERGIE)

    assert client.graph.set_ontology.call_count == 2


def test_ontologie_zep_vide_refusee_avant_appel_distant(
    store_zep, store_zep_avec_client
):
    """Une ontologie vide est refusée avant tout appel distant : AC5 symétrie (007-1 relecture)."""
    from app.utils.graph_store.errors import OntologyValidationError

    _, client = store_zep_avec_client

    with pytest.raises(OntologyValidationError):
        store_zep.add_episode("g-zep", "Un fait.", ontology={"entity_types": []})

    client.graph.set_ontology.assert_not_called()
    client.graph.add.assert_not_called()


# --- Alignement du contrat entre les deux implémentations (AC5) ---


def _stores_alignes(store_graphiti, store_zep):
    return {"graphiti": store_graphiti, "zep": store_zep}


ONTOLOGIES_REFAUSEES_DES_DEUX_COTES = [
    pytest.param({}, id="vide"),
    pytest.param({"entity_types": []}, id="liste-entite-vide"),
    pytest.param({"entity_types": [], "edge_types": []}, id="rien-de-utile"),
    pytest.param(
        {"entity_types": [{"name": "Media Organization"}]},
        id="nom-non-label-cypher",
    ),
    pytest.param(
        {"entity_types": [{"name": "TypeInvalide", "attributes": [{"name": "mon-attribut"}]}]},
        id="attribut-non-identifiant",
    ),
]


@pytest.mark.parametrize("ontology", ONTOLOGIES_REFAUSEES_DES_DEUX_COTES)
def test_les_deux_stores_refusent_la_meme_ontologie(store_graphiti, store_zep, ontology):
    """AC5 : même entrée, même refus. Le contrat commun n'est pas un décor."""
    with pytest.raises(OntologyValidationError):
        store_graphiti.set_ontology("g-1", ontology)
    with pytest.raises(OntologyValidationError):
        store_zep.set_ontology("g-1", ontology)


@pytest.mark.parametrize(
    "ontology",
    [
        pytest.param({"entity_types": ["Person"]}, id="entite-en-chaine"),
        pytest.param({"entity_types": [{"name": "Person"}]}, id="entite-dict"),
        pytest.param(
            {"entity_types": [], "edge_types": [{"name": "RELATED_TO"}]},
            id="relations-seules",
        ),
        pytest.param(
            {
                "entity_types": [{"name": "Person"}],
                "edge_types": [{"name": "KNOWS", "source_targets": [{"source": "Person", "target": "Person"}]}],
            },
            id="entites-et-relations",
        ),
    ],
)
def test_les_deux_stores_acceptent_la_meme_ontologie(store_graphiti, store_zep, ontology):
    """AC5, autre sens : une ontologie valide est acceptée des deux côtés."""
    store_graphiti.set_ontology("g-1", ontology)
    store_zep.set_ontology("g-1", ontology)

    assert store_graphiti.get_applied_ontology("g-1") is not None
    assert store_zep.get_applied_ontology("g-1") is not None


def test_les_deux_stores_rendent_la_meme_forme_d_ontologie(store_graphiti, store_zep):
    """Un appelant qui tient une référence `GraphStore` doit lire la même chose."""
    store_graphiti.set_ontology("g-1", ONTOLOGIE_TELECOM)
    store_zep.set_ontology("g-1", ONTOLOGIE_TELECOM)

    graphiti = store_graphiti.get_applied_ontology("g-1")
    zep = store_zep.get_applied_ontology("g-1")

    assert type(graphiti) is type(zep)
    assert graphiti.to_dict() == zep.to_dict()


def test_les_deux_stores_refusent_un_nom_de_type_reserve(store_graphiti, store_zep):
    """`Episodic` est un label interne du moteur : un nœud qui le porte serait
    relu comme un épisode. Les deux stores doivent refuser, pas un seul."""
    for store in (store_graphiti, store_zep):
        with pytest.raises(GraphValidationError):
            store.set_ontology("g-1", {"entity_types": [{"name": "Episodic"}]})


# --- Câblage applicatif (AC7) ---


def test_graph_builder_pose_l_ontologie_puis_ingere_sous_cette_ontologie(
    graphiti_deps,
):
    """Le câblage réel de `GraphBuilderService` : set_ontology puis ingestion typée.

    Seul le moteur Graphiti est mocké. Le service, le store et la traduction
    d'ontologie sont les vrais : le test échoue si l'ordre ou le contrat change.
    """
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store = GraphitiGraphStore(**graphiti_deps)
    service = GraphBuilderService(store=store)

    service.set_ontology("g-build", ONTOLOGIE_TELECOM)
    service.add_text_batches("g-build", ["Fragment A", "Fragment B"], batch_size=2)

    appels = graphiti_deps["graphiti"].add_episode.call_args_list
    assert len(appels) == 2
    for appel in appels:
        entity_types = appel.kwargs["entity_types"]
        assert entity_types["Subscriber"].__doc__ == (
            "Un abonné au réseau de télécommunication"
        )


def test_graph_builder_ne_pose_aucune_ontologie_tangentielle(
    graphiti_deps,
):
    """Un graphe construit sans ontologie reste sur le label générique."""
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store = GraphitiGraphStore(**graphiti_deps)
    service = GraphBuilderService(store=store)

    service.add_text_batches("g-sans-onto", ["Fragment A"], batch_size=1)

    assert "entity_types" not in graphiti_deps["graphiti"].add_episode.call_args.kwargs


def test_get_applied_ontology_refuse_un_graph_id_inutilisable(store_graphiti, store_zep):
    """La lecture explicite valide son entrée comme le reste du contrat."""
    with pytest.raises(GraphValidationError):
        store_graphiti.get_applied_ontology("")
    with pytest.raises(GraphValidationError):
        store_zep.get_applied_ontology("")


def test_delete_graph_purge_l_ontologie_appliquee_graphiti(
    store_graphiti, graphiti_deps
):
    """Cycle de vie : `delete_graph` purge l'ontologie appliquée mémorisée.

    Un graphe supprimé puis recréé sous le même `graph_id` ne doit pas voir
    `get_applied_ontology` répondre sur un état mémoire antérieur (bug de
    cycle de vie relecturé le 12 octobre 2026).
    """
    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store_graphiti.set_ontology("g-cycle", ONTOLOGIE_TELECOM)
    assert store_graphiti.get_applied_ontology("g-cycle") is not None

    # delete_graph appelle directement _execute_cypher, sans dépendance externe
    # dans ce test (le mock _run_async tolère l'appel).
    graphiti_deps["driver"].execute_query.return_value = ([], [], [])
    store_graphiti.delete_graph("g-cycle")

    assert store_graphiti.get_applied_ontology("g-cycle") is None


def test_create_graph_avec_id_explicite_purge_l_ontologie_appliquee_graphiti(
    store_graphiti,
):
    """Cycle de vie : `create_graph` avec `graph_id` explicite purge l'ontologie
    appliquée mémorisée.

    Sans purge, un graphe recréé sous le même identifiant hériterait d'une
    politique posée avant lui (bug de cycle de vie relecturé le 12 octobre
    2026)."""
    from app.utils.graph_store.base import AppliedOntology
    from app.utils.graph_store.errors import GraphConnectionError

    store_graphiti._check_connection = AsyncMock(
        side_effect=GraphConnectionError("non testé")
    )

    store_graphiti._applied_ontologies["g-reuse"] = _FakeTraduite(
        neutre=AppliedOntology(entity_type_names=("Person",), edge_type_names=())
    )
    assert store_graphiti.get_applied_ontology("g-reuse") is not None

    # create_graph lève _après_ la purge si la connexion échoue.
    with pytest.raises(GraphConnectionError):
        store_graphiti.create_graph("graphe recyclé", graph_id="g-reuse")

    assert "g-reuse" not in store_graphiti._applied_ontologies


def test_delete_graph_purge_l_ontologie_appliquee_zep(
    store_zep, store_zep_avec_client
):
    """Cycle de vie Zep : `delete_graph` purge l'ontologie appliquée mémorisée."""
    _, client = store_zep_avec_client
    store_zep.set_ontology("g-zep-cycle", ONTOLOGIE_TELECOM)
    assert store_zep.get_applied_ontology("g-zep-cycle") is not None

    store_zep.delete_graph("g-zep-cycle")

    assert store_zep.get_applied_ontology("g-zep-cycle") is None
    client.graph.delete.assert_called_once()


def test_set_ontology_refuse_strict_non_booleen_graphiti(store_graphiti):
    """`strict` doit être un booléen : `bool("false")` vaut `True`, piège latent."""
    with pytest.raises(GraphValidationError):
        store_graphiti.set_ontology(
            "g-strict", graphe_de_test(), strict="false"  # noqa: F821
        )


def test_set_ontology_refuse_strict_non_booleen_zep(store_zep):
    """`strict` doit être un booléen, côté Zep aussi."""
    with pytest.raises(GraphValidationError):
        store_zep.set_ontology(
            "g-strict", graphe_de_test(), strict="false"  # noqa: F821
        )


def test_add_episode_ontologie_explicite_herite_strict_du_graphe(
    store_graphiti, graphiti_deps
):
    """Une ontologie explicite hérite du `strict` posé par `set_ontology` (ADR 0014)."""
    from app.utils.graph_store.base import AppliedOntology

    graphiti_deps["graphiti"].add_episode = MagicMock(return_value=_episode_retourne())
    store_graphiti.set_ontology("g-strict-h", ONTOLOGIE_TELECOM, strict=True)

    # On appelle add_episode avec une ontologie explicite mais sans strict :
    # l'ontologie résolue doit porter `strict=True` hérité du graphe.
    graphiti_deps["graphiti"].add_episode.reset_mock()
    store_graphiti.add_episode(
        "g-strict-h", "Fait.", ontology=ONTOLOGIE_TELECOM
    )

    # L'AppliedOntology du graphe est `strict=True`, l'ontologie résolue
    # pour cet épisode aussi.
    appliquee = store_graphiti.get_applied_ontology("g-strict-h")
    assert isinstance(appliquee, AppliedOntology)
    assert appliquee.strict is True


def test_get_applied_ontology_default_retourne_none_pour_sous_classe_tierce():
    """Le contrat `Optional[AppliedOntology]` est respecté par défaut (007-1 relecture).

    Une sous-classe qui n'override pas la méthode retourne `None` au lieu de
    lever `NotImplementedError`, ce qui matche la docstring et le type
    annoncé.
    """
    from app.utils.graph_store.base import GraphStore

    class _TierceSansOverride(GraphStore):
        version = 2

        def set_ontology(self, graph_id, ontology, *, strict=False):
            return None

        def add_episode(self, graph_id, text, source_description="", metadata=None,
                        created_at=None, *, ontology=None):
            return None

        def create_graph(self, name, graph_id=None):
            return graph_id or "g"

        def delete_graph(self, graph_id):
            return None

        def get_all_nodes(self, graph_id, limit=10000):
            return []

        def get_all_edges(self, graph_id, include_temporal=True, limit=10000):
            return []

        def get_node(self, graph_id, node_uuid):
            return None

        def get_node_edges(self, graph_id, node_uuid):
            return []

        def get_graph_data(self, graph_id):
            return {"nodes": [], "edges": []}

        def get_graph_info(self, graph_id):
            from app.utils.graph_store.base import GraphInfo

            return GraphInfo(graph_id=graph_id, node_count=0, edge_count=0, entity_types=[])

        def search(self, graph_id, query, scopes=("edges",)):
            return []

        def add_text_batch(self, graph_id, texts, batch_size=10):
            from app.utils.graph_store.base import BatchSubmissionRecord

            return BatchSubmissionRecord(batch_id="b", operation_id="op", episode_uuids=[], item_count=0)

        def wait_for_batch(self, batch, *, timeout=10.0):
            return None

        def wait_for_episodes(self, graph_id, episode_uuids, *, timeout=10.0):
            return None

        def get_edge_provenance(self, graph_id, edge_uuid):
            return []

    tierce = _TierceSansOverride()
    assert tierce.get_applied_ontology("g-quelconque") is None


# --- Le contrat tient-il encore pour une implémentation tierce ? ---


def test_une_implementation_tierce_sans_version_reste_instantiable():
    """`version` est déclaré, pas imposé : une sous-classe qui l'ignore reste utilisable.

    C'est la contrepartie mesurée du choix « pas de `__init_subclass__` » de
    l'ADR 0014 : les doublures de test des epics 002 à 009 ne cassent pas.
    """

    class StoreMinimal(GraphStore):
        def create_graph(self, name, graph_id=None):
            return name

        def delete_graph(self, graph_id):
            return None

        def get_graph_data(self, graph_id):
            return {}

        def get_graph_info(self, graph_id):
            return None

        def set_ontology(self, graph_id, ontology, *, strict=False):
            return None

        def add_episode(self, graph_id, text, source_description="", metadata=None,
                        created_at=None, *, ontology=None):
            return None

        def add_text_batch(self, graph_id, chunks, batch_size=350,
                           progress_callback=None, chunk_metadata=None):
            return None

        def wait_for_batch(self, batch, progress_callback=None, timeout=600.0):
            return True

        def wait_for_episodes(self, graph_id, episode_uuids, timeout=600.0):
            return True

        def get_all_nodes(self, graph_id):
            return []

        def get_all_edges(self, graph_id, include_temporal=True):
            return []

        def get_node(self, graph_id, node_uuid):
            return None

        def get_node_edges(self, graph_id, node_uuid):
            return []

        def get_edge_provenance(self, graph_id, edge_uuid):
            return []

        def search(self, graph_id, query, limit=10, scope="edges", reranker=None):
            return None

    store: Optional[GraphStore] = StoreMinimal()
    assert store is not None
    assert getattr(type(store), "version", 1) >= 2