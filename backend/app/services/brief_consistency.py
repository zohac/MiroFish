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
        # Une organisation (Keova, Stripe...) n'a pas de biographie personnelle privée
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
