"""Grille de score mécanique du banc de benchmark A/B (Story 013-6, AC5 à AC8).

Ce module est **pur** : il ne lit aucun fichier, n'ouvre aucune connexion, ne
sollicite aucun modèle. Il transforme des artefacts de rapport (dictionnaires
déjà chargés et Markdown déjà lu) en un jeu de métriques fermé, versionné et
strictement mécanique.

Trois règles structurent le module :

  - **Grille fermée.** ``SCORE_GRID_METRICS`` est la liste exhaustive des
    métriques publiées. Toute métrique absente des artefacts vaut ``None`` et
    s'affiche « indisponible » — jamais ``0``, qui désignerait une mesure.
  - **Aucune interprétation.** Le module ne note pas la qualité rédactionnelle,
    ne classe pas les variantes, ne désigne aucun modèle. Il publie des
    décomptes, des taux et des statuts ; l'arbitrage appartient à la revue
    aveugle (décision d'ingénierie n° 6 de la story 013-6).
  - **Dénominateur nul = échec de couverture.** Un taux dont le dénominateur
    est connu et vaut zéro est ``None`` et porte le statut « échec de
    couverture » : il ne vaut jamais ``100 %`` (AC6).

Le module est sans dépendance applicative : il ne connaît ni service, ni
modèle métier, ni configuration. Il est donc testable hors de toute stack.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Version de la grille. Elle est écrite dans le rapport de campagne : une
# grille ne change pas au milieu d'une campagne, et deux campagnes ne sont
# comparables que si leurs versions de grille sont identiques.
#
# 1.1.0 : ajout de `usage_theoretical_cost_usd` et de
# `cohort_adoption_denominator`, et respect du drapeau `usage_available`
# (revue BMAD du 20 octobre 2026 : des zéros étaient publiés pour des
# données que le fournisseur n'avait jamais fournies).
SCORE_GRID_VERSION = "1.1.0"

# Statuts de couverture (dérivés mécaniquement, jamais interprétés).
COVERAGE_STATUS_MESUREE = "mesurée"
COVERAGE_STATUS_ECHEC = "échec de couverture"
COVERAGE_STATUS_INDISPONIBLE = "indisponible"

# Verdicts de comparabilité.
VERDICT_CONTROLEE = "comparaison contrôlée"
VERDICT_NON_CONTROLEE = "comparaison non contrôlée"

# Règle de comparabilité : l'empreinte SHA-256 des preuves figées est la seule
# adresse de contenu ; l'identifiant d'instantané est un identifiant de
# *capture* (uuid par capture) et ne sert donc qu'en repli. Cette règle est
# celle déjà appliquée par l'IHM (`frontend/src/utils/reportComparison.js`,
# `evaluateComparability`) : les deux implémentations sont alignées cas par
# cas, et elle est énoncée dans le rapport pour que le lecteur puisse la
# contester.
COMPARABILITY_RULE = (
    "empreinte SHA-256 des preuves figées en priorité, "
    "identifiant d'instantané en repli"
)

# Grille fermée : la liste exhaustive des métriques publiées par le banc.
SCORE_GRID_METRICS: Tuple[str, ...] = (
    # ── Registre des affirmations (report_claims.json) ──────────────────
    "claims_total",
    "claims_verified",
    "claims_unsupported",
    "claims_contradicted",
    "claims_verification_ratio",
    "claims_action_total",
    "claims_action_verified",
    "claims_action_verification_rate",
    # ── Barrière de publication (quality_checks.json) ────────────────────
    "quality_total_checks",
    "quality_passed_checks",
    "quality_warning_checks",
    "quality_failed_checks",
    "quality_publication_status",
    "quality_is_publishable",
    # ── Couverture de cohorte (cohort_coverage.json) ────────────────────
    "cohort_total_members",
    "cohort_active_members",
    "cohort_silent_members",
    "cohort_adoption_denominator",
    "cohort_adoption_rate",
    # ── Télémétrie d'usage (usage.json) ─────────────────────────────────
    "usage_calls_count",
    "usage_prompt_tokens",
    "usage_completion_tokens",
    "usage_thinking_tokens",
    "usage_cached_tokens",
    "usage_total_tokens",
    "usage_duration_seconds",
    "usage_wall_seconds",
    "usage_estimated_cost_usd",
    "usage_theoretical_cost_usd",
    "usage_stop_reason",
    "usage_stop_message",
    "usage_finish_reasons",
    # ── Contenu rédigé (full_report.md) ─────────────────────────────────
    "report_characters",
    "report_sections",
)

# Type d'affirmation qui constitue une « assertion d'action » : une action
# concrète constatée dans les traces de la simulation. C'est le seul dénominateur
# qui porte le taux de vérification des actions (AC6).
ACTION_CLAIM_KIND = "OBSERVED_SOCIAL_ACTION"

# Statuts de vérification d'une affirmation.
VERIFICATION_VERIFIED = "VERIFIED"
VERIFICATION_UNSUPPORTED = "UNSUPPORTED"
VERIFICATION_CONTRADICTED = "CONTRADICTED"


# ──────────────────────────────────────────────────────────────────────────
# Helpers de lecture défensive
# ──────────────────────────────────────────────────────────────────────────


def _as_int(value: Any) -> Optional[int]:
    """Convertit en entier, ou ``None`` si la donnée est absente ou illisible."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _as_float(value: Any) -> Optional[float]:
    """Convertit en flottant, ou ``None`` si la donnée est absente ou illisible."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _as_text(value: Any) -> Optional[str]:
    """Convertit en texte non vide, ou ``None``."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> Optional[bool]:
    """Convertit en booléen, ou ``None`` si la donnée est absente."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return None


def _artifact(artifacts: Mapping[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """Retourne un artefact de rapport s'il est présent et exploitable."""
    raw = artifacts.get(key)
    return raw if isinstance(raw, dict) else None


def _ratio(numerator: Optional[int], denominator: Optional[int]) -> Optional[float]:
    """Taux arrondi, ou ``None`` si le dénominateur est absent ou nul.

    Un dénominateur nul n'est jamais un ``100 %`` : c'est l'échec de couverture
    (AC6). La distinction entre dénominateur *connu et nul* et dénominateur
    *inconnu* est portée par l'appelant, via le statut de couverture.
    """
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 4)


# ──────────────────────────────────────────────────────────────────────────
# Métriques par famille d'artefacts
# ──────────────────────────────────────────────────────────────────────────


def _score_claims(artifact: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Métriques du registre des affirmations.

    Le registre absent donne des métriques indisponibles (``None``), pas des
    zéros : un rapport sans registre n'a pas « zéro affirmation ».
    """
    metrics: Dict[str, Any] = {
        "claims_total": None,
        "claims_verified": None,
        "claims_unsupported": None,
        "claims_contradicted": None,
        "claims_verification_ratio": None,
        "claims_action_total": None,
        "claims_action_verified": None,
        "claims_action_verification_rate": None,
    }
    if artifact is None:
        return metrics

    raw_claims = artifact.get("claims")
    if isinstance(raw_claims, list):
        verified = sum(
            1
            for claim in raw_claims
            if isinstance(claim, dict)
            and str(claim.get("verification_status") or "").strip().upper()
            == VERIFICATION_VERIFIED
        )
        unsupported = sum(
            1
            for claim in raw_claims
            if isinstance(claim, dict)
            and str(claim.get("verification_status") or "").strip().upper()
            == VERIFICATION_UNSUPPORTED
        )
        contradicted = sum(
            1
            for claim in raw_claims
            if isinstance(claim, dict)
            and str(claim.get("verification_status") or "").strip().upper()
            == VERIFICATION_CONTRADICTED
        )
        action_total = sum(
            1
            for claim in raw_claims
            if isinstance(claim, dict)
            and str(claim.get("claim_kind") or "").strip().upper() == ACTION_CLAIM_KIND
        )
        action_verified = sum(
            1
            for claim in raw_claims
            if isinstance(claim, dict)
            and str(claim.get("claim_kind") or "").strip().upper() == ACTION_CLAIM_KIND
            and str(claim.get("verification_status") or "").strip().upper()
            == VERIFICATION_VERIFIED
        )
        metrics["claims_total"] = len(raw_claims)
        metrics["claims_verified"] = verified
        metrics["claims_unsupported"] = unsupported
        metrics["claims_contradicted"] = contradicted
        metrics["claims_verification_ratio"] = _ratio(verified, len(raw_claims))
        metrics["claims_action_total"] = action_total
        metrics["claims_action_verified"] = action_verified
        metrics["claims_action_verification_rate"] = _ratio(action_verified, action_total)
        return metrics

    # Registre sans liste d'affirmations : seuls les décomptes déclarés par
    # l'artefact sont disponibles. Le dénominateur d'actions reste inconnu,
    # donc la couverture sera marquée indisponible plutôt qu'en échec.
    metrics["claims_total"] = _as_int(artifact.get("total_claims"))
    metrics["claims_verified"] = _as_int(artifact.get("verified_claims"))
    metrics["claims_unsupported"] = _as_int(artifact.get("unsupported_claims"))
    metrics["claims_contradicted"] = _as_int(artifact.get("contradicted_claims"))
    metrics["claims_verification_ratio"] = _as_float(artifact.get("verification_ratio"))
    return metrics


def _score_quality(artifact: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Métriques de la barrière de publication."""
    metrics: Dict[str, Any] = {
        "quality_total_checks": None,
        "quality_passed_checks": None,
        "quality_warning_checks": None,
        "quality_failed_checks": None,
        "quality_publication_status": None,
        "quality_is_publishable": None,
    }
    if artifact is None:
        return metrics

    metrics["quality_total_checks"] = _as_int(artifact.get("total_checks"))
    metrics["quality_passed_checks"] = _as_int(artifact.get("passed_checks"))
    metrics["quality_warning_checks"] = _as_int(artifact.get("warning_checks"))
    metrics["quality_failed_checks"] = _as_int(artifact.get("failed_checks"))
    metrics["quality_publication_status"] = _as_text(artifact.get("publication_status"))
    metrics["quality_is_publishable"] = _as_bool(artifact.get("is_publishable"))
    return metrics


def _score_cohort(artifact: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Métriques de couverture de cohorte.

    Le dénominateur du taux d'adoption est publié séparément : le modèle de
    cohorte renvoie ``0.0`` quand aucun prospect n'est éligible, ce qui est un
    « non applicable » sérialisé en zéro. Sans le dénominateur, un taux de 0 %
    et un taux indéfini seraient indiscernables (revue BMAD du 20 octobre 2026).

    Le dénominateur est calculé par le modèle métier et injecté dans
    l'artefact sous la clé ``adoption_denominator`` : la règle d'éligibilité
    reste ainsi écrite à un seul endroit.
    """
    metrics: Dict[str, Any] = {
        "cohort_total_members": None,
        "cohort_active_members": None,
        "cohort_silent_members": None,
        "cohort_adoption_denominator": None,
        "cohort_adoption_rate": None,
    }
    if artifact is None:
        return metrics

    metrics["cohort_total_members"] = _as_int(artifact.get("total_members"))
    metrics["cohort_active_members"] = _as_int(artifact.get("active_members"))
    metrics["cohort_silent_members"] = _as_int(artifact.get("silent_members"))
    denominateur = _as_int(artifact.get("adoption_denominator"))
    metrics["cohort_adoption_denominator"] = denominateur
    if denominateur == 0:
        # Dénominateur connu et nul : le taux est indéfini, pas 0 %.
        metrics["cohort_adoption_rate"] = None
    else:
        metrics["cohort_adoption_rate"] = _as_float(artifact.get("adoption_rate"))
    return metrics


def _distinct_finish_reasons(usage: Mapping[str, Any]) -> Optional[str]:
    """Liste des motifs de fin d'appel distincts, dans l'ordre d'apparition.

    ``None`` quand le journal d'appels est absent : la donnée est alors
    indisponible, pas « aucun motif de fin ».
    """
    calls = usage.get("calls")
    if not isinstance(calls, list) or not calls:
        return None
    seen: List[str] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        reason = _as_text(call.get("finish_reason"))
        if reason and reason not in seen:
            seen.append(reason)
    return ", ".join(seen) if seen else None


def _score_usage(artifact: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Métriques de télémétrie d'usage.

    Le drapeau ``usage_available`` de l'artefact fait autorité : s'il vaut
    ``False``, le fournisseur n'a renvoyé aucun objet d'usage et les
    compteurs de tokens valent 0 **par défaut de saisie**, pas par mesure.
    Les publier serait mentir sur une donnée inconnue (revue BMAD du
    20 octobre 2026) : ils sont donc déclarés indisponibles.
    """
    metrics: Dict[str, Any] = {
        "usage_calls_count": None,
        "usage_prompt_tokens": None,
        "usage_completion_tokens": None,
        "usage_thinking_tokens": None,
        "usage_cached_tokens": None,
        "usage_total_tokens": None,
        "usage_duration_seconds": None,
        "usage_wall_seconds": None,
        "usage_estimated_cost_usd": None,
        "usage_theoretical_cost_usd": None,
        "usage_stop_reason": None,
        "usage_stop_message": None,
        "usage_finish_reasons": None,
    }
    if artifact is None:
        return metrics

    metrics["usage_calls_count"] = _as_int(artifact.get("calls_count"))
    metrics["usage_duration_seconds"] = _as_float(artifact.get("duration_seconds"))
    metrics["usage_wall_seconds"] = _as_float(artifact.get("wall_seconds"))
    # Coût *estimé* : la grille tarifaire est une estimation, jamais une
    # facture. Une passerelle locale à coût nul produit 0.0, ce qui est une
    # mesure (le coût facturable est réellement nul), pas une absence.
    metrics["usage_estimated_cost_usd"] = _as_float(artifact.get("estimated_cost_usd"))
    # Coût théorique : mêmes tokens valorisés au tarif du fournisseur, hors
    # gratuité de la passerelle locale. C'est le seul chiffre informatif sur
    # une campagne locale, dont le coût facturable est nul.
    metrics["usage_theoretical_cost_usd"] = _as_float(
        artifact.get("theoretical_cost_usd")
    )
    metrics["usage_stop_reason"] = _as_text(artifact.get("stop_reason"))
    metrics["usage_stop_message"] = _as_text(artifact.get("stop_message"))
    metrics["usage_finish_reasons"] = _distinct_finish_reasons(artifact)

    if artifact.get("usage_available") is False:
        # Les compteurs de tokens sont indisponibles : ils ne mesurent rien.
        return metrics

    metrics["usage_prompt_tokens"] = _as_int(artifact.get("prompt_tokens"))
    metrics["usage_completion_tokens"] = _as_int(artifact.get("completion_tokens"))
    metrics["usage_thinking_tokens"] = _as_int(artifact.get("thinking_tokens"))
    metrics["usage_cached_tokens"] = _as_int(artifact.get("cached_tokens"))
    metrics["usage_total_tokens"] = _as_int(artifact.get("total_tokens"))
    return metrics


def _count_markdown_sections(markdown: Optional[str]) -> Optional[int]:
    """Nombre de titres de niveau 1 à 6 dans un Markdown.

    Les blocs de code sont respectés : une ligne ``#`` qui s'y trouve est du
    code, pas un titre.
    """
    if not isinstance(markdown, str):
        return None
    count = 0
    in_code_fence = False
    for raw_line in markdown.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            if 1 <= hashes <= 6 and stripped[hashes:].startswith(" "):
                count += 1
    return count


def _score_report(markdown: Optional[str]) -> Dict[str, Any]:
    """Métriques du contenu rédigé."""
    metrics: Dict[str, Any] = {
        "report_characters": None,
        "report_sections": None,
    }
    if not isinstance(markdown, str):
        return metrics
    metrics["report_characters"] = len(markdown)
    metrics["report_sections"] = _count_markdown_sections(markdown)
    return metrics


# ──────────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────────


def grid_metric_names() -> Tuple[str, ...]:
    """Retourne la grille fermée : la liste exhaustive des métriques publiées."""
    return SCORE_GRID_METRICS


def score_report_artifacts(artifacts: Mapping[str, Any]) -> Dict[str, Any]:
    """Calcule la grille de score d'une variante à partir de ses artefacts.

    Args:
        artifacts: dictionnaire des artefacts d'un rapport. Clés attendues :
            ``report_claims``, ``quality_checks``, ``cohort_coverage``,
            ``usage``, ``full_report``. Une clé absente ou illisible rend ses
            métriques indisponibles — elle n'est jamais traitée comme vide.

    Returns:
        Un dictionnaire ``{"score_grid_version", "metrics", "coverage_status",
        "artefacts_absents"}``. Les métriques sont exactement celles de
        ``SCORE_GRID_METRICS`` : ni une de plus, ni une de moins.
    """
    artifacts = artifacts or {}
    claims = _artifact(artifacts, "report_claims")
    quality = _artifact(artifacts, "quality_checks")
    cohort = _artifact(artifacts, "cohort_coverage")
    usage = _artifact(artifacts, "usage")

    metrics: Dict[str, Any] = {}
    metrics.update(_score_claims(claims))
    metrics.update(_score_quality(quality))
    metrics.update(_score_cohort(cohort))
    metrics.update(_score_usage(usage))
    metrics.update(_score_report(artifacts.get("full_report")))

    # La grille est fermée : on ne publie rien qui n'y figure pas.
    ordered_metrics = {name: metrics.get(name) for name in SCORE_GRID_METRICS}

    artefacts_absents = [
        key
        for key, value in (
            ("report_claims", claims),
            ("quality_checks", quality),
            ("cohort_coverage", cohort),
            ("usage", usage),
        )
        if value is None
    ]
    if not isinstance(artifacts.get("full_report"), str):
        artefacts_absents.append("full_report")

    return {
        "score_grid_version": SCORE_GRID_VERSION,
        "metrics": ordered_metrics,
        "coverage_status": _coverage_status(ordered_metrics, claims is not None),
        "artefacts_absents": artefacts_absents,
    }


def _coverage_status(metrics: Mapping[str, Any], claims_present: bool) -> str:
    """Détermine le statut de couverture, sans jamais le déduire d'un taux.

    - registre des affirmations absent → couverture indisponible ;
    - dénominateur d'actions inconnu → couverture indisponible ;
    - dénominateur d'actions connu et nul → échec de couverture (AC6) ;
    - sinon → couverture mesurée.
    """
    if not claims_present:
        return COVERAGE_STATUS_INDISPONIBLE
    action_total = metrics.get("claims_action_total")
    if action_total is None:
        return COVERAGE_STATUS_INDISPONIBLE
    if action_total == 0:
        return COVERAGE_STATUS_ECHEC
    return COVERAGE_STATUS_MESUREE


def evaluate_comparability(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> Dict[str, Any]:
    """Évalue la comparabilité de deux jeux de preuves figées.

    La règle appliquée est **celle de l'IHM** (`frontend/src/utils/reportComparison.js`,
    ``evaluateComparability``), à l'identique : un instantané doit être
    présent des deux côtés, la simulation doit être la même, et l'identité des
    preuves est établie par l'empreinte SHA-256 lorsqu'elle est exposée des
    deux côtés, l'identifiant d'instantané ne servant qu'en repli. Les deux
    implémentations sont donc alignées cas par cas (revue BMAD du 20 octobre
    2026 : elles divergeaient sur deux entrées).

    Le verdict ne dit jamais quelle variante est meilleure : il dit seulement
    si la comparaison est contrôlée.

    Args:
        left: empreinte gauche, avec les clés ``sha256``, ``snapshot_id`` et
            ``simulation_id``.
        right: empreinte droite, mêmes clés.

    Returns:
        Un dictionnaire décrivant le verdict, son motif en toutes lettres et
        la règle appliquée.
    """
    left = left or {}
    right = right or {}
    left_sha = _as_text(left.get("sha256"))
    right_sha = _as_text(right.get("sha256"))
    left_snapshot = _as_text(left.get("snapshot_id"))
    right_snapshot = _as_text(right.get("snapshot_id"))
    left_simulation = _as_text(left.get("simulation_id"))
    right_simulation = _as_text(right.get("simulation_id"))

    details: Dict[str, Any] = {
        "regle": COMPARABILITY_RULE,
        "verdict": VERDICT_NON_CONTROLEE,
        "preuve_identite": None,
        "gauche_sha256": left_sha,
        "droite_sha256": right_sha,
        "gauche_snapshot_id": left_snapshot,
        "droite_snapshot_id": right_snapshot,
    }

    if not left_snapshot or not right_snapshot:
        details["motif"] = (
            "L'un des deux rapports ne porte aucun instantané de preuves "
            "figées : l'identité du jeu de preuves ne peut pas être établie."
        )
        return details

    if left_simulation and right_simulation and left_simulation != right_simulation:
        details["motif"] = (
            "Les deux rapports ne portent pas la même simulation : ils ne "
            "portent pas sur le même terrain de comparaison."
        )
        return details

    if left_sha and right_sha:
        if left_sha == right_sha:
            details["verdict"] = VERDICT_CONTROLEE
            details["preuve_identite"] = "sha256"
            details["motif"] = (
                "Les deux variantes reposent sur le même jeu de preuves figées "
                "(empreinte SHA-256 identique)."
            )
            return details
        details["motif"] = (
            "Les empreintes SHA-256 des preuves diffèrent : les deux variantes "
            "n'ont pas été produites sur le même jeu de preuves, la comparaison "
            "n'est pas contrôlée."
        )
        return details

    if left_snapshot == right_snapshot:
        details["verdict"] = VERDICT_CONTROLEE
        details["preuve_identite"] = "snapshot_id"
        details["motif"] = (
            "L'empreinte SHA-256 n'est pas exposée des deux côtés ; les deux "
            "variantes partagent le même identifiant d'instantané, qui "
            "identifie une capture unique."
        )
        return details

    details["motif"] = (
        "L'empreinte SHA-256 n'est pas exposée des deux côtés et les "
        "identifiants d'instantané diffèrent : la comparaison n'est pas "
        "contrôlée."
    )
    return details


def format_metric_value(value: Any) -> str:
    """Formate une métrique pour l'affichage lisible.

    Une donnée indisponible (``None``) s'affiche « indisponible » : jamais
    ``0``, jamais une chaîne vide (AC8).
    """
    if value is None:
        return "indisponible"
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".") or "0"
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    return text or "indisponible"


def metric_difference(left: Any, right: Any) -> Optional[float]:
    """Écart brut entre deux métriques, ou ``None`` si l'une manque.

    Aucun signe n'est interprété : l'écart est une différence, jamais une
    préférence (AC9).
    """
    left_value = _as_float(left)
    right_value = _as_float(right)
    if left_value is None or right_value is None:
        return None
    return round(right_value - left_value, 6)


def iter_grid_metrics(metrics: Mapping[str, Any]) -> Iterable[Tuple[str, Any]]:
    """Itère la grille dans son ordre canonique."""
    for name in SCORE_GRID_METRICS:
        yield name, metrics.get(name)


def as_metric_sequence(metrics: Mapping[str, Any]) -> Sequence[Tuple[str, Any]]:
    """Retourne la grille sous forme de séquence ordonnée ``(nom, valeur)``."""
    return list(iter_grid_metrics(metrics))
