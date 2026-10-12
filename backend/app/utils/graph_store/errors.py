"""Hiérarchie d'exceptions unifiée pour la couche GraphStore."""


class GraphStoreError(RuntimeError):
    """Erreur de base pour toutes les opérations sur le magasin de graphe."""

    pass


class GraphNotFoundError(GraphStoreError):
    """Levée lorsqu'un graphe, un nœud ou une ressource demandée n'existe pas."""

    pass


class GraphConnectionError(GraphStoreError):
    """Levée lors d'un échec réseau ou d'indisponibilité du service distant/local."""

    pass


class GraphTimeoutError(GraphStoreError, TimeoutError):
    """Levée lors de l'expiration du délai d'attente d'ingestion ou de requête."""

    pass


class GraphValidationError(GraphStoreError, ValueError):
    """Levée lorsque les paramètres fournis au magasin de graphe sont invalides."""

    pass


class OntologyValidationError(GraphValidationError):
    """Ontologie refusée : inexploitable en schéma, ou non constructible (ADR 0014).

    Sous-classe de `GraphValidationError` : un appelant qui ne connaît pas
    l'ontologie attrape la même exception qu'une entrée invalide, et un appelant
    qui la connaît distingue « le graphe est mal demandé » de « l'ontologie est
    mauvaise ».
    """

    pass
