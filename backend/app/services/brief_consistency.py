"""Service d'audit de cohérence biographique brief/fiches et filtrage des personas non admis (Epic 014, FR-07, C5).

Ce module garantit :
1. L'extraction déterministe d'« épisodes biographiques » (montant + mot-clé capitalisé)
   depuis des textes narratifs (brief de simulation, biographies ou personas).
2. L'audit de cohérence entre un brief de simulation et les fiches persona :
   - détection des épisodes partagés entre deux personas distincts,
   - détection des épisodes attribués par le brief à un persona et repris par un autre.
3. Le rejet Fail-Closed à la construction (BriefPersonaContradictionError).
4. Le filtrage strict du contexte de rédaction pour exclure toute mention active
   de personas non admis (statuts REVIEW ou INELIGIBLE).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class BriefPersonaContradictionError(ValueError):
    """Erreur levée quand une contradiction biographique est détectée entre le brief et les fiches persona."""


def _normalize_text(text: str) -> str:
    """Normalise une chaîne en NFKD minuscule avec suppression des espaces superflus."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return " ".join(nfkd.strip().split())


def _normalize_word_ascii(word: str) -> str:
    """Retire les accents et met en majuscules pour comparaison insensible aux accents."""
    if not word:
        return ""
    nfkd = unicodedata.normalize("NFKD", word)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


def _extract_amount_token(raw_amount: str) -> str:
    """Normalise un montant en jeton déterministe (chiffres + 'eur')."""
    if not raw_amount:
        return ""
    # Gérer les décimales superflues comme ,00 ou .00 (ex: 15,00 € -> 15eur, 29.00 € -> 29eur)
    clean_amount = re.sub(r"[,.]00(?=\s*(?:€|euros?|EUR))", "", raw_amount, flags=re.IGNORECASE)
    digits = re.sub(r"[^\d]", "", clean_amount)
    return f"{digits}eur" if digits else ""


# Mots vides à ignorer lors de l'extraction des mots-clés capitalisés (en français et anglais)
STOPWORDS_CAPITALIZED = frozenset({
    "LE", "LA", "LES", "UN", "UNE", "DES", "DU", "DE", "D", "AU", "AUX",
    "ET", "OU", "MAIS", "DONC", "OR", "NI", "CAR",
    "POUR", "PAR", "SUR", "DANS", "AVEC", "SANS", "SOUS", "VERS", "CHEZ",
    "APRES", "AVANT", "PENDANT", "DEPUIS", "ENTRE", "CONTRE",
    "CE", "CET", "CETTE", "CES", "MON", "TON", "SON", "NOTRE", "VOTRE", "LEUR",
    "IL", "ELLE", "ILS", "ELLES", "ON", "NOUS", "VOUS", "JE", "TU",
    "QUI", "QUE", "QUOI", "DONT", "OU", "QUAND", "COMMENT", "POURQUOI",
    "QUEL", "QUELLE", "QUELS", "QUELLES", "LEQUEL", "LAQUELLE", "LESQUELS", "LESQUELLES",
    "THE", "A", "AN", "AND", "OR", "BUT", "FOR", "WITH", "WITHOUT", "IN", "ON", "AT", "TO", "FROM",
    "AFTER", "BEFORE", "DURING", "SINCE",
    "EUR", "EURO", "EUROS", "TTC", "HT", "TVA", "USD", "DOLLAR", "DOLLARS", "GBP",
    "MOIS", "MENSUEL", "MENSUELLE", "MENSUELS", "MENSUELLES", "AN", "ANNEE", "ANNUEL", "ANNUELLE", "ANNUELS", "ANNUELLES",
    "SEANCE", "CONSULTATION", "SESSION", "TARIF", "TARIFS", "PRIX", "ABONNEMENT", "ABONNEMENTS",
    "FORFAIT", "FORFAITS", "OFFRE", "OFFRES", "FORMULE", "FORMULES", "PACK", "PACKS",
    "COUT", "COUTS", "CHARGE", "CHARGES", "FRAIS", "TOTAL", "NET", "BRUT",
})

# Motif d'extraction des montants monétaires : chiffres avec séparateurs éventuels suivis de €, euro(s) ou EUR
AMOUNT_PATTERN = re.compile(
    r"(?<!\w)(\d[\d\s.,]*\s?(?:€|euros?|EUR))(?!\w)",
    re.IGNORECASE,
)

# Motif de découpage en phrases (ne découpe pas sur les décimales des nombres ex: 1500.00)
SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<!\d)\.+(?:\s+|$)|(?<=\d)\.(?!\d)(?:\s+|$)|[!?;]+(?:\s+|$)|[\n\r]+",
    re.UNICODE,
)


@dataclass(frozen=True)
class BiographicalEpisode:
    """Épisode biographique normalisé."""

    signature: str          # ex: "1500eur:wordpress"
    raw_amount: str         # ex: "1 500 €"
    keyword: str            # ex: "wordpress"
    sentence: str           # phrase source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature": self.signature,
            "raw_amount": self.raw_amount,
            "keyword": self.keyword,
            "sentence": self.sentence,
        }


@dataclass
class PersonaContradiction:
    """Contradiction biographique détectée lors de l'audit."""

    signature: str
    owner: Optional[str]
    carrier: str
    other_carriers: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature": self.signature,
            "owner": self.owner,
            "carrier": self.carrier,
            "other_carriers": sorted(self.other_carriers),
            "reason": self.reason,
        }


@dataclass
class ConsistencyResult:
    """Résultat de l'audit de cohérence brief/fiches persona."""

    is_consistent: bool
    contradictions: List[PersonaContradiction] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_consistent": self.is_consistent,
            "contradictions": [c.to_dict() for c in self.contradictions],
            "diagnostics": self.diagnostics,
        }


def extract_episodes(
    text: str,
    excluded_keywords: Optional[Set[str]] = None,
) -> List[BiographicalEpisode]:
    """Extrait de manière déterministe les épisodes biographiques (montant + mot-clé).

    Règles :
    1. Découpage du texte en phrases.
    2. Pour chaque occurrence de montant (ex: 1 500 €), recherche des mots capitalisés
       d'au moins 3 caractères dans la même phrase (hors mots vides et noms de personas).
    3. Si un ou plusieurs mots-clés sont trouvés, le mot-clé le plus pertinent / proche est associé.
       À défaut de mot capitalisé, les substantifs significatifs de ≥ 4 caractères dans la phrase sont candidats.
    4. La signature est `[montant_normalisé]:[mot_clé_normalisé]`.
    """
    if not text:
        return []

    episodes: List[BiographicalEpisode] = []
    seen_signatures: Set[str] = set()

    excluded_kw_upper = {
        _normalize_word_ascii(k) for k in (excluded_keywords or set()) if k
    }

    sentences = SENTENCE_SPLIT_PATTERN.split(text)
    for raw_sentence in sentences:
        s = raw_sentence.strip()
        if not s:
            continue

        for match in AMOUNT_PATTERN.finditer(s):
            raw_amount = match.group(1).strip()
            amount_tok = _extract_amount_token(raw_amount)
            if not amount_tok or amount_tok == "eur":
                continue

            match_start = match.start()
            match_end = match.end()
            token_matches = list(re.finditer(r"\b[A-Za-zÀ-ÿ0-9_-]+\b", s))

            # Recherche des mots capitalisés dans la phrase (en excluant les tokens du montant lui-même)
            capitalized_candidates = []
            for tm in token_matches:
                if match_start <= tm.start() < match_end:
                    continue
                w = tm.group(0)
                if len(w) >= 3 and (w[0].isupper() or any(c.isupper() for c in w)):
                    norm_upper = _normalize_word_ascii(w)
                    if norm_upper not in STOPWORDS_CAPITALIZED and norm_upper not in excluded_kw_upper:
                        capitalized_candidates.append((w, tm.start()))

            chosen_keyword = ""
            if capitalized_candidates:
                # Choisir le mot capitalisé le plus proche du montant
                best_dist = float("inf")
                for cand_word, cand_pos in capitalized_candidates:
                    dist = abs(cand_pos - match_start)
                    if dist < best_dist:
                        best_dist = dist
                        chosen_keyword = cand_word
            else:
                # Repli sur les mots alphabétiques ≥ 4 caractères hors stopwords et personas
                fallback_candidates = []
                for tm in token_matches:
                    if match_start <= tm.start() < match_end:
                        continue
                    w = tm.group(0)
                    norm_upper = _normalize_word_ascii(w)
                    if (
                        len(w) >= 4
                        and norm_upper not in STOPWORDS_CAPITALIZED
                        and norm_upper not in excluded_kw_upper
                    ):
                        fallback_candidates.append((w, tm.start()))

                if fallback_candidates:
                    best_dist = float("inf")
                    for cand_word, cand_pos in fallback_candidates:
                        dist = abs(cand_pos - match_start)
                        if dist < best_dist:
                            best_dist = dist
                            chosen_keyword = cand_word

            if not chosen_keyword:
                chosen_keyword = "general"

            norm_kw = unicodedata.normalize("NFKD", chosen_keyword).lower()
            norm_kw = re.sub(r"[^a-z0-9]", "", norm_kw)
            if not norm_kw:
                norm_kw = "general"

            sig = f"{amount_tok}:{norm_kw}"
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                episodes.append(
                    BiographicalEpisode(
                        signature=sig,
                        raw_amount=raw_amount,
                        keyword=norm_kw,
                        sentence=s,
                    )
                )

    # Tri déterministe par signature puis phrase
    episodes.sort(key=lambda e: (e.signature, e.sentence))
    return episodes


def _extract_brief_attributed_episodes(brief_text: str, persona_names: List[str]) -> Dict[str, Set[str]]:
    """Associe les épisodes détectés dans le brief à des personas nommés dans la même phrase ou section.

    Renvoie un dictionnaire persona_name -> ensemble des signatures d'épisodes.
    """
    attributed: Dict[str, Set[str]] = {name: set() for name in persona_names}
    if not brief_text:
        return attributed

    excluded_kw = set(persona_names)
    sentences = SENTENCE_SPLIT_PATTERN.split(brief_text)
    for raw_sentence in sentences:
        s = raw_sentence.strip()
        if not s:
            continue

        episodes = extract_episodes(s, excluded_keywords=excluded_kw)
        if not episodes:
            continue

        # Trouver les personas mentionnés dans cette phrase
        s_norm = unicodedata.normalize("NFKD", s).lower()
        for name in persona_names:
            name_norm = unicodedata.normalize("NFKD", name).lower()
            # Chercher le nom en tant que mot entier
            if re.search(r"\b" + re.escape(name_norm) + r"\b", s_norm):
                for ep in episodes:
                    attributed[name].add(ep.signature)

    return attributed


def audit_brief_persona_consistency(
    brief_text: str,
    profiles: List[Any],
    known_personas: Optional[List[str]] = None,
    known_organizations: Optional[List[str]] = None,
) -> ConsistencyResult:
    """Audite la cohérence biographique entre un brief et une liste de profils persona.

    Les profils peuvent être des objets (OasisAgentProfile, etc.) avec attributs `name`,
    `bio`, `persona` ou des dictionnaires avec ces mêmes clés.

    Règles d'audit :
    1. AC1 — Épisode partagé par deux personas :
       Quand un même épisode biographique privé (signature montant:mot-clé) apparaît
       dans les fiches de deux personas distincts, une contradiction est signalée.
       Les montants généraux de contexte de scénario (tarifs d'offre évalués par la cohorte)
       et les entités organisationnelles ne sont pas des biographies humaines privées.
    2. AC2 / AC8 — Décalage d'attribution (owner mismatch) :
       Quand le brief attribue un épisode biographique au persona A et que la fiche du
       persona B le contient (avec B != A), une contradiction est signalée.
    3. AC3 — Un brief cohérent renvoie `is_consistent=True` et `contradictions=[]`.
    4. AC7 — Déterminisme strict : tri stable par signature puis porteur.
    """
    contradictions: List[PersonaContradiction] = []
    diagnostics: Dict[str, Any] = {
        "total_profiles": len(profiles),
        "episodes_in_brief": 0,
        "episodes_by_profile": {},
    }

    org_set = {
        unicodedata.normalize("NFKD", o).lower()
        for o in (known_organizations or set())
        if o and str(o).strip()
    }

    # 1. Identifier les personas candidats (connus en amont, ou fiches + corps du brief)
    all_candidate_names: Set[str] = set()
    if known_personas:
        for kp in known_personas:
            if kp and str(kp).strip():
                all_candidate_names.add(str(kp).strip())

    for p in profiles:
        if isinstance(p, dict):
            name = str(p.get("name") or p.get("username") or p.get("user_name") or "")
        else:
            name = str(getattr(p, "name", "") or getattr(p, "user_name", ""))
        if name.strip():
            all_candidate_names.add(name.strip())

    # Extraction prudente depuis le corps du brief
    # (permet de découvrir les personas nommés dans le brief même s'ils ne sont pas admis dans known_personas, ex: AC4)
    if brief_text:
        body_lines = [
            line.strip() for line in brief_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        body_text = "\n".join(body_lines)
        # Détecter les personas introduits sous forme de liste: - **Nom** (...)
        for match in re.finditer(r"[-*]\s*\*\*([A-Za-zÀ-ÿ0-9_\s-]+?)\*\*", body_text):
            candidate = match.group(1).strip()
            # Un nom de persona comporte généralement 1 à 3 mots et moins de 40 caractères
            if (
                candidate
                and len(candidate) <= 40
                and len(candidate.split()) <= 3
                and _normalize_word_ascii(candidate) not in STOPWORDS_CAPITALIZED
            ):
                all_candidate_names.add(candidate)
        for s in SENTENCE_SPLIT_PATTERN.split(body_text):
            for match in re.finditer(
                r"\b([A-ZÀ-ÿ][a-zà-ÿ]{2,})\s+(?:a|est|avait|était|refuse|hesite|craint|redoute|depense|paye|perd)\b",
                s,
            ):
                w = match.group(1)
                if _normalize_word_ascii(w) not in STOPWORDS_CAPITALIZED:
                    all_candidate_names.add(w)

    # 2. Extraire les fiches persona en excluant les noms de personas comme mot-clé d'épisode
    profile_episodes: Dict[str, List[BiographicalEpisode]] = {}
    profile_names: List[str] = []

    for p in profiles:
        if isinstance(p, dict):
            name = str(p.get("name") or p.get("username") or p.get("user_name") or "")
            bio = str(p.get("bio") or "")
            persona_desc = str(p.get("persona") or "")
        else:
            name = str(getattr(p, "name", "") or getattr(p, "user_name", ""))
            bio = str(getattr(p, "bio", "") or "")
            persona_desc = str(getattr(p, "persona", "") or "")

        name_clean = name.strip()
        if not name_clean:
            continue

        profile_names.append(name_clean)
        combined_text = f"{bio}\n{persona_desc}"
        eps = extract_episodes(combined_text, excluded_keywords=all_candidate_names)
        profile_episodes[name_clean] = eps
        diagnostics["episodes_by_profile"][name_clean] = [e.signature for e in eps]

    # 3. Extraire les épisodes du brief et leur attribution aux personas connus
    brief_all_episodes = extract_episodes(brief_text or "", excluded_keywords=all_candidate_names)
    diagnostics["episodes_in_brief"] = len(brief_all_episodes)

    brief_attributed = _extract_brief_attributed_episodes(
        brief_text or "", sorted(all_candidate_names)
    )

    # Mapper chaque signature d'épisode dans le brief vers son ou ses propriétaires (owners)
    brief_signature_to_owners: Dict[str, Set[str]] = {}
    for owner_name, sigs in brief_attributed.items():
        # Une organisation commerciale n'a pas de biographie personnelle privée
        if org_set and unicodedata.normalize("NFKD", owner_name).lower() in org_set:
            continue
        for sig in sigs:
            brief_signature_to_owners.setdefault(sig, set()).add(owner_name)

    # Montants attribués spécifiquement à un persona dans le brief
    brief_persona_attributed_amounts = {
        sig.split(":")[0] for sig in brief_signature_to_owners.keys()
    }
    # Montants de contexte général du scénario (non attribués à un persona individuel)
    scenario_amounts = {
        ep.signature.split(":")[0] for ep in brief_all_episodes
        if ep.signature.split(":")[0] not in brief_persona_attributed_amounts
    }

    # 4. Analyser la répartition des signatures d'épisodes dans les fiches
    signature_to_carriers: Dict[str, List[str]] = {}
    for p_name, eps in profile_episodes.items():
        for ep in eps:
            signature_to_carriers.setdefault(ep.signature, []).append(p_name)

    seen_contradiction_keys: Set[Tuple[str, Optional[str], str]] = set()

    # Détection AC1 : Épisode partagé entre deux personas distincts
    for sig, carriers in sorted(signature_to_carriers.items()):
        amt_prefix = sig.split(":")[0]
        # Un montant issu du contexte général du scénario (ex: tarif d'offre évalué par la cohorte)
        # est un fait public du scénario qui peut être cité par plusieurs personas sans contradiction.
        if amt_prefix in scenario_amounts:
            continue

        unique_carriers = sorted(set(carriers))
        # Si une organisation partage son offre avec son fondateur ou ses usagers, pas de contradiction
        if org_set:
            human_carriers = [
                c for c in unique_carriers
                if unicodedata.normalize("NFKD", c).lower() not in org_set
            ]
            if len(human_carriers) <= 1:
                continue

        if len(unique_carriers) > 1:
            key = (sig, None, unique_carriers[0])
            seen_contradiction_keys.add(key)
            contradictions.append(
                PersonaContradiction(
                    signature=sig,
                    owner=None,
                    carrier=unique_carriers[0],
                    other_carriers=unique_carriers[1:],
                    reason=(
                        f"Épisode partagé entre plusieurs personas distincts: "
                        f"{', '.join(unique_carriers)}"
                    ),
                )
            )

    # Détection AC2 / AC8 : Épisode attribué dans le brief à un persona et porté par un autre
    for sig, carriers in sorted(signature_to_carriers.items()):
        amt_prefix = sig.split(":")[0]
        if amt_prefix in scenario_amounts:
            continue
        owners = brief_signature_to_owners.get(sig, set())
        for owner in sorted(owners):
            for carrier in sorted(set(carriers)):
                # Normalisation insensible à la casse / accents pour la comparaison des noms
                norm_owner = unicodedata.normalize("NFKD", owner).lower()
                norm_carrier = unicodedata.normalize("NFKD", carrier).lower()
                if norm_owner != norm_carrier:
                    key = (sig, owner, carrier)
                    if key not in seen_contradiction_keys:
                        seen_contradiction_keys.add(key)
                        contradictions.append(
                            PersonaContradiction(
                                signature=sig,
                                owner=owner,
                                carrier=carrier,
                                other_carriers=[],
                                reason=(
                                    f"Épisode attribué par le brief à '{owner}' "
                                    f"mais retrouvé dans la fiche de '{carrier}'"
                                ),
                            )
                        )

    # Tri déterministe strict (AC7) par signature, puis owner (ou ""), puis carrier
    contradictions.sort(
        key=lambda c: (c.signature, c.owner or "", c.carrier)
    )

    is_consistent = len(contradictions) == 0
    return ConsistencyResult(
        is_consistent=is_consistent,
        contradictions=contradictions,
        diagnostics=diagnostics,
    )


@dataclass(frozen=True)
class PracticeDurationAttribute:
    """Attribut biographique d'ancienneté d'exercice ou d'installation professionnelle (Story 015-6, D1)."""

    years: float
    raw_value: str
    context_kind: str  # "current_practice" ou "past_career"
    snippet: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "years": self.years,
            "raw_value": self.raw_value,
            "context_kind": self.context_kind,
            "snippet": self.snippet,
        }


def _build_text_numbers_map() -> Dict[str, int]:
    base_fr = {
        "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
        "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
        "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
        "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19,
    }
    tens_fr = {
        "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
        "soixante": 60, "soixante-dix": 70, "quatre-vingts": 80,
        "quatre-vingt": 80, "quatre-vingt-dix": 90,
    }
    res: Dict[str, int] = dict(base_fr)
    res.update(tens_fr)
    units_fr = {1: "un", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six", 7: "sept", 8: "huit", 9: "neuf"}
    for t_val, t_name in [(20, "vingt"), (30, "trente"), (40, "quarante"), (50, "cinquante"), (60, "soixante")]:
        for u_val, u_name in units_fr.items():
            val = t_val + u_val
            if u_val == 1:
                res[f"{t_name} et {u_name}"] = val
                res[f"{t_name}-et-{u_name}"] = val
                res[f"{t_name} et une"] = val
                res[f"{t_name}-et-une"] = val
            res[f"{t_name}-{u_name}"] = val
            res[f"{t_name} {u_name}"] = val
    for u_val, u_name in [(11, "onze"), (12, "douze"), (13, "treize"), (14, "quatorze"), (15, "quinze"), (16, "seize"), (17, "dix-sept"), (18, "dix-huit"), (19, "dix-neuf")]:
        val = 60 + u_val
        if u_val == 11:
            res[f"soixante et {u_name}"] = val
            res[f"soixante-et-{u_name}"] = val
        res[f"soixante-{u_name}"] = val
        res[f"soixante {u_name}"] = val
    for u_val, u_name in units_fr.items():
        val = 80 + u_val
        res[f"quatre-vingt-{u_name}"] = val
        res[f"quatre-vingt {u_name}"] = val
    for u_val, u_name in [(11, "onze"), (12, "douze"), (13, "treize"), (14, "quatorze"), (15, "quinze"), (16, "seize"), (17, "dix-sept"), (18, "dix-huit"), (19, "dix-neuf")]:
        val = 80 + u_val
        res[f"quatre-vingt-dix-{u_name}"] = val
        res[f"quatre-vingt dix {u_name}"] = val
        res[f"quatre-vingt-{u_name}"] = val
    base_en = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
        "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    }
    res.update(base_en)
    units_en = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
    for t_val, t_name in [(20, "twenty"), (30, "thirty"), (40, "forty"), (50, "fifty"), (60, "sixty"), (70, "seventy"), (80, "eighty"), (90, "ninety")]:
        for u_val, u_name in units_en.items():
            val = t_val + u_val
            res[f"{t_name}-{u_name}"] = val
            res[f"{t_name} {u_name}"] = val
    return res


TEXT_NUMBERS_MAP = _build_text_numbers_map()


def _strip_combining_accents(s: str) -> str:
    """Supprime les diacritiques combinants pour comparaison insensible aux accents."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)
    ).strip().lower()


def _extract_profile_full_text(profile: Dict[str, Any]) -> str:
    """Extrait le texte complet descriptif d'un persona (support Reddit et Twitter)."""
    parts = [
        str(profile.get("persona") or ""),
        str(profile.get("bio") or ""),
        str(profile.get("description") or ""),
        str(profile.get("user_char") or ""),
    ]
    return " ".join(p.strip() for p in parts if p.strip()).strip()


def parse_duration_tokens(num_raw: str, unit_raw: str, has_half: bool) -> Optional[float]:
    """Parse une quantité de durée en années flottantes."""
    num_clean = num_raw.lower().strip()
    val: Optional[float] = None
    m_num = re.search(r"\b(\d+(?:[.,]\d+)?)\b", num_clean)
    if m_num:
        try:
            val = float(m_num.group(1).replace(",", "."))
        except ValueError:
            val = None
    else:
        for word, n in sorted(TEXT_NUMBERS_MAP.items(), key=lambda x: -len(x[0])):
            pattern = r"(?<![\w\-])" + re.escape(word) + r"(?![\w\-])"
            if re.search(pattern, num_clean):
                val = float(n)
                break
    if val is None:
        return None
    if has_half:
        val += 0.5
    u = unit_raw.lower()
    if "mois" in u or "month" in u:
        return round(val / 12.0, 2)
    return float(val)


def extract_practice_durations(text: str) -> List[PracticeDurationAttribute]:
    """Extrait déterministement les durées d'exercice ou d'installation professionnelle (Story 015-6, D1, AC1)."""
    if not text:
        return []

    durations: List[PracticeDurationAttribute] = []

    # 1. Ancienneté d'installation / exercice actuel
    pat_current = re.compile(
        r"(?:\b(?:install[eé]e?s?|exerce|exer[cç]ant|en\s+activit[eé]|en\s+lib[eé]ral|pratique|cabinet\s+ouvert|practicing|installed|in\s+practice|established|operating)\b)"
        r"(?:[^\n,.;:]*?\s+)?"
        r"(?:\b(?:depuis|for)\b)\s+"
        r"(?:un\s+peu\s+plus\s+de\s+|environ\s+|pr[eè]s\s+de\s+|plus\s+de\s+|over\s+|about\s+|nearly\s+)?"
        r"([a-z0-9\s\-]+?)\s*"
        r"\b(ans?|ann[eé]es?|mois|years?|months?)\b"
        r"(?:\s+(?:et\s+demie?|and\s+a\s+half))?",
        re.IGNORECASE,
    )

    for m in pat_current.finditer(text):
        full_match = m.group(0)
        num_raw = m.group(1)
        unit_raw = m.group(2)
        has_half = bool(re.search(r"\b(?:et\s+demie?|and\s+a\s+half)\b", full_match, re.IGNORECASE))
        years = parse_duration_tokens(num_raw, unit_raw, has_half)
        if years is not None:
            durations.append(
                PracticeDurationAttribute(
                    years=years,
                    raw_value=full_match.strip(),
                    context_kind="current_practice",
                    snippet=full_match.strip(),
                )
            )

    # 2. Carrière antérieure révolue ou durée passée
    # Exclut les expressions d'installation actuelle (depuis / installed / practicing) pour ne pas doubler en past_career
    pat_past = re.compile(
        r"(?:\b(?:pendant|during|durant)\s+(?:environ\s+|pr[eè]s\s+de\s+|plus\s+de\s+|over\s+|about\s+)?([a-z0-9\s\-]+?)\s*\b(ans?|ann[eé]es?|mois|years?|months?)\b(?:\s+(?:et\s+demie?|and\s+a\s+half))?"
        r"|(?<!\bpracticing\s)(?<!\binstalled\s)\bfor\s+(?:over\s+|about\s+|nearly\s+)?([a-z0-9\s\-]+?)\s*\b(years?|months?)\b(?:\s+and\s+a\s+half)?"
        r"|\b([a-z0-9\s\-]+?)\s*\b(ans?|ann[eé]es?|mois|years?|months?)\b\s+comme\b"
        r"|formation\s+de\s+([a-z0-9\s\-]+?)\s*\b(ans?|ann[eé]es?|mois|years?|months?)\b)",
        re.IGNORECASE,
    )
    for m in pat_past.finditer(text):
        full_match = m.group(0)
        num_raw = m.group(1) or m.group(3) or m.group(5) or m.group(7)
        unit_raw = m.group(2) or m.group(4) or m.group(6) or m.group(8)
        if not num_raw or not unit_raw:
            continue
        has_half = bool(re.search(r"\b(?:et\s+demie?|and\s+a\s+half)\b", full_match, re.IGNORECASE))
        years = parse_duration_tokens(num_raw, unit_raw, has_half)
        if years is not None:
            durations.append(
                PracticeDurationAttribute(
                    years=years,
                    raw_value=full_match.strip(),
                    context_kind="past_career",
                    snippet=full_match.strip(),
                )
            )

    return durations


def extract_all_biographical_durations(text: str) -> List[float]:
    """Extrait l'ensemble des valeurs numériques de durée en années (actuelle, passée, formation) d'un texte."""
    if not text:
        return []
    attrs = extract_practice_durations(text)
    return [a.years for a in attrs]


def check_claim_persona_biography(
    claim_text: str,
    agent_name: str,
    profiles_by_name: Dict[str, Dict[str, Any]],
    all_profile_episodes: Optional[Dict[str, List[BiographicalEpisode]]] = None,
) -> Tuple[bool, str]:
    """Vérifie si une affirmation unitaire contredit factuellement la biographie de son persona (Story 015-6, D2, AC2, AC3).

    Retourne:
      (is_contradicted, reason)
    """
    if not claim_text or not agent_name or not profiles_by_name:
        return False, ""

    # Pré-calcul automatique d'all_profile_episodes si omis (Patch 1 BMAD)
    if all_profile_episodes is None and profiles_by_name:
        all_profile_episodes = {}
        for p_name, p_data in profiles_by_name.items():
            p_text = _extract_profile_full_text(p_data)
            all_profile_episodes[p_name] = extract_episodes(p_text, excluded_keywords={p_name.lower()})

    norm_name = _strip_combining_accents(agent_name)
    profile = None
    canonical_name = agent_name
    for p_name, p_data in profiles_by_name.items():
        if _strip_combining_accents(p_name) == norm_name:
            profile = p_data
            canonical_name = p_name
            break

    if not profile:
        return False, ""

    profile_text = _extract_profile_full_text(profile)
    profile_durations = extract_practice_durations(profile_text)
    profile_current = [d for d in profile_durations if d.context_kind == "current_practice"]
    all_profile_duration_values = extract_all_biographical_durations(profile_text)

    # 1. Vérification de l'ancienneté d'installation affirmée dans le claim
    claim_durations = extract_practice_durations(claim_text)
    claim_current = [d for d in claim_durations if d.context_kind == "current_practice"]

    if profile_current and claim_current:
        # Le profil canonique a une ou plusieurs durées d'installation courantes de référence
        for c_dur in claim_current:
            matches_current = False
            for p_dur in profile_current:
                allowed_rel = max(1.0, 0.35 * p_dur.years)
                if abs(c_dur.years - p_dur.years) <= allowed_rel:
                    matches_current = True
                    break
            if not matches_current:
                # Vérifier si c_dur.years correspond à une carrière passée légitime du persona (ex: 22 ans)
                if any(abs(c_dur.years - val) <= 0.5 for val in all_profile_duration_values):
                    continue
                reason = (
                    f"PERSONA_BIOGRAPHY_CONTRADICTION : L'affirmation attribue à '{canonical_name}' "
                    f"une ancienneté d'installation de {c_dur.years:g} ans ('{c_dur.raw_value}') "
                    f"en contradiction avec sa fiche canonique ({profile_current[0].years:g} ans, '{profile_current[0].raw_value}')."
                )
                return True, reason

    # 2. Vérification d'attribution croisée d'un épisode monétaire personnel exclusif
    # On exclut le nom du persona lui-même pour ne pas polluer l'épisode (ex: "1500eur:nom_persona")
    persona_names_to_exclude = {canonical_name.lower(), agent_name.lower()}
    for pn in profiles_by_name.keys():
        persona_names_to_exclude.add(pn.lower())
    claim_episodes = extract_episodes(claim_text, excluded_keywords=persona_names_to_exclude)
    if claim_episodes and all_profile_episodes:
        # Vérifier si un épisode du claim appartient exclusivement à un AUTRE profil
        my_eps = {e.signature for e in all_profile_episodes.get(canonical_name, [])}
        for ep in claim_episodes:
            if ep.signature not in my_eps:
                # Regarder si un autre profil le possède exclusivement
                carriers = [
                    other_name
                    for other_name, other_eps in all_profile_episodes.items()
                    if other_name != canonical_name and any(oe.signature == ep.signature for oe in other_eps)
                ]
                # Un épisode personnel est exclusif s'il n'appartient qu'à un seul autre persona
                # S'il appartient à plusieurs profils (offres publiques partagées, tarifs communs), il n'est pas exclusif
                if len(carriers) == 1:
                    reason = (
                        f"PERSONA_BIOGRAPHY_CONTRADICTION : L'affirmation attribue à '{canonical_name}' "
                        f"l'épisode monétaire personnel '{ep.raw_amount}' ({ep.signature}) "
                        f"qui appartient à la fiche de '{carriers[0]}'."
                    )
                    return True, reason

    return False, ""


def audit_prose_persona_consistency(
    markdown_content: str,
    profiles: List[Dict[str, Any]],
    allowed_names: Optional[Set[str]] = None,
) -> ConsistencyResult:
    """Audite la cohérence biographique de la prose finale d'un rapport contre les fiches personas (Story 015-6, D2, AC2)."""
    if not markdown_content or not profiles:
        return ConsistencyResult(is_consistent=True, contradictions=[], diagnostics={})

    profiles_by_name: Dict[str, Dict[str, Any]] = {}
    for p in profiles:
        name = p.get("name") or p.get("realname") or p.get("username")
        if name:
            profiles_by_name[name] = p

    # Filtrer si allowed_names est fourni
    if allowed_names:
        norm_allowed = {_strip_combining_accents(n) for n in allowed_names if n}
        profiles_by_name = {
            k: v for k, v in profiles_by_name.items()
            if _strip_combining_accents(k) in norm_allowed
        }

    # Pré-calcul des épisodes monétaires de tous les profils
    all_profile_episodes: Dict[str, List[BiographicalEpisode]] = {}
    practice_durations_by_profile: Dict[str, List[Dict[str, Any]]] = {}

    for name, p in profiles_by_name.items():
        text = _extract_profile_full_text(p)
        all_profile_episodes[name] = extract_episodes(text, excluded_keywords={name.lower()})
        durs = extract_practice_durations(text)
        practice_durations_by_profile[name] = [d.to_dict() for d in durs]

    contradictions: List[PersonaContradiction] = []
    seen_keys: Set[Tuple[str, str]] = set()

    # Découpage du markdown en segments de paragraphe puis en phrases
    paragraphs = re.split(r"\n\s*\n", markdown_content)
    for para in paragraphs:
        flat_para = re.sub(r"\s*\n\s*", " ", para).strip()
        if not flat_para:
            continue
        sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(flat_para) if s.strip()]
        for sentence in sentences:
            # Identifier si la phrase mentionne un persona admis
            for name, p in profiles_by_name.items():
                pattern_name = _make_name_regex(name)
                if re.search(pattern_name, sentence, re.IGNORECASE):
                    is_contra, reason = check_claim_persona_biography(
                        claim_text=sentence,
                        agent_name=name,
                        profiles_by_name=profiles_by_name,
                        all_profile_episodes=all_profile_episodes,
                    )
                    if is_contra:
                        key = (name, reason)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            contradictions.append(
                                PersonaContradiction(
                                    signature="persona_biography_contradiction",
                                    owner=name,
                                    carrier=name,
                                    other_carriers=[],
                                    reason=reason,
                                )
                            )

    is_consistent = len(contradictions) == 0
    return ConsistencyResult(
        is_consistent=is_consistent,
        contradictions=contradictions,
        diagnostics={
            "practice_durations_by_profile": practice_durations_by_profile,
            "profiles_audited": len(profiles_by_name),
        },
    )

    is_consistent = len(contradictions) == 0
    return ConsistencyResult(
        is_consistent=is_consistent,
        contradictions=contradictions,
        diagnostics={
            "practice_durations_by_profile": practice_durations_by_profile,
            "profiles_audited": len(profiles_by_name),
        },
    )


def _make_name_regex(name: str) -> str:
    """Construit un motif regex tolérant aux variantes d'accents fréquentes (ex: Emilie / Émilie)."""
    norm_nfc = unicodedata.normalize("NFC", name)
    parts = []
    for c in norm_nfc:
        base = "".join(
            ch for ch in unicodedata.normalize("NFD", c) if not unicodedata.combining(ch)
        )
        if base.isalpha():
            b_low = base.lower()
            if b_low == "e":
                parts.append(r"[eéèêë]")
            elif b_low == "a":
                parts.append(r"[aàáâãäå]")
            elif b_low == "i":
                parts.append(r"[iìíîï]")
            elif b_low == "o":
                parts.append(r"[oòóôõö]")
            elif b_low == "u":
                parts.append(r"[uùúûü]")
            elif b_low == "c":
                parts.append(r"[cç]")
            else:
                parts.append(re.escape(b_low))
        else:
            parts.append(re.escape(c))
    return r"\b" + "".join(parts) + r"\b"


def filter_non_admitted_personas_from_text(
    text: str,
    admitted_names: List[str],
    excluded_names: List[str],
    redaction_token: str = "[persona non admis]",
) -> str:
    """Filtre le texte du contexte de rédaction pour en exclure les personas non admis (AC5).

    Règles :
    1. Un persona admis (eligible) n'est JAMAIS retiré.
    2. Les phrases contenant un persona exclu (review ou ineligible) et attribuant une
       action ou posture sont retirées du texte ; à défaut de suppression de phrase,
       le nom est remplacé par `redaction_token`.
    3. Si une phrase contient à la fois un persona admis et un persona exclu,
       le nom exclu est remplacé par le jeton pour préserver l'information concernant l'admis.
    4. Toutes les occurrences du persona exclu sont traitées (gouvernance exhaustive).
    """
    if not text or not excluded_names:
        return text or ""

    # Normalisation préalable en NFC pour neutraliser les décompositions Unicode NFD
    text_nfc = unicodedata.normalize("NFC", text)

    # Nettoyage et déduplication des listes de noms en NFC
    admitted_clean = {
        unicodedata.normalize("NFC", name.strip())
        for name in admitted_names if name and name.strip()
    }
    excluded_clean = {
        unicodedata.normalize("NFC", name.strip())
        for name in excluded_names if name and name.strip()
    }

    # Sécurité : aucun admis ne doit être compté parmi les exclus
    excluded_effective = [
        name for name in excluded_clean if name not in admitted_clean
    ]
    if not excluded_effective:
        return text_nfc

    admitted_patterns = [_make_name_regex(adm) for adm in admitted_clean]
    excluded_patterns = [(exc, _make_name_regex(exc)) for exc in excluded_effective]

    # Découpage par paragraphes pour préserver la structure markdown
    paragraphs = text_nfc.split("\n\n")
    cleaned_paragraphs: List[str] = []

    for para in paragraphs:
        if not para.strip():
            cleaned_paragraphs.append(para)
            continue

        # Découpage en phrases dans le paragraphe
        # On découpe en préservant la ponctuation
        raw_sentences = re.split(r"(?<=[.!?\n])\s+", para)
        kept_sentences: List[str] = []

        for sentence in raw_sentences:
            s = sentence.strip()
            if not s:
                continue

            # Vérifier quels personas sont présents dans la phrase
            has_admitted = any(
                re.search(adm_pat, s, re.IGNORECASE)
                for adm_pat in admitted_patterns
            )
            found_excluded_patterns = [
                (exc, exc_pat) for exc, exc_pat in excluded_patterns
                if re.search(exc_pat, s, re.IGNORECASE)
            ]

            if not found_excluded_patterns:
                # Phrase intacte
                kept_sentences.append(sentence)
            elif has_admitted:
                # Phrase partagée : on ne supprime pas la phrase, on caviarde le non-admis
                redacted_sentence = sentence
                for _exc, exc_pat in found_excluded_patterns:
                    redacted_sentence = re.sub(
                        exc_pat,
                        redaction_token,
                        redacted_sentence,
                        flags=re.IGNORECASE,
                    )
                kept_sentences.append(redacted_sentence)
            else:
                # Phrase ne nommant que le(s) exclu(s) : on supprime la phrase
                # Si la suppression de la phrase vide entièrement une ligne importante (ex: élément de liste),
                # on remplace par le jeton pour préserver la validité structurelle
                if s.startswith("- ") or s.startswith("* ") or re.match(r"^\d+\.", s):
                    redacted_sentence = sentence
                    for _exc, exc_pat in found_excluded_patterns:
                        redacted_sentence = re.sub(
                            exc_pat,
                            redaction_token,
                            redacted_sentence,
                            flags=re.IGNORECASE,
                        )
                    kept_sentences.append(redacted_sentence)
                else:
                    # Retrait pur et simple de la phrase
                    continue

        if kept_sentences:
            # Préserver le saut de ligne si le paragraphe source était une liste multi-lignes
            separator = "\n" if "\n" in para else " "
            cleaned_paragraphs.append(separator.join(kept_sentences))
        else:
            # Si le paragraphe entier est vidé, on ne l'injecte pas
            pass

    return "\n\n".join(cleaned_paragraphs)
