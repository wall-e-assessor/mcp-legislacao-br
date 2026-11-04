"""Compilação real da Câmara (normas.leg.br) contra o Planalto, mesmos artigos da Lei 9.099/1995."""

from pathlib import Path

import pytest

from mcp_legislacao_br.parser import extrai_artigo, html_para_blocos, normaliza_comparacao
from mcp_legislacao_br.rede import Resposta

FIX = Path(__file__).parent / "fixtures"


def _blocos(nome, encoding):
    raw = (FIX / nome).read_text("utf-8").encode(encoding)
    return html_para_blocos(Resposta("x", raw, "text/html", "2026-11-04T00:00:00+00:00", "ao vivo").texto())


@pytest.fixture(scope="module")
def planalto():
    return _blocos("planalto_l9099_trecho.html", "windows-1252")


@pytest.fixture(scope="module")
def camara():
    return _blocos("camara_l9099_trecho.html", "utf-8")


def test_camara_le_notas_proprias(camara):
    a = extrai_artigo(camara, "8")
    assert "§ 1º Somente serão admitidas a propor ação perante o Juizado Especial: (Parágrafo com redação dada pela Lei nº 12.126, de 16/12/2009)" in a.vigente
    assert "(Inciso acrescido pela Lei nº 12.126, de 16/12/2009, e com nova redação dada pela Lei Complementar nº 147, de 7/8/2014)" in a.vigente


@pytest.mark.parametrize("art", ["8", "9", "10", "11", "12", "12-A", "48", "49", "50"])
def test_redacoes_coincidem(planalto, camara, art):
    p, c = extrai_artigo(planalto, art), extrai_artigo(camara, art)
    assert normaliza_comparacao(p.vigente) == normaliza_comparacao(c.vigente)


def test_divergencia_real_continua_detectada(planalto, camara):
    p = extrai_artigo(planalto, "50").vigente
    c = extrai_artigo(camara, "50").vigente.replace("interrompem", "suspendem")
    assert normaliza_comparacao(p) != normaliza_comparacao(c)


def test_redacao_antiga_do_planalto_nao_vale_como_vigente(planalto, camara):
    antigo = extrai_artigo(planalto, "50").completo.split("]]")[0]
    assert "suspenderão o prazo" in antigo
    assert normaliza_comparacao(antigo) != normaliza_comparacao(extrai_artigo(camara, "50").vigente)


def test_vetado_permanece():
    assert normaliza_comparacao("XII - (VETADO);") == "xii vetado"
