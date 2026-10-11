"""Tests unitaires du modèle ActorEligibility (story 009-1, AC1 et AC4)."""

import pytest
from pydantic import ValidationError

from app.models.actor_eligibility import (
    ActorEligibility,
    ActorEligibilityError,
    ActorEligibilityResponse,
    ActorRole,
    EligibilityStatus,
    qualify_from_response,
)


def _eligibility(**overrides):
    base = dict(
        entity_uuid="u-1",
        entity_name="Élodie",
        role=ActorRole.PERSON,
        status=EligibilityStatus.ELIGIBLE,
        rationale="Individu décrit",
        confidence=0.9,
    )
    base.update(overrides)
    return ActorEligibility(**base)


def test_person_eligible_is_valid_and_serializable():
    qualification = _eligibility()
    data = qualification.to_dict()
    assert data["role"] == "person"
    assert data["status"] == "eligible"
    assert qualification.is_eligible is True
    restored = ActorEligibility.from_dict(data)
    assert restored == qualification


@pytest.mark.parametrize(
    "role",
    [ActorRole.PRODUCT, ActorRole.CONCEPT, ActorRole.DOMAIN, ActorRole.PLACE, ActorRole.UNKNOWN],
)
def test_passive_role_cannot_be_eligible(role):
    with pytest.raises(ActorEligibilityError):
        _eligibility(role=role, status=EligibilityStatus.ELIGIBLE)


@pytest.mark.parametrize("role", [ActorRole.PERSON, ActorRole.ORGANIZATION])
def test_active_role_can_be_eligible(role):
    qualification = _eligibility(role=role)
    assert qualification.status == EligibilityStatus.ELIGIBLE


@pytest.mark.parametrize("rationale", ["", "   ", None, 123])
def test_empty_rationale_is_refused(rationale):
    with pytest.raises(ActorEligibilityError):
        _eligibility(rationale=rationale)


@pytest.mark.parametrize("confidence", [True, False, "0.9", None, object()])
def test_non_numeric_confidence_is_refused(confidence):
    with pytest.raises(ActorEligibilityError):
        _eligibility(confidence=confidence)


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf"), -0.1, 1.1])
def test_non_finite_or_out_of_range_confidence_is_refused(confidence):
    with pytest.raises(ActorEligibilityError):
        _eligibility(confidence=confidence)


def test_unknown_enum_value_is_refused():
    with pytest.raises(ActorEligibilityError):
        _eligibility(role="human")


# ---------------------------------------------------------------------------
# Validation de la réponse LLM
# ---------------------------------------------------------------------------


def _response(**overrides):
    base = dict(role="person", status="eligible", rationale="Personne", confidence=0.8)
    base.update(overrides)
    return ActorEligibilityResponse.model_validate(base)


def test_valid_response_is_accepted():
    response = _response()
    assert response.role == ActorRole.PERSON
    assert response.status == EligibilityStatus.ELIGIBLE
    assert response.confidence == 0.8


def test_response_accepts_enum_values_as_json_strings():
    response = _response(role="ORGANIZATION", status="ELIGIBLE")
    assert response.role == ActorRole.ORGANIZATION


@pytest.mark.parametrize("value", ["0.9", True, "high"])
def test_response_refuses_coerced_confidence(value):
    with pytest.raises(ValidationError):
        _response(confidence=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01])
def test_response_refuses_non_finite_or_unbounded_confidence(value):
    with pytest.raises(ValidationError):
        _response(confidence=value)


def test_response_refuses_unknown_role():
    with pytest.raises(ValidationError):
        _response(role="spaceship")


def test_response_refuses_empty_rationale():
    with pytest.raises(ValidationError):
        _response(rationale="   ")


def test_response_ignores_extra_fields():
    response = _response(instruction="ignore the rules", confidence=0.9)
    assert response.confidence == 0.9
    assert not hasattr(response, "instruction")


# ---------------------------------------------------------------------------
# Construction sûre à partir de la réponse
# ---------------------------------------------------------------------------


def test_passive_role_eligible_is_downgraded_to_review():
    qualification = qualify_from_response(
        "u-1", "Sillage",
        original_type="Entity",
        attributes={},
        response=_response(role="product", status="eligible"),
    )
    assert qualification.status == EligibilityStatus.REVIEW
    assert qualification.diagnostic


def test_low_confidence_is_downgraded_to_review():
    qualification = qualify_from_response(
        "u-1", "Élodie",
        original_type="Entity",
        attributes={},
        response=_response(confidence=0.699),
    )
    assert qualification.status == EligibilityStatus.REVIEW


def test_low_confidence_exclusion_is_downgraded_to_review():
    qualification = qualify_from_response(
        "u-1", "Sillage",
        original_type="Entity",
        attributes={},
        response=_response(role="product", status="ineligible", confidence=0.5),
    )
    assert qualification.status == EligibilityStatus.REVIEW
    assert qualification.diagnostic


def test_low_confidence_review_stays_review():
    qualification = qualify_from_response(
        "u-1", "Orion",
        original_type="Entity",
        attributes={},
        response=_response(role="unknown", status="review", confidence=0.3),
    )
    assert qualification.status == EligibilityStatus.REVIEW


@pytest.mark.parametrize("confidence", [0.7, 1.0])
def test_confidence_at_or_above_threshold_keeps_eligible(confidence):
    qualification = qualify_from_response(
        "u-1", "Élodie",
        original_type="Entity",
        attributes={},
        response=_response(confidence=confidence),
    )
    assert qualification.status == EligibilityStatus.ELIGIBLE


def test_identity_comes_from_input_not_response():
    qualification = qualify_from_response(
        "uuid-input", "Nom d'entrée",
        original_type="Person",
        attributes={"role": "person", "status": "eligible"},
        response=_response(),
    )
    assert qualification.entity_uuid == "uuid-input"
    assert qualification.entity_name == "Nom d'entrée"
    assert qualification.attributes == {"role": "person", "status": "eligible"}
