"""Documents sources typés, fragments et conflits (story 009-2).

Les trois décisions de ce module sont figées par l'ADR 0013 :
  - le statut de validation est déclaratif et sans effet d'ingestion ;
  - un nom de fichier ne confère aucune autorité ;
  - une contradiction conserve ses deux sources et ne se résout que par une
    règle déclarée.
"""

from __future__ import annotations

import re
import uuid as uuid_module
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

#: Longueur maximale d'un `author`/`source` libre : au-delà, ce n'est pas une
#: métadonnée de provenance mais un document collé par erreur.
MAX_METADATA_FIELD_LENGTH = 512


class DocumentRole(str, Enum):
    """Rôle sémantique d'un document source.

    Le rôle décrit **ce qu'est censé contenir** le document. Il ne dit rien de
    sa véracité : c'est le rôle de `validation_status`, et les deux sont
    indépendants.
    """

    FACTS = "facts"
    SCENARIO = "scenario"
    PERSONAS = "personas"
    HYPOTHESES = "hypotheses"
    CONSTRAINTS = "constraints"
    REFERENCE = "reference"

    @classmethod
    def default(cls) -> "DocumentRole":
        """Rôle du mode simple : le document est donné pour des faits."""
        return cls.FACTS


class DocumentValidationStatus(str, Enum):
    """Statut de validation documentaire (ADR 0013 §1).

    Aucun de ces statuts ne modifie l'ingestion, le graphe ni l'éligibilité
    d'un acteur : ils décrivent une revue humaine, pas un filtre.
    """

    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"
    CONFLICTED = "conflicted"

    @classmethod
    def default(cls) -> "DocumentValidationStatus":
        return cls.UNVALIDATED


#: Transitions autorisées. Une transition absente d'ici est refusée.
VALIDATION_TRANSITIONS: Dict[DocumentValidationStatus, tuple] = {
    DocumentValidationStatus.UNVALIDATED: (
        DocumentValidationStatus.VALIDATED,
        DocumentValidationStatus.CONFLICTED,
    ),
    DocumentValidationStatus.CONFLICTED: (
        DocumentValidationStatus.VALIDATED,
        DocumentValidationStatus.UNVALIDATED,
    ),
    DocumentValidationStatus.VALIDATED: (DocumentValidationStatus.UNVALIDATED,),
}


def can_transition(
    current: DocumentValidationStatus, target: DocumentValidationStatus
) -> bool:
    """Indique si une transition de statut est autorisée (ADR 0013 §1)."""

    return target in VALIDATION_TRANSITIONS.get(current, ())


class ConflictStatus(str, Enum):
    """État d'un conflit de sources."""

    OPEN = "open"
    RESOLVED = "resolved"


class ConflictResolutionRule(str, Enum):
    """Règles déclarées de résolution d'un conflit (ADR 0013 §2).

    Il n'existe aucune règle implicite : une résolution sans règle nommée est
    impossible à produire par ce modèle.
    """

    VALIDATION_STATUS = "validation_status"
    PRIORITY = "priority"
    RECENCY = "recency"


class InformationOrigin(str, Enum):
    """Typologie stricte des 5 origines d'information (ADR 0012, ADR 0013, PRD C7).

    Les 5 catégories exclusives sont :
      - documentary : fait issu d'un document source validé ou avec positions exactes.
      - hypothesis : hypothèse de brief ou consigne de scénario.
      - simulation : comportement d'agent ou événement enregistré lors du run.
      - inference : déduction analytique ou synthèse du LLM de rapport.
      - unknown : référence non résolue, arête héritée ou sans provenance traçable.
    """

    DOCUMENTARY = "documentary"
    HYPOTHESIS = "hypothesis"
    SIMULATION = "simulation"
    INFERENCE = "inference"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "InformationOrigin":
        """Normalise une chaîne quelconque vers l'une des 5 origines."""
        if not value or not isinstance(value, str):
            return cls.UNKNOWN
        val = value.strip().lower()
        if val in ("documentary", "document", "facts", "doc"):
            return cls.DOCUMENTARY
        if val in ("hypothesis", "scenario", "hypotheses", "hypothesis/scenario"):
            return cls.HYPOTHESIS
        if val in ("simulation", "observation", "simulated", "simulation/observation"):
            return cls.SIMULATION
        if val in ("inference", "deduction", "analysis"):
            return cls.INFERENCE
        if val in ("unknown", "inherited", "legacy", "unresolved", "unknown/inherited"):
            return cls.UNKNOWN
        return cls.UNKNOWN


class EpistemicSourceKind(str, Enum):
    """Typage épistémique strict des documents et fragments sources (Story 011-3, FR-04, C5).

    Distingue la nature réelle du contenu :
      - CANONICAL_DOCUMENT : document institutionnel, officiel ou avéré (vérité de référence).
      - HISTORICAL_CASE : cas historique ou précédent documenté préexistant.
      - PERSONA_SPECIFICATION : fiche de persona fictif ou profil synthétique créé pour le test.
      - SCENARIO_BRIEF : directive d'expérimentation, brief ou consigne de scénario.
    """

    CANONICAL_DOCUMENT = "CANONICAL_DOCUMENT"
    HISTORICAL_CASE = "HISTORICAL_CASE"
    PERSONA_SPECIFICATION = "PERSONA_SPECIFICATION"
    SCENARIO_BRIEF = "SCENARIO_BRIEF"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "EpistemicSourceKind":
        if not value or not isinstance(value, str):
            return cls.CANONICAL_DOCUMENT
        val = value.strip().upper()
        for member in cls:
            if member.value == val or member.name == val:
                return member
        if "PERSONA" in val or "PROFILE" in val or "TARGET" in val or "CIBLE" in val:
            return cls.PERSONA_SPECIFICATION
        if "SCENARIO" in val or "BRIEF" in val or "HYPOTHESIS" in val or "HYPOTHESE" in val:
            return cls.SCENARIO_BRIEF
        if "HISTORIC" in val or "CASE" in val or "ANTERIOR" in val:
            return cls.HISTORICAL_CASE
        return cls.CANONICAL_DOCUMENT


def derive_epistemic_kind(
    role: Optional[Any] = None,
    filename: Optional[str] = None,
    explicit_kind: Optional[Any] = None,
) -> EpistemicSourceKind:
    """Dérive de manière déterministe le type épistémique d'une source (AC2)."""
    if explicit_kind is not None:
        if isinstance(explicit_kind, EpistemicSourceKind):
            return explicit_kind
        return EpistemicSourceKind.from_str(str(explicit_kind))

    role_val = role.value if isinstance(role, DocumentRole) else str(role or "").lower()

    if role_val in (DocumentRole.PERSONAS.value, "personas", "persona", "profiles"):
        return EpistemicSourceKind.PERSONA_SPECIFICATION
    if role_val in (
        DocumentRole.SCENARIO.value,
        DocumentRole.HYPOTHESES.value,
        "scenario",
        "hypotheses",
        "brief",
    ):
        return EpistemicSourceKind.SCENARIO_BRIEF

    fn = str(filename or "").lower()
    if any(k in fn for k in ("persona", "cible", "profile", "target")):
        return EpistemicSourceKind.PERSONA_SPECIFICATION
    if any(k in fn for k in ("scenario", "brief", "consigne", "hypothese", "hypothesis")):
        return EpistemicSourceKind.SCENARIO_BRIEF
    if any(k in fn for k in ("historique", "historical", "archive", "litige", "case-study", "case_study", "etude-de-cas")):
        return EpistemicSourceKind.HISTORICAL_CASE
    if re.search(r"(?:^|[-_])case(?:[-_.]|$)", fn):
        return EpistemicSourceKind.HISTORICAL_CASE

    return EpistemicSourceKind.CANONICAL_DOCUMENT


def classify_record_origin(record: Any) -> InformationOrigin:
    """Détermine l'une des 5 origines d'un ProvenanceRecord ou dict de provenance (Story 011-3, C5)."""
    if record is None:
        return InformationOrigin.UNKNOWN

    def _get(key: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(key, default)
        return getattr(record, key, default)

    origin = _get("origin")
    role = _get("source_role") or _get("role")
    epistemic_kind = _get("epistemic_kind")
    filename = _get("source_filename") or _get("filename")

    # Dérivation ou lecture du type épistémique
    derived_epistemic = derive_epistemic_kind(
        role=role, filename=filename, explicit_kind=epistemic_kind
    )

    # BARRIÈRE HERMÉTIQUE C5 (AC3) :
    # Tout fait ou fragment issu d'un persona fictif ou d'un brief de scénario
    # est STRICTEMENT INTERDIT d'être qualifié DOCUMENTARY (contexte historique).
    if derived_epistemic in (
        EpistemicSourceKind.PERSONA_SPECIFICATION,
        EpistemicSourceKind.SCENARIO_BRIEF,
    ):
        return InformationOrigin.HYPOTHESIS

    # Rôle sémantique d'hypothèse ou de scénario prioritaire sur la nature documentaire
    if role in (
        DocumentRole.HYPOTHESES.value,
        DocumentRole.SCENARIO.value,
        "hypotheses",
        "scenario",
    ):
        return InformationOrigin.HYPOTHESIS

    # Fait documentaire vérifié (objet avec property is_documentary ou dict avec références valides)
    if _get("is_documentary", False):
        return InformationOrigin.DOCUMENTARY

    if origin == "document" and _get("resolved", False):
        return InformationOrigin.DOCUMENTARY

    if _get("filename") and _get("char_start") is not None and _get("char_end") is not None:
        return InformationOrigin.DOCUMENTARY

    if _get("source_filename") and _get("char_start") is not None and _get("char_end") is not None:
        return InformationOrigin.DOCUMENTARY

    if origin == "simulation" or _get("simulation_id"):
        return InformationOrigin.SIMULATION

    if origin in ("legacy", "unresolved") or not _get("resolved", True):
        return InformationOrigin.UNKNOWN

    if origin:
        return InformationOrigin.from_str(str(origin))

    return InformationOrigin.UNKNOWN


def classify_provenance_records(
    records: List[Any],
) -> tuple[InformationOrigin, List[InformationOrigin]]:
    """Détermine l'origine principale et toutes les origines distinctes d'un ensemble de ProvenanceRecord."""
    if not records:
        return InformationOrigin.UNKNOWN, [InformationOrigin.UNKNOWN]

    distinct: List[InformationOrigin] = []
    for r in records:
        o = classify_record_origin(r)
        if o not in distinct:
            distinct.append(o)

    if not distinct:
        return InformationOrigin.UNKNOWN, [InformationOrigin.UNKNOWN]

    # Priorité pour l'origine représentative :
    # Si documentaire présent -> DOCUMENTARY, sinon SIMULATION, sinon HYPOTHESIS, sinon INFERENCE, sinon UNKNOWN
    if InformationOrigin.DOCUMENTARY in distinct:
        primary = InformationOrigin.DOCUMENTARY
    elif InformationOrigin.SIMULATION in distinct:
        primary = InformationOrigin.SIMULATION
    elif InformationOrigin.HYPOTHESIS in distinct:
        primary = InformationOrigin.HYPOTHESIS
    elif InformationOrigin.INFERENCE in distinct:
        primary = InformationOrigin.INFERENCE
    else:
        primary = InformationOrigin.UNKNOWN

    return primary, distinct


class SourceDocumentError(ValueError):
    """Métadonnée de document source invalide."""


class SourceConflictError(ValueError):
    """Conflit de sources incohérent ou tentative de résolution implicite."""


def _clean_optional_text(value: Any, field_name: str) -> Optional[str]:
    """Normalise un texte facultatif, en refusant les valeurs aberrantes."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise SourceDocumentError(f"{field_name} doit être une chaîne ou None")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_METADATA_FIELD_LENGTH:
        raise SourceDocumentError(
            f"{field_name} dépasse {MAX_METADATA_FIELD_LENGTH} caractères ; "
            "ce champ décrit une provenance, il ne porte pas un document"
        )
    return cleaned


@dataclass
class SourceDocument:
    """Un fichier importé, avec son rôle et son origine.

    La construction passe **toujours** par `create_source_document`. Il n'existe
    aucun chemin qui déduise une priorité, un rôle ou une validité du nom de
    fichier : c'est ce qui rend l'absence d'autorité structurelle (ADR 0013 §1).
    """

    document_id: str
    filename: str
    role: DocumentRole
    saved_filename: str
    priority: int = 1
    date: Optional[str] = None
    total_chunks: int = 0
    author: Optional[str] = None
    source: Optional[str] = None
    validation_status: DocumentValidationStatus = DocumentValidationStatus.UNVALIDATED
    epistemic_kind: Optional[EpistemicSourceKind] = None

    def __post_init__(self) -> None:
        if not self.document_id or not str(self.document_id).strip():
            raise SourceDocumentError("document_id est requis")
        if not self.filename or not str(self.filename).strip():
            raise SourceDocumentError("filename est requis")
        if not self.saved_filename or not str(self.saved_filename).strip():
            raise SourceDocumentError("saved_filename est requis")

        try:
            self.role = DocumentRole(self.role)
        except ValueError as error:
            raise SourceDocumentError(f"rôle de document inconnu : {self.role}") from error

        try:
            self.validation_status = DocumentValidationStatus(self.validation_status)
        except ValueError as error:
            raise SourceDocumentError(
                f"statut de validation inconnu : {self.validation_status}"
            ) from error

        self.epistemic_kind = derive_epistemic_kind(
            role=self.role,
            filename=self.filename,
            explicit_kind=self.epistemic_kind,
        )

        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise SourceDocumentError("priority doit être un entier")
        if not 1 <= self.priority <= 5:
            raise SourceDocumentError("priority doit être comprise entre 1 et 5")

        if isinstance(self.total_chunks, bool) or not isinstance(self.total_chunks, int):
            raise SourceDocumentError("total_chunks doit être un entier")
        if self.total_chunks < 0:
            raise SourceDocumentError("total_chunks ne peut pas être négatif")

        self.date = _clean_optional_text(self.date, "date")
        self.author = _clean_optional_text(self.author, "author")
        self.source = _clean_optional_text(self.source, "source")

    def with_validation_status(
        self, target: DocumentValidationStatus
    ) -> "SourceDocument":
        """Retourne une copie au statut changé, en refusant une transition non déclarée."""

        target = DocumentValidationStatus(target)
        if not can_transition(self.validation_status, target):
            raise SourceDocumentError(
                f"transition de statut refusée : {self.validation_status.value} "
                f"-> {target.value}"
            )
        return SourceDocument(
            document_id=self.document_id,
            filename=self.filename,
            role=self.role,
            saved_filename=self.saved_filename,
            priority=self.priority,
            date=self.date,
            total_chunks=self.total_chunks,
            author=self.author,
            source=self.source,
            validation_status=target,
            epistemic_kind=self.epistemic_kind,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation complète, sans champ perdu."""

        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "role": self.role.value,
            "saved_filename": self.saved_filename,
            "priority": self.priority,
            "date": self.date,
            "total_chunks": self.total_chunks,
            "author": self.author,
            "source": self.source,
            "validation_status": self.validation_status.value,
            "epistemic_kind": (
                self.epistemic_kind.value if self.epistemic_kind else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceDocument":
        """Relit une sérialisation produite par `to_dict`."""

        if not isinstance(data, dict):
            raise SourceDocumentError("un document source se relit depuis un dictionnaire")

        return cls(
            document_id=data.get("document_id", ""),
            filename=data.get("filename", ""),
            role=data.get("role", DocumentRole.FACTS.value),
            saved_filename=data.get("saved_filename", ""),
            priority=data.get("priority", 1),
            date=data.get("date"),
            total_chunks=data.get("total_chunks", 0),
            author=data.get("author"),
            source=data.get("source"),
            validation_status=data.get(
                "validation_status", DocumentValidationStatus.UNVALIDATED.value
            ),
            epistemic_kind=data.get("epistemic_kind"),
        )


def create_source_document(
    *,
    filename: str,
    saved_filename: str,
    role: Any = None,
    priority: Optional[int] = None,
    date: Optional[str] = None,
    author: Optional[str] = None,
    source: Optional[str] = None,
    validation_status: Any = None,
    document_id: Optional[str] = None,
    total_chunks: int = 0,
    epistemic_kind: Optional[Any] = None,
) -> SourceDocument:
    """Crée un `SourceDocument` en mode simple par défaut."""

    return SourceDocument(
        document_id=document_id or f"doc_{uuid_module.uuid4().hex[:12]}",
        filename=filename,
        role=DocumentRole.FACTS if role is None else role,
        saved_filename=saved_filename,
        priority=1 if priority is None else priority,
        date=date,
        total_chunks=total_chunks,
        author=author,
        source=source,
        validation_status=(
            DocumentValidationStatus.UNVALIDATED
            if validation_status is None
            else validation_status
        ),
        epistemic_kind=epistemic_kind,
    )


@dataclass
class DocumentChunk:
    """Un fragment de document, avec sa position exacte dans le texte normalisé.

    Les positions comptent des **caractères du texte normalisé du document**
    (sortie de `TextProcessor.preprocess_text`), et non des octets ni des
    positions PDF. L'invariant est vérifiable :
    `document_text[char_start:char_end] == text`.
    """

    source_document_id: str
    source_filename: str
    chunk_index: int
    text: str
    source_role: DocumentRole
    char_start: int
    char_end: int
    section: Optional[str] = None
    page: Optional[int] = None
    epistemic_kind: Optional[EpistemicSourceKind] = None

    def __post_init__(self) -> None:
        if not self.source_document_id or not str(self.source_document_id).strip():
            raise SourceDocumentError("source_document_id est requis")
        if not self.source_filename or not str(self.source_filename).strip():
            raise SourceDocumentError("source_filename est requis")
        if not isinstance(self.text, str) or not self.text.strip():
            raise SourceDocumentError("un fragment doit porter un texte non vide")

        try:
            self.source_role = DocumentRole(self.source_role)
        except ValueError as error:
            raise SourceDocumentError(f"rôle de fragment inconnu : {self.source_role}") from error

        self.epistemic_kind = derive_epistemic_kind(
            role=self.source_role,
            filename=self.source_filename,
            explicit_kind=self.epistemic_kind,
        )

        for name in ("chunk_index", "char_start", "char_end"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise SourceDocumentError(f"{name} doit être un entier")
        if self.chunk_index < 0:
            raise SourceDocumentError("chunk_index doit être >= 0 (base 0, local au document)")
        if self.char_start < 0:
            raise SourceDocumentError("char_start doit être >= 0")
        if self.char_end <= self.char_start:
            raise SourceDocumentError(
                f"char_end ({self.char_end}) doit être strictement supérieur à "
                f"char_start ({self.char_start})"
            )
        if self.page is not None:
            if isinstance(self.page, bool) or not isinstance(self.page, int):
                raise SourceDocumentError("page doit être un entier ou None")
            if self.page < 1:
                raise SourceDocumentError("page doit être >= 1 quand elle est connue")

    def verify_against_document(self, document_text: str) -> bool:
        """Vérifie que la plage restituée est bien le fragment (AC2).

        Une page ou une section n'est jamais déduite d'un index : cette méthode
        ne s'occupe que du texte.
        """

        if not isinstance(document_text, str):
            return False
        return document_text[self.char_start : self.char_end] == self.text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_document_id": self.source_document_id,
            "source_filename": self.source_filename,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "source_role": self.source_role.value,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "section": self.section,
            "page": self.page,
            "epistemic_kind": (
                self.epistemic_kind.value if self.epistemic_kind else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentChunk":
        if not isinstance(data, dict):
            raise SourceDocumentError("un fragment se relit depuis un dictionnaire")
        return cls(
            source_document_id=data.get("source_document_id", ""),
            source_filename=data.get("source_filename", ""),
            chunk_index=data.get("chunk_index", 0),
            text=data.get("text", ""),
            source_role=data.get("source_role", DocumentRole.FACTS.value),
            char_start=data.get("char_start", 0),
            char_end=data.get("char_end", 0),
            section=data.get("section"),
            page=data.get("page"),
            epistemic_kind=data.get("epistemic_kind"),
        )

    def to_metadata(self) -> Dict[str, Any]:
        """ Métadonnées d'ingestion transmises au `GraphStore` (ADR 0012 §1)."""

        return {
            "source_document_id": self.source_document_id,
            "source_filename": self.source_filename,
            "chunk_index": self.chunk_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "source_role": self.source_role.value,
            "page": self.page,
            "section": self.section,
            "epistemic_kind": (
                self.epistemic_kind.value if self.epistemic_kind else None
            ),
        }


@dataclass(frozen=True)
class SourceReference:
    """ Pointeur vers une source, conservé même quand le conflit est résolu."""

    document_id: str
    filename: str
    role: DocumentRole
    priority: int
    date: Optional[str]
    validation_status: DocumentValidationStatus
    chunk_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    epistemic_kind: Optional[EpistemicSourceKind] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "role": self.role.value,
            "priority": self.priority,
            "date": self.date,
            "validation_status": self.validation_status.value,
            "chunk_index": self.chunk_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "epistemic_kind": (
                self.epistemic_kind.value if self.epistemic_kind else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceReference":
        if not isinstance(data, dict):
            raise SourceConflictError("une référence de source se relit depuis un dictionnaire")
        role_val = data.get("role", DocumentRole.FACTS.value)
        explicit_epistemic = data.get("epistemic_kind")
        epistemic_val = EpistemicSourceKind.from_str(explicit_epistemic) if explicit_epistemic else None
        return cls(
            document_id=data.get("document_id", ""),
            filename=data.get("filename", ""),
            role=DocumentRole(role_val),
            priority=data.get("priority", 1),
            date=data.get("date"),
            validation_status=DocumentValidationStatus(
                data.get("validation_status", DocumentValidationStatus.UNVALIDATED.value)
            ),
            chunk_index=data.get("chunk_index"),
            char_start=data.get("char_start"),
            char_end=data.get("char_end"),
            epistemic_kind=epistemic_val,
        )



@dataclass
class SourceConflict:
    """Deux affirmations inconciliables, **conservées toutes les deux**.

    `resolution` reste `None` tant qu'aucune règle déclarée n'a été appliquée :
    l'état « à confirmer » est donc l'état par défaut, pas un cas d'erreur.
    """

    conflict_id: str
    claim: str
    source_references: List[SourceReference] = field(default_factory=list)
    resolution_rule: Optional[ConflictResolutionRule] = None
    resolution: Optional[str] = None
    status: ConflictStatus = ConflictStatus.OPEN

    def __post_init__(self) -> None:
        if not self.claim or not str(self.claim).strip():
            raise SourceConflictError("un conflit doit nommer l'affirmation concernée")
        if not isinstance(self.source_references, list):
            raise SourceConflictError("source_references doit être une liste")
        if len(self.source_references) < 2:
            raise SourceConflictError(
                "un conflit exige au moins deux sources : en deçà, on ne compare rien"
            )
        document_ids = [ref.document_id for ref in self.source_references]
        if len(set(document_ids)) != len(document_ids):
            raise SourceConflictError(
                "les deux sources d'un conflit doivent venir de documents distincts"
            )
        try:
            self.status = ConflictStatus(self.status)
        except ValueError as error:
            raise SourceConflictError(f"état de conflit inconnu : {self.status}") from error

        if self.resolution_rule is not None:
            try:
                self.resolution_rule = ConflictResolutionRule(self.resolution_rule)
            except ValueError as error:
                raise SourceConflictError(
                    f"règle de résolution inconnue : {self.resolution_rule}"
                ) from error

        if self.resolution is not None:
            # Une résolution désigne une source connue et s'accompagne de sa
            # règle : sinon une décision sans règle nommée existerait, ce que
            # l'ADR 0013 §2 interdit.
            if self.resolution_rule is None:
                raise SourceConflictError(
                    "une résolution doit nommer la règle qui l'a produite"
                )
            if self.resolution not in document_ids:
                raise SourceConflictError(
                    f"la résolution '{self.resolution}' ne désigne aucune source du conflit"
                )
            self.status = ConflictStatus.RESOLVED

    @property
    def is_resolved(self) -> bool:
        return self.status is ConflictStatus.RESOLVED and self.resolution is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "claim": self.claim,
            "source_references": [ref.to_dict() for ref in self.source_references],
            "resolution_rule": (
                self.resolution_rule.value if self.resolution_rule is not None else None
            ),
            "resolution": self.resolution,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceConflict":
        if not isinstance(data, dict):
            raise SourceConflictError("un conflit se relit depuis un dictionnaire")
        rule = data.get("resolution_rule")
        return cls(
            conflict_id=data.get("conflict_id", ""),
            claim=data.get("claim", ""),
            source_references=[
                SourceReference.from_dict(ref)
                for ref in data.get("source_references", [])
            ],
            resolution_rule=ConflictResolutionRule(rule) if rule else None,
            resolution=data.get("resolution"),
            status=data.get("status", ConflictStatus.OPEN.value),
        )


def _rule_validation_status(
    conflict: SourceConflict,
) -> Optional[str]:
    """Règle `validation_status` : le document validé l'emporte, sinon « à confirmer »."""

    validated = [
        ref for ref in conflict.source_references
        if ref.validation_status is DocumentValidationStatus.VALIDATED
    ]
    if len(validated) == 1:
        return validated[0].document_id
    return None


def _rule_priority(conflict: SourceConflict) -> Optional[str]:
    """Règle `priority` : la priorité numérique la plus basse l'emporte."""

    best = min(ref.priority for ref in conflict.source_references)
    winners = [ref for ref in conflict.source_references if ref.priority == best]
    if len(winners) == 1:
        return winners[0].document_id
    return None


def _parse_date(value: Optional[str]) -> Optional[tuple]:
    """Normalise une date en tuple comparable, ou ``None`` si non interprétable.

    Une comparaison de chaînes est fausse dès que le format n'est pas zéro-paddé
    (`"2026-2-1"` serait « après » `"2026-12-1"`). On n'accepte donc que des
    formats ISO `YYYY`, `YYYY-MM` ou `YYYY-MM-DD`, et toute autre forme rend la
    règle inapplicable plutôt que fausse.
    """

    if not isinstance(value, str):
        return None
    match = re.match(
        r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?(?:[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?.*)?$",
        value.strip(),
    )
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 1
    day = int(match.group(3)) if match.group(3) else 1
    hour = int(match.group(4)) if match.group(4) else 0
    minute = int(match.group(5)) if match.group(5) else 0
    second = int(match.group(6)) if match.group(6) else 0
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
        return None
    return (year, month, day, hour, minute, second)


def _rule_recency(conflict: SourceConflict) -> Optional[str]:
    """Règle `recency` : la date la plus récente l'emporte ; date absente ou non
    interprétable, « à confirmer »."""

    parsed = [(ref, _parse_date(ref.date)) for ref in conflict.source_references]
    if any(value is None for _, value in parsed):
        return None
    latest = max(value for _, value in parsed)
    winners = [ref for ref, value in parsed if value == latest]
    if len(winners) == 1:
        return winners[0].document_id
    return None


_RESOLUTION_RULES = {
    ConflictResolutionRule.VALIDATION_STATUS: _rule_validation_status,
    ConflictResolutionRule.PRIORITY: _rule_priority,
    ConflictResolutionRule.RECENCY: _rule_recency,
}


def resolve_conflict(
    conflict: SourceConflict, rule: ConflictResolutionRule
) -> SourceConflict:
    """Applique une règle **déclarée** et enregistre la décision avec elle.

    Une règle qui ne départage pas laisse le conflit ouvert avec
    `resolution=None` : l'état « à confirmer » est alors un résultat correct,
    pas un échec. Les deux sources sont conservées dans tous les cas.
    """

    rule = ConflictResolutionRule(rule)
    winner = _RESOLUTION_RULES[rule](conflict)

    if winner is None:
        return SourceConflict(
            conflict_id=conflict.conflict_id,
            claim=conflict.claim,
            source_references=list(conflict.source_references),
            resolution_rule=rule,
            resolution=None,
            status=ConflictStatus.OPEN,
        )

    return SourceConflict(
        conflict_id=conflict.conflict_id,
        claim=conflict.claim,
        source_references=list(conflict.source_references),
        resolution_rule=rule,
        resolution=winner,
        status=ConflictStatus.RESOLVED,
    )


#: Marqueurs de négation reconnus, exprimés avec des frontières de mot : sans
#: elles, « personne » contiendrait « ne » et « compas » « pas ». La détection
#: reste **bornée** et le dit.
_NEGATION_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bne\b",
        r"\bn'",
        r"\bn’",
        r"\bpas\b",
        r"\baucun\w*",
        r"\binterdit\w*",
        r"\bexclu\w*",
        r"\bnot\b",
        r"\bno\b",
        r"\bnever\b",
        r"\bshall not\b",
        r"\bmust not\b",
    )
)

#: Mots outils écartés avant de comparer deux affirmations. Sans eux, deux
#: phrases sans aucun rapport partagent presque toujours un mot.
_STOPWORDS = frozenset(
    """
    a à ai aie aient aies ainsi alors après as au aucun aucune aujourd auquel aura
    aurait aux avaient avait avant avec avoir bien car ce ceci cela celle celles
    celui cependant ces cet cette ceux chaque chez comme comment dans de dedans
    dehors depuis des deux doit donc dont du elle elles en encore est et étaient
    était été être eu eux fait faire fois font hors ici il ils je la là le les leur
    leurs lorsque lui ma mais malgré me même mes moi mon ne ni nos notre nous on
    ont ou où par parce pas pendant peu peut plus pour pourquoi qu quand que quel
    quelle quelles quels qui quoi sans se selon sera serait ses si sien soit son
    sont sous soyez suis sur ta tandis te tes toi ton tous tout toute toutes très
    tu un une vos votre vous y
    """.split()
)


def _normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def _polarity(text: str) -> str:
    """Signe de polarité d'une affirmation : `negative` ou `positive`.

    Un marqueur de négation présent rend l'affirmation négative. La négation
    française standard (`ne ... pas`, `n'est pas`, `aucun`) et sa version
    anglaise (`not`, `no`, `never`) comptent donc **comme** une négation, et
    non comme une double négation qui s'annulerait.
    """

    normalised = _normalise(text)
    if any(pattern.search(normalised) for pattern in _NEGATION_PATTERNS):
        return "negative"
    return "positive"


def _content_terms(text: str) -> frozenset:
    """Termes significatifs d'une affirmation, pour vérifier qu'elle porte sur
    le même objet que l'autre.

    Deux affirmations de polarités opposées ne sont en conflit que si elles
    partagent au moins un terme significatif. Sans cette condition, « Le service
    est payant » et « Aucun remboursement n'est possible » seraient signalés
    contradictoires parce que l'une contient un marqueur négatif et l'autre non.
    """

    tokens = re.findall(r"[\w']+", _normalise(text))
    return frozenset(
        token for token in tokens
        if token not in _STOPWORDS and len(token) > 2
    )


@dataclass
class ConflictScanResult:
    """Résultat d'une détection bornée, avec ce qu'elle n'a pas couvert."""

    conflicts: List[SourceConflict] = field(default_factory=list)
    comparisons_made: int = 0
    comparisons_skipped: int = 0
    truncated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "comparisons_made": self.comparisons_made,
            "comparisons_skipped": self.comparisons_skipped,
            "truncated_at": self.truncated_at,
        }


def detect_conflicts(
    claims: List[Dict[str, Any]],
    *,
    max_comparisons: int = 200,
) -> ConflictScanResult:
    """Détecte des contradictions **bornées et explicites** (ADR 0013 §2).

    Chaque entrée de `claims` porte `claim` (l'affirmation) et
    `source_reference` (un `SourceReference` ou son dictionnaire). La fonction
    ne compare que ce qu'on lui donne, sur des signaux lexicaux de polarité, et
    **reste bornée** : au-delà de `max_comparisons` elle s'arrête et déclare
    `comparisons_skipped` / `truncated_at` plutôt que de laisser croire à une
    couverture exhaustive.
    """

    if not isinstance(claims, list):
        raise SourceConflictError("claims doit être une liste")

    normalised_claims: List[Dict[str, Any]] = []
    for entry in claims:
        if not isinstance(entry, dict):
            raise SourceConflictError("chaque affirmation doit être un dictionnaire")
        text = entry.get("claim")
        reference = entry.get("source_reference")
        if not text or not str(text).strip():
            raise SourceConflictError("chaque affirmation doit porter un texte")
        if reference is None:
            raise SourceConflictError("chaque affirmation doit porter sa source")
        if isinstance(reference, dict):
            reference = SourceReference.from_dict(reference)
        if not isinstance(reference, SourceReference):
            raise SourceConflictError("source_reference doit être une SourceReference")
        normalised_claims.append(
            {
                "claim": str(text).strip(),
                "reference": reference,
                "polarity": _polarity(str(text)),
                "terms": _content_terms(str(text)),
            }
        )

    result = ConflictScanResult()
    budget = max(0, int(max_comparisons))
    examined = 0

    for index, left in enumerate(normalised_claims):
        for right in normalised_claims[index + 1 :]:
            # Le budget compte les paires **examinées**, pas les paires retenues :
            # compter seulement les conflits trouverait ne rien consommer sur un
            # corpus sans contradiction, et la borne ne bornerait rien.
            if examined >= budget:
                result.comparisons_skipped += 1
                if result.truncated_at is None:
                    result.truncated_at = left["reference"].document_id
                continue
            examined += 1

            if left["reference"].document_id == right["reference"].document_id:
                # Deux fragments du même document ne se contredisent pas au sens
                # de ce modèle : il n'y a qu'une source, donc rien à arbitrer.
                continue

            polarities = {left["polarity"], right["polarity"]}
            if polarities != {"positive", "negative"}:
                continue

            # Deux affirmations ne se contredisent que si elles portent sur le
            # même objet : sans terme significatif commun, c'est un hasard
            # lexical, pas une contradiction.
            if not (left["terms"] & right["terms"]):
                continue

            result.comparisons_made += 1
            conflict_index = len(result.conflicts) + 1
            result.conflicts.append(
                SourceConflict(
                    conflict_id=(
                        f"conflict_{left['reference'].document_id}_"
                        f"{right['reference'].document_id}_{conflict_index}"
                    ),
                    claim=f"{left['claim']} ⟷ {right['claim']}",
                    source_references=[left["reference"], right["reference"]],
                )
            )

    return result