from pathlib import Path

import pytest

from mcp_legislacao_br.fontes import candidatos_planalto, filtra_dispositivos, normaliza_tipo
from mcp_legislacao_br.parser import extrai_artigo, html_para_blocos, normaliza_artigo, normaliza_comparacao
from mcp_legislacao_br.rede import detecta_charset

FIX = Path(__file__).parent / "fixtures" / "planalto_amostra.htm"


@pytest.fixture(scope="module")
def blocos():
    return html_para_blocos(FIX.read_bytes())


def test_charset_windows_1252():
    assert detecta_charset(FIX.read_bytes()) == "windows-1252"


def test_acentos_decodificados(blocos):
    assert any("Juízes leigos" in b.vigente for b in blocos)


@pytest.mark.parametrize("entrada,saida", [("319", "319"), ("1.015", "1015"), ("art. 12-a", "12-A"), ("5º", "5"), (8, "8"), ("Art. 3o", "3")])
def test_normaliza_artigo(entrada, saida):
    assert normaliza_artigo(entrada) == saida


def test_normaliza_artigo_invalido():
    with pytest.raises(ValueError):
        normaliza_artigo("abc")


def test_artigo_vigente_sem_tachado(blocos):
    a = extrai_artigo(blocos, "8")
    assert a is not None
    assert a.vigente.startswith("Art. 8º Não poderão ser partes")
    assert "Somente as pessoas físicas capazes serão admitidas" not in a.vigente  # § 1º antigo, tachado
    assert "§ 1o Somente serão admitidas" in a.vigente
    assert "II - as microempresas e empresas de pequeno porte" in a.vigente
    assert "II - as microempresas;" not in a.vigente
    assert "com assistência" not in a.vigente  # tachado parcial dentro do parágrafo
    assert "independentemente de assistência" in a.vigente
    assert "Art. 9º" not in a.vigente


def test_artigo_completo_marca_revogados(blocos):
    a = extrai_artigo(blocos, "8")
    assert "[[REVOGADO: § 1º Somente as pessoas físicas" in a.completo
    assert "[[REVOGADO: com assistência]]" in a.completo


def test_artigo_com_sufixo_e_redacao_antiga(blocos):
    a = extrai_artigo(blocos, "12-A")
    assert a.vigente == "Art. 12-A. Na contagem de prazo em dias computar-se-ão somente os dias úteis."
    assert "Texto antigo revogado" in a.completo


def test_para_no_cabecalho_estrutural(blocos):
    a = extrai_artigo(blocos, "12-A")
    assert "Seção V" not in a.completo


def test_milhar(blocos):
    a = extrai_artigo(blocos, "1015")
    assert "I - tutelas provisórias;" in a.vigente
    assert "Art. 20" not in a.completo


def test_revogado_integralmente(blocos):
    a = extrai_artigo(blocos, "20")
    assert a.revogado_integralmente
    assert a.vigente == ""


def test_para_no_fecho(blocos):
    a = extrai_artigo(blocos, "21")
    assert "Brasília" not in a.completo


def test_inexistente(blocos):
    assert extrai_artigo(blocos, "999") is None


def test_art_1_nao_casa_com_10():
    b = html_para_blocos("<p>Art. 10. Dez.</p><p>Art. 1º Um.</p><p>Art. 2º Dois.</p>")
    assert extrai_artigo(b, "1").vigente == "Art. 1º Um."


def test_comparacao_ignora_notas_e_ordinais():
    a = "§ 1º Somente serão admitidas: (Redação dada pela Lei nº 12.126, de 2009)"
    b = "§ 1o  Somente serão admitidas:"
    assert normaliza_comparacao(a) == normaliza_comparacao(b)


def test_portal_novo_sumario_nao_confunde_e_secao_encerra():
    from mcp_legislacao_br.parser import extrai_artigo, html_para_blocos
    html = (Path(__file__).parent / "fixtures" / "portal_novo_l9099_trecho.html").read_text("utf-8")
    blocos = html_para_blocos(html)
    assert not any("Sumário" in b.completo for b in blocos)
    art50 = extrai_artigo(blocos, "50")
    assert art50.vigente.startswith("Art. 50. Os embargos de declaração interrompem")
    assert "Seção XIV" not in art50.completo and "suspenderão" in art50.completo
    art51 = extrai_artigo(blocos, "51")
    assert art51.vigente.endswith("audiências do processo;") and "Brasília" not in art51.vigente


def test_ancoras_e_portais():
    from mcp_legislacao_br.fontes import ancora_artigo, metadados_pagina, para_classico, para_portal
    assert ancora_artigo("48") == "#art48" and ancora_artigo("121-A") == "#art121a" and ancora_artigo("1015") == "#art1015"
    u = "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"
    assert para_portal(u) == "https://portaldalegislacao.presidencia.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"
    assert para_classico(para_portal(u)) == u
    html = (Path(__file__).parent / "fixtures" / "portal_novo_l9099_trecho.html").read_text("utf-8")
    assert metadados_pagina(html)["urn_lexml"] == "urn:lex:br:federal:lei:1995-09-26;9099"


def test_candidatos_planalto():
    assert candidatos_planalto("lei", "13.105", 2015)[2] == "https://portaldalegislacao.presidencia.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"
    assert any(u.endswith("/leis/l9099.htm") for u in candidatos_planalto("lei", 9099, 1995))
    assert any(u.endswith("/leis/2002/l10406compilada.htm") for u in candidatos_planalto("lei", 10406, 2002))
    assert candidatos_planalto("decreto-lei", 2848, 1940)[0].endswith("/decreto-lei/del2848compilado.htm")
    assert candidatos_planalto("cf", 1988, 1988)[0].endswith("/constituicao/constituicaocompilado.htm")
    assert any("/_ato2023-2026/2024/lei/l14994" in u for u in candidatos_planalto("lei", 14994, 2024))


def test_tipos():
    assert normaliza_tipo("LC") == "lei_complementar"
    assert normaliza_tipo("Decreto-Lei") == "decreto_lei"
    with pytest.raises(ValueError):
        normaliza_tipo("portaria")


def test_filtra_dispositivos():
    info = {"dispositivos": [
        {"dispositivo": "Art. 319, § 1"}, {"dispositivo": "Art. 31"}, {"dispositivo": "Art. 319"},
        {"dispositivo": "Art. 1.015, I"}, {"dispositivo": "Art. 12-A"}, {"dispositivo": "Art. 12"},
    ]}
    assert [d["dispositivo"] for d in filtra_dispositivos(info, "319")] == ["Art. 319, § 1", "Art. 319"]
    assert [d["dispositivo"] for d in filtra_dispositivos(info, "1015")] == ["Art. 1.015, I"]
    assert [d["dispositivo"] for d in filtra_dispositivos(info, "12-A")] == ["Art. 12-A"]
    assert [d["dispositivo"] for d in filtra_dispositivos(info, "12")] == ["Art. 12"]
