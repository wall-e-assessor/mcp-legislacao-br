"""Trechos reais do HTML do Planalto (lidos em 04/11/2026), entregues em windows-1252."""

from pathlib import Path

import pytest

from mcp_legislacao_br.parser import extrai_artigo, html_para_blocos
from mcp_legislacao_br.rede import Resposta

FIX = Path(__file__).parent / "fixtures"


def _blocos(nome):
    raw = (FIX / nome).read_text("utf-8").encode("windows-1252")  # sem meta charset, como no portal
    return html_para_blocos(Resposta("x", raw, "text/html", "2026-11-04T00:00:00+00:00", "ao vivo").texto())


@pytest.fixture(scope="module")
def l9099():
    return _blocos("planalto_l9099_trecho.html")


@pytest.fixture(scope="module")
def cpc():
    return _blocos("planalto_cpc_trecho.html")


def test_l9099_art8_redacao_vigente(l9099):
    a = extrai_artigo(l9099, "8")
    linhas = a.vigente.split("\n")
    assert linhas[0].startswith("Art. 8º Não poderão ser partes")
    assert linhas[1] == "§ 1o Somente serão admitidas a propor ação perante o Juizado Especial: (Redação dada pela Lei nº 12.126, de 2009)"
    assert "II - as microempresas, assim definidas" not in a.vigente
    assert linhas[3].startswith("II - as pessoas enquadradas como microempreendedores individuais")
    assert linhas[-1].startswith("§ 2º O maior de dezoito anos")
    assert len(linhas) == 7
    assert "[[REVOGADO: II - as microempresas, assim definidas pela Lei no 9.841" in a.completo


def test_l9099_art9_paragrafo_4_substituido(l9099):
    a = extrai_artigo(l9099, "9")
    assert "§ 4o O réu, sendo pessoa jurídica ou titular de firma individual, poderá ser representado por preposto credenciado, munido de carta de preposição" in a.vigente
    assert a.vigente.count("§ 4") == 1


def test_l9099_artigo_antes_de_secao(l9099):
    a = extrai_artigo(l9099, "11")
    assert a.vigente == "Art. 11. O Ministério Público intervirá nos casos previstos em lei."


@pytest.mark.parametrize("art,esperado", [
    ("48", "Art. 48. Caberão embargos de declaração contra sentença ou acórdão nos casos previstos no Código de Processo Civil. (Redação dada pela Lei nº 13.105, de 2015) (Vigência)\nParágrafo único. Os erros materiais podem ser corrigidos de ofício."),
    ("50", "Art. 50. Os embargos de declaração interrompem o prazo para a interposição de recurso. (Redação dada pela Lei nº 13.105, de 2015) (Vigência)"),
    ("12-A", "Art. 12-A. Na contagem de prazo em dias, estabelecido por lei ou pelo juiz, para a prática de qualquer ato processual, inclusive para a interposição de recursos, computar-se-ão somente os dias úteis. (Incluído pela Lei nº 13.728, de 2018)"),
])
def test_l9099_caput_antigo_tachado(l9099, art, esperado):
    a = extrai_artigo(l9099, art)
    assert a.vigente == esperado
    assert not a.revogado_integralmente


def test_cpc_art319(cpc):
    a = extrai_artigo(cpc, "319")
    linhas = a.vigente.split("\n")
    assert linhas[0] == "Art. 319. A petição inicial indicará:"
    assert linhas[7] == "VII - a opção do autor pela realização ou não de audiência de conciliação ou de mediação."
    assert linhas[-1].startswith("§ 3º A petição inicial não será indeferida pelo não atendimento")
    assert len(linhas) == 11
    assert "Art. 320" not in a.vigente


def test_cpc_art1015_milhar_e_link_no_meio(cpc):
    a = extrai_artigo(cpc, "1.015")
    assert a.vigente.split("\n")[0] == "Art. 1.015. Cabe agravo de instrumento contra as decisões interlocutórias que versarem sobre:"
    assert "XI - redistribuição do ônus da prova nos termos do art. 373, § 1º;" in a.vigente
    assert a.vigente.endswith("no processo de execução e no processo de inventário.")
    assert "Art. 1.016" not in a.vigente
