import json
from pathlib import Path

import httpx
import pytest
import respx

from mcp_legislacao_br import rede
from mcp_legislacao_br import server as S

FIX = (Path(__file__).parent / "fixtures" / "planalto_amostra.htm").read_bytes()
NOVO = (Path(__file__).parent / "fixtures" / "portal_novo_l9099_trecho.html").read_bytes()
PORTAL = "https://portaldalegislacao.presidencia.gov.br/ccivil_03"


def _portal_bloqueia():
    """O portal novo desvia acessos automatizados para gov.br/planalto (comportamento real)."""
    respx.get(url__startswith=PORTAL).mock(return_value=httpx.Response(302, headers={"Location": "https://gov.br/planalto"}))
    respx.get("https://gov.br/planalto").mock(return_value=httpx.Response(200, content=b"<html>teste para saber se voce e humano</html>"))
URN = "urn:lex:br:federal:lei:1995-09-26;9099"


@pytest.fixture(autouse=True)
def cache_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGISLACAO_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(rede, "_cliente", None)

    async def sem_espera(_):
        return None

    monkeypatch.setattr(rede.asyncio, "sleep", sem_espera)


@respx.mock
async def test_novas_tentativas_e_cache():
    url = "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm"
    rota = respx.get(url).mock(side_effect=[httpx.ConnectTimeout("lento"), httpx.Response(200, content=FIX)])
    r = await rede.obter(url)
    assert r.origem == "ao vivo" and rota.call_count == 2
    r2 = await rede.obter(url)
    assert r2.origem == "cache" and rota.call_count == 2


@respx.mock
async def test_bloqueio_usa_cache_antigo_com_aviso(monkeypatch):
    url = "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm"
    respx.get(url).mock(return_value=httpx.Response(200, content=FIX))
    await rede.obter(url)
    respx.get(url).mock(return_value=httpx.Response(200, content=b"<html>Acesso Negado! Esta requisicao foi bloqueada.</html>"))
    r = await rede.obter(url, forcar_ao_vivo=True)
    assert r.origem == "cache" and "Fonte sem resposta" in r.aviso


@respx.mock
async def test_sem_cache_levanta():
    url = "https://www.planalto.gov.br/x.htm"
    respx.get(url).mock(side_effect=httpx.ConnectError("off"))
    with pytest.raises(rede.FonteIndisponivel):
        await rede.obter(url)


def _mocks_fontes(html_camara: bytes):
    _portal_bloqueia()
    respx.get(url__regex=r"https://www\.planalto\.gov\.br/ccivil_03/leis/l9099compilad[oa]\.htm").mock(return_value=httpx.Response(404))
    respx.get("https://www.planalto.gov.br/ccivil_03/leis/l9099.htm").mock(return_value=httpx.Response(200, content=FIX))
    respx.get(url__startswith="https://legis.senado.leg.br/sigen/api/catalogo/basico").mock(return_value=httpx.Response(200, json={
        "searchHits": [{"id": URN, "content": {"urn": URN, "nome": "Lei nº 9.099 de 26/09/1995", "tipo": "lei", "numero": 9099,
                                               "assinatura": "1995-09-26", "ementa": "Dispõe sobre os Juizados", "urnRevogacao": None}}]}))
    respx.get(url__startswith="https://normas.leg.br/api/public/normas").mock(return_value=httpx.Response(200, json={
        "name": "Lei nº 9.099 de 26/09/1995", "sameAs": ["https://legis.senado.leg.br/legislacao/DetalhaSigen.action?id=123"],
        "encoding": [{"name": "Compilação Monovigente na CD", "version": "Current", "contentUrl": "https://normas.leg.br/api/binario/abc/texto"}]}))
    respx.get("https://normas.leg.br/api/public/binario/abc/texto").mock(return_value=httpx.Response(200, content=html_camara, headers={"content-type": "text/html; charset=utf-8"}))
    respx.get("https://legis.senado.leg.br/dadosabertos/legislacao/123").mock(return_value=httpx.Response(200, content=
        b"<DetalheDocumento><documentos><documento id='123'><identificacao><normaNome>Lei 9099</normaNome></identificacao>"
        b"<disps><disp><nomeDispositivo>Art. 8, \xc2\xa7 1</nomeDispositivo><refs><ref><dispositivo>Art. 1</dispositivo><comentario>alterado</comentario>"
        b"<codNormaPosterior>9</codNormaPosterior></ref></refs></disp><disp><nomeDispositivo>Art. 80</nomeDispositivo></disp></disps></documento></documentos></DetalheDocumento>"))


@respx.mock
async def test_conferir_vigencia_coincide():
    camara = ("<p>Art. 12-A. Na contagem de prazo em dias computar-se-&atilde;o somente os dias &uacute;teis. "
              "(Inclu&iacute;do pela Lei n&ordm; 13.728, de 2018)</p><p>Art. 13. X</p>").encode()
    _mocks_fontes(camara)
    out = await S.conferir_vigencia("12-A", "lei", "9099", 1995)
    assert out["redacoes_coincidem"] is True, json.dumps(out, ensure_ascii=False, indent=1)
    assert out["planalto"]["url"] == "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm"
    assert out["planalto"]["portal"] == "clássico (reserva)"
    assert out["planalto"]["url_artigo"] == PORTAL + "/leis/l9099.htm#art12a"
    assert out["camara"]["urn"] == URN


@respx.mock
async def test_conferir_vigencia_diverge_e_senado():
    camara = "<p>Art. 8º Não poderão ser partes o incapaz.</p><p>Art. 9º Y</p>".encode()
    _mocks_fontes(camara)
    out = await S.conferir_vigencia("8", "lei", "9099", 1995)
    assert out["redacoes_coincidem"] is False and "DIVERGÊNCIA" in out["sintese"]
    assert [d["dispositivo"] for d in out["senado"]["dispositivos"]] == ["Art. 8, § 1"]


@respx.mock
async def test_fonte_fora_vira_marcador():
    respx.get(url__startswith=PORTAL).mock(side_effect=httpx.ConnectError("off"))
    respx.get(url__startswith="https://www.planalto.gov.br/").mock(side_effect=httpx.ConnectError("off"))
    out = await S.artigo_planalto("8", "lei", "9099", 1995)
    assert out["marcador"].startswith("[FONTE INDISPONÍVEL NESTA SESSÃO — Portal da Legislação")


@respx.mock
async def test_portal_novo_e_a_fonte_primaria():
    respx.get(url__regex=PORTAL.replace(".", r"\.") + r"/leis/l9099compilad[oa]\.htm").mock(return_value=httpx.Response(404))
    rota = respx.get(PORTAL + "/leis/l9099.htm").mock(return_value=httpx.Response(200, content=NOVO, headers={"content-type": "text/html; charset=utf-8"}))
    classico = respx.get(url__startswith="https://www.planalto.gov.br/")
    out = await S.artigo_planalto("48", "lei", "9099", 1995, incluir_revogado=True)
    assert rota.called and not classico.called
    assert out["portal"] == "Novo Portal da Legislação"
    assert out["url_artigo"] == PORTAL + "/leis/l9099.htm#art48"
    assert out["url_classico"] == "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm"
    assert out["urn_lexml"] == URN and out["ato"]["data"] == "1995-09-26"
    assert out["texto_vigente"].startswith("Art. 48. Caberão embargos de declaração contra sentença ou acórdão nos casos previstos no Código de Processo Civil.")
    assert "Os erros materiais podem ser corrigidos de ofício." in out["texto_vigente"]
    assert "houver obscuridade" not in out["texto_vigente"] and "[[REVOGADO:" in out["texto_com_revogados"]


@respx.mock
async def test_bloqueio_do_portal_novo_nao_repete_tentativas():
    _portal_bloqueia()
    with pytest.raises(rede.FonteIndisponivel, match="desviou"):
        await rede.obter(PORTAL + "/leis/l9099.htm")
    assert respx.calls.call_count == 2  # uma ida ao portal e o desvio, sem novas tentativas


@respx.mock
async def test_url_do_planalto_e_lida_primeiro_no_portal_novo():
    rota = respx.get(PORTAL + "/leis/l9099.htm").mock(return_value=httpx.Response(200, content=NOVO))
    out = await S.artigo_planalto("50", url="https://www.planalto.gov.br/ccivil_03/leis/l9099.htm")
    assert rota.called and out["texto_vigente"].startswith("Art. 50. Os embargos de declaração interrompem o prazo")


async def test_ferramentas_registradas():
    nomes = {t.name for t in await S.mcp.list_tools()}
    assert nomes == {"buscar_legislacao", "artigo_planalto", "texto_planalto", "artigo_camara",
                     "metadados_norma", "alteracoes_artigo", "conferir_vigencia"}
