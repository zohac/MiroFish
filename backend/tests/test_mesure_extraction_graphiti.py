"""Tests unitaires hermétiques du banc de mesure de l'extraction Graphiti (Story 001-5).

Ces tests vérifient le fonctionnement autonome, le calcul des métriques C1 à C5,
le découpage du document d'épreuve et la génération du rapport sans dépendance
à un conteneur Neo4j externe ni à l'endpoint OpenCode Go.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.mesurer_extraction_graphiti import (
    DEFAULT_EXPECTED_SHA256,
    ChunkResultat,
    DonneesMesure,
    LocalPassthroughCrossEncoder,
    MockGraphDriver,
    _extraire_valeur_compteur,
    assainir_message_erreur,
    calculer_criteres,
    charger_et_decouper_document,
    creer_mock_graphiti,
    executer_mesure_extraction,
    generer_rapport_markdown,
    reinitialiser_graphe_neo4j,
    verifier_sha256,
)


def test_verifier_sha256(tmp_path: Path):
    """Vérifie le calcul et la validation de l'empreinte SHA256."""
    test_file = tmp_path / "test_doc.txt"
    contenu = b"Document de test parlementaire MiroFish"
    test_file.write_bytes(contenu)
    vrai_sha = hashlib.sha256(contenu).hexdigest()

    valide, calcul = verifier_sha256(test_file, vrai_sha)
    assert valide is True
    assert calcul == vrai_sha

    valide_faux, _ = verifier_sha256(test_file, "0000000000000000000000000000000000000000000000000000000000000000")
    assert valide_faux is False

    with pytest.raises(FileNotFoundError):
        verifier_sha256(tmp_path / "inexistant.pdf", vrai_sha)


def test_charger_et_decouper_document(tmp_path: Path):
    """Vérifie le découpage du texte en chunks de taille configurée."""
    test_txt = tmp_path / "doc.txt"
    texte = "Phrase un. " * 30 + "Phrase deux. " * 30
    test_txt.write_text(texte, encoding="utf-8")

    texte_lu, chunks = charger_et_decouper_document(test_txt, chunk_size=200, overlap=20)
    assert texte_lu == texte
    assert len(chunks) > 1
    assert all(len(c) <= 250 for c in chunks)


def test_calculer_criteres_nominal():
    """Vérifie l'évaluation des critères C1 à C5 dans un cas nominal conforme."""
    resultats: List[ChunkResultat] = []
    for i in range(1, 31):
        resultats.append(
            ChunkResultat(
                index=i,
                taille_caracteres=400,
                nb_mots=50,
                apercu_texte="Texte...",
                succes=True,
                duree_sec=0.5,
                nb_noeuds=2,
                nb_aretes=1,
                nb_valid_at=1 if i % 2 == 0 else 0,
                missing_session_id=False,
            )
        )

    res = calculer_criteres(resultats, nb_nodes_neo4j=60, nb_edges_neo4j=30, nb_edges_valid_at_neo4j=15)
    assert res["c1_valide"] is True
    assert res["c1_succes_count"] == 30
    assert res["c1_taux_succes"] == 1.0
    assert res["c2_valide"] is True
    assert res["c2_missing_session_count"] == 0
    assert res["c3_valide"] is True
    assert res["c4_valide"] is True
    assert res["c4_nb_aretes_valid_at"] == 15
    assert res["c5_valide"] is True
    assert res["verdict_global_go"] is True


def test_calculer_criteres_seuil_limite_c1():
    """Vérifie le seuil limite C1 à exactement 27/30 (90%)."""
    resultats: List[ChunkResultat] = []
    for i in range(1, 31):
        # 27 succès, 3 échecs
        succes = i <= 27
        resultats.append(
            ChunkResultat(
                index=i,
                taille_caracteres=400,
                nb_mots=50,
                apercu_texte="Texte...",
                succes=succes,
                duree_sec=0.5,
                missing_session_id=False,
            )
        )

    res = calculer_criteres(resultats, nb_nodes_neo4j=54, nb_edges_neo4j=27, nb_edges_valid_at_neo4j=10)
    assert res["c1_succes_count"] == 27
    assert res["c1_valide"] is True
    assert res["c4_nb_aretes_valid_at"] == 10
    assert res["verdict_global_go"] is True

    # 26 succès (en dessous de 90%) -> no-go
    resultats[26].succes = False
    res_echec = calculer_criteres(resultats, nb_nodes_neo4j=52, nb_edges_neo4j=26, nb_edges_valid_at_neo4j=10)
    assert res_echec["c1_succes_count"] == 26
    assert res_echec["c1_valide"] is False
    assert res_echec["verdict_global_go"] is False


def test_calculer_criteres_violation_c2_missing_session():
    """Vérifie qu'un échec MissingSessionID entraîne immédiatement un NO-GO (C2)."""
    resultats = [
        ChunkResultat(
            index=1,
            taille_caracteres=400,
            nb_mots=50,
            apercu_texte="Texte...",
            succes=False,
            duree_sec=0.1,
            missing_session_id=True,
            type_erreur="MissingSessionIDError",
            message_erreur="HTTP 400: MissingSessionID",
        )
    ]
    res = calculer_criteres(resultats, nb_nodes_neo4j=0, nb_edges_neo4j=0, nb_edges_valid_at_neo4j=0)
    assert res["c2_valide"] is False
    assert res["c2_missing_session_count"] == 1
    assert res["verdict_global_go"] is False


def test_calculer_criteres_violation_c3_graphe_vide():
    """Vérifie qu'un graphe vide sans entités ou relations échoue C3."""
    resultats = [
        ChunkResultat(
            index=1,
            taille_caracteres=400,
            nb_mots=50,
            apercu_texte="Texte...",
            succes=True,
            duree_sec=0.5,
            missing_session_id=False,
        )
    ]
    # 0 nœuds, 0 relations
    res = calculer_criteres(resultats, nb_nodes_neo4j=0, nb_edges_neo4j=0, nb_edges_valid_at_neo4j=0)
    assert res["c3_valide"] is False
    assert res["verdict_global_go"] is False


@pytest.mark.asyncio
async def test_local_passthrough_cross_encoder():
    """Vérifie que le cross-encoder local classe les passages sans appel externe."""
    encoder = LocalPassthroughCrossEncoder()
    passages = ["Passage 1", "Passage 2", "Passage 3"]
    ranked = await encoder.rank("requete test", passages)
    assert len(ranked) == 3
    assert [p for p, _ in ranked] == passages
    assert ranked[0][1] > ranked[1][1] > ranked[2][1]


@pytest.mark.asyncio
async def test_mock_graph_driver_cypher():
    """Vérifie le comportement de MockGraphDriver sur les requêtes Cypher attendues."""
    driver = MockGraphDriver()
    driver.nodes["uuid1"] = {"name": "TestNode1"}
    driver.nodes["uuid2"] = {"name": "TestNode2"}
    driver.edges.append({"name": "REL", "valid_at": "2026-10-06"})
    driver.edges.append({"name": "REL2", "valid_at": None})

    res_nodes = await driver.execute_query("MATCH (n) RETURN count(n) AS cnt")
    assert res_nodes[0]["cnt"] == 2

    res_edges = await driver.execute_query("MATCH ()-[r]->() RETURN count(r) AS cnt")
    assert res_edges[0]["cnt"] == 2

    res_valid = await driver.execute_query("MATCH ()-[r]->() WHERE r.valid_at IS NOT NULL RETURN count(r) AS cnt")
    assert res_valid[0]["cnt"] == 1

    await driver.execute_query("MATCH (n) DETACH DELETE n")
    assert len(driver.nodes) == 0
    assert len(driver.edges) == 0


@pytest.mark.asyncio
async def test_reinitialiser_graphe_neo4j_sans_call_db_indexes():
    """Vérifie que la remise à zéro n'invoque pas delete_all_indexes / CALL db.indexes()."""
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=[])
    mock_driver.build_indices_and_constraints = AsyncMock()
    mock_driver.delete_all_indexes = AsyncMock()

    await reinitialiser_graphe_neo4j(mock_driver)

    mock_driver.execute_query.assert_awaited_once_with("MATCH (n) DETACH DELETE n")
    mock_driver.build_indices_and_constraints.assert_awaited_once_with(delete_existing=False)
    mock_driver.delete_all_indexes.assert_not_called()


def test_generer_rapport_markdown():
    """Vérifie le formatage du rapport Markdown, en particulier le verdict en tête (NFR-4)."""
    res = [
        ChunkResultat(
            index=1,
            taille_caracteres=350,
            nb_mots=45,
            apercu_texte="Extrait du rapport...",
            succes=True,
            duree_sec=0.42,
            nb_noeuds=2,
            nb_aretes=1,
            nb_valid_at=1,
            noms_entites=["Commission", "Transition"],
            faits_relations=["Commission pilote Transition"],
        )
    ]
    donnees = DonneesMesure(
        date_mesure="2026-10-06 15:00:00 UTC",
        mode_mock=True,
        pdf_path="uploads/documents/test.pdf",
        pdf_sha256="4281a931545537f56625c3f4d0907fc66f54be82fef5d7b10e655dcdaf72ce88",
        sha256_valide=True,
        nb_total_chunks_document=562,
        chunks_testes=1,
        chunk_size=500,
        overlap=50,
        model_llm="space-bunny-free",
        endpoint_llm="https://opencode.ai/zen/go/v1",
        model_embedder="all-MiniLM-L6-v2",
        dims_embedder=384,
        duree_totale_sec=0.42,
        resultats_chunks=res,
        c1_succes_count=1,
        c1_total_count=1,
        c1_taux_succes=1.0,
        c1_valide=True,
        c2_missing_session_count=0,
        c2_valide=True,
        c3_nb_noeuds_neo4j=2,
        c3_nb_relations_neo4j=1,
        c3_valide=True,
        c4_nb_aretes_valid_at=1,
        c4_valide=True,
        c5_rapport_genere=True,
        verdict_global_go=True,
    )

    markdown = generer_rapport_markdown(donnees)
    assert "# Rapport de mesure — Épreuve Graphiti local" in markdown
    assert "Verdict global" in markdown
    assert "GO — EXTRACTION VALIDÉE" in markdown
    assert "## 1. Synthèse des critères de sortie" in markdown
    assert "## 2. Configuration du banc d'essai" in markdown
    assert "## 3. Résultats détaillés par chunk" in markdown
    assert "Commission" in markdown


@pytest.mark.asyncio
async def test_executer_mesure_extraction_mock_complet(tmp_path: Path):
    """Vérifie l'exécution complète du banc de mesure en mode mock."""
    test_pdf = tmp_path / "rapport.txt"
    test_pdf.write_text("Introduction du rapport parlementaire n° 2506 sur la transition énergétique. " * 20, encoding="utf-8")
    rapport_dest = tmp_path / "rapport_test.md"
    sha = hashlib.sha256(test_pdf.read_bytes()).hexdigest()

    donnees, contenu_md = await executer_mesure_extraction(
        mock=True,
        limit=5,
        chunks_start=0,
        chunk_size=200,
        overlap=20,
        pdf_path_str=str(test_pdf),
        expected_sha256=sha,
        output_report_str=str(rapport_dest),
        skip_reset=False,
        delay_between_chunks=0.0,
    )

    assert donnees.verdict_global_go is True
    assert donnees.chunks_testes == 5
    assert donnees.c1_succes_count == 5
    assert donnees.c2_missing_session_count == 0
    assert donnees.c4_nb_aretes_valid_at == 2
    assert donnees.c4_valide is True
    assert rapport_dest.exists()
    assert "GO — EXTRACTION VALIDÉE" in contenu_md


def test_calculer_criteres_fallback_memoire_valid_at():
    """Vérifie que C4 utilise la somme des chunks lorsque Neo4j renvoie 0 arêtes valid_at."""
    resultats = [
        ChunkResultat(
            index=1,
            taille_caracteres=300,
            nb_mots=40,
            apercu_texte="Texte...",
            succes=True,
            duree_sec=0.2,
            nb_valid_at=3,
        )
    ]
    res = calculer_criteres(resultats, nb_nodes_neo4j=2, nb_edges_neo4j=1, nb_edges_valid_at_neo4j=0)
    assert res["c4_nb_aretes_valid_at"] == 3
    assert res["c4_valide"] is True


def test_extraire_valeur_compteur_robustesse():
    """Vérifie la robustesse de l'extraction de compteurs Cypher face à des valeurs None ou vides."""
    assert _extraire_valeur_compteur(None) == 0
    assert _extraire_valeur_compteur([]) == 0
    assert _extraire_valeur_compteur([[]]) == 0
    assert _extraire_valeur_compteur([{"cnt": None}]) == 0
    assert _extraire_valeur_compteur([{"cnt": 42}]) == 42
    assert _extraire_valeur_compteur([(12,)]) == 12
    assert _extraire_valeur_compteur([(None,)]) == 0


def test_assainir_message_erreur():
    """Vérifie le caviardage des secrets et clés d'API dans les messages d'erreurs (NFR-2)."""
    assert assainir_message_erreur(None) is None
    msg_bearer = "Erreur HTTP 401: Bearer eyJhbGciOiJIUzI1NiJ9.invalid"
    assert "Bearer [MASQUÉ]" in assainir_message_erreur(msg_bearer)
    msg_key = "Clé invalide api_key=sk-1234567890abcdef"
    assert "api_key=[MASQUÉ]" in assainir_message_erreur(msg_key)
    msg_pwd = "Auth failed for password=my_secret_pass"
    assert "password=[MASQUÉ]" in assainir_message_erreur(msg_pwd)


@pytest.mark.asyncio
async def test_executer_mesure_extraction_sha256_invalide(tmp_path: Path):
    """Vérifie qu'un SHA256 non conforme interrompt immédiatement l'épreuve avec ValueError."""
    test_pdf = tmp_path / "faux_rapport.txt"
    test_pdf.write_text("Contenu corrompu", encoding="utf-8")

    with pytest.raises(ValueError, match="Empreinte SHA256 du document d'épreuve non conforme"):
        await executer_mesure_extraction(
            mock=True,
            pdf_path_str=str(test_pdf),
            expected_sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )


@pytest.mark.asyncio
async def test_executer_mesure_extraction_parametres_invalides(tmp_path: Path):
    """Vérifie le rejet des paramètres CLI invalides (chunk_size <= overlap ou limit <= 0)."""
    test_pdf = tmp_path / "doc.txt"
    test_pdf.write_text("Texte test", encoding="utf-8")
    sha = hashlib.sha256(test_pdf.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="chunk_size .* doit être strictement supérieur à overlap"):
        await executer_mesure_extraction(
            mock=True,
            chunk_size=50,
            overlap=50,
            pdf_path_str=str(test_pdf),
            expected_sha256=sha,
        )

    with pytest.raises(ValueError, match="limit .* doit être un entier strictement positif"):
        await executer_mesure_extraction(
            mock=True,
            limit=0,
            pdf_path_str=str(test_pdf),
            expected_sha256=sha,
        )


@pytest.mark.asyncio
async def test_executer_mesure_extraction_sans_password_reel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Vérifie qu'en mode réel sans mock, l'absence de NEO4J_PASSWORD lève une exception explicite."""
    test_pdf = tmp_path / "doc.txt"
    test_pdf.write_text("Texte test", encoding="utf-8")
    sha = hashlib.sha256(test_pdf.read_bytes()).hexdigest()

    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.setattr("app.config.Config.NEO4J_PASSWORD", None, raising=False)

    with pytest.raises(ValueError, match="NEO4J_PASSWORD est requise pour l'exécution réelle"):
        await executer_mesure_extraction(
            mock=False,
            pdf_path_str=str(test_pdf),
            expected_sha256=sha,
        )
