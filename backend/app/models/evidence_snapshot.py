"""Modèle de données EvidenceSnapshot (Epic 013, FR-05, C3, C7).

Capture l'empreinte cryptographique SHA-256 déterministe et les métadonnées
d'un jeu de preuves figé issu d'une simulation existante.
Garantit que deux rapports générés en mode `replay_frozen` opèrent sur des
faits strictement identiques.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class EvidenceSnapshot:
    """Instantané immuable des preuves figées d'une simulation."""

    snapshot_id: str
    simulation_id: str
    sha256_hash: str
    file_hashes: Dict[str, str]
    total_events: int
    total_actors: int
    has_archived_interviews: bool
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Sérialise le snapshot en dictionnaire."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceSnapshot:
        """Désérialise un dictionnaire en instance EvidenceSnapshot."""
        return cls(
            snapshot_id=str(data.get("snapshot_id", "")),
            simulation_id=str(data.get("simulation_id", "")),
            sha256_hash=str(data.get("sha256_hash", "")),
            file_hashes=dict(data.get("file_hashes", {})),
            total_events=int(data.get("total_events", 0)),
            total_actors=int(data.get("total_actors", 0)),
            has_archived_interviews=bool(data.get("has_archived_interviews", False)),
            created_at=str(data.get("created_at", "")),
        )
