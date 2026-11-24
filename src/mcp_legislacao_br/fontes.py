"""Fontes oficiais de legislação federal.

- Novo Portal da Legislação (Presidência da República, SAJ/Casa Civil, no ar
  desde 13/11/2026): fonte primária. Mesmo texto compilado e mesmos caminhos
  do Planalto (/ccivil_03/...), em HTML UTF-8, com redação revogada marcada
  por <del>, âncora estável por dispositivo (#art48, #art3i, #art3§1) e dados
  estruturados schema.org com a URN LexML. Não há API.
- Portal clássico (www.planalto.gov.br e portaldalegislacao-classico): reserva,
  com os mesmos caminhos e a redação revogada em <strike>.
- Senado Federal: busca no catálogo de normas (sigen) e dados abertos de
  legislação, com publicações, alterações e dispositivos alterados.
- Normas.leg.br (Congresso Nacional): metadados JSON-LD e textos; a versão
  "Current" é a compilação monovigente da Câmara dos Deputados.
- Câmara dos Deputados (Legin): páginas de texto original e atualizado.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from .rede import FonteIndisponivel, Resposta, obter

PORTAL = "https://portaldalegislacao.presidencia.gov.br/ccivil_03"
CLASSICO = "https://www.planalto.gov.br/ccivil_03"
PLANALTO = PORTAL  # compatibilidade: o nome antigo aponta para o portal novo
DOMINIOS_PRESIDENCIA = re.compile(
    r"^https?://(?:www\.)?(?:planalto\.gov\.br|portaldalegislacao(?:-classico)?\.presidencia\.gov\.br)/",
    re.I,
)
NORMAS = "https://normas.leg.br"
SENADO = "https://legis.senado.leg.br"

# Tipos aceitos -> (segmento da URN LexML, sigla dos dados abertos do Senado)
TIPOS = {
    "lei": ("lei", "LEI"),
    "lei_complementar": ("lei.complementar", "LCP"),
    "decreto_lei": ("decreto.lei", "DEL"),
    "decreto": ("decreto", "DEC"),
    "medida_provisoria": ("medida.provisoria", "MPV"),
    "constituicao": ("constituicao", "CON"),
    "emenda_constitucional": ("emenda.constitucional", "EMC"),
}

ALIASES = {
    "lc": "lei_complementar", "lcp": "lei_complementar", "lei complementar": "lei_complementar",
    "dl": "decreto_lei", "del": "decreto_lei", "decreto-lei": "decreto_lei", "decreto lei": "decreto_lei",
    "dec": "decreto", "mp": "medida_provisoria", "mpv": "medida_provisoria", "medida provisoria": "medida_provisoria",
    "medida provisória": "medida_provisoria", "cf": "constituicao", "crfb": "constituicao", "constituição": "constituicao",
    "ec": "emenda_constitucional", "emc": "emenda_constitucional", "emenda constitucional": "emenda_constitucional",
}


def normaliza_tipo(tipo: str) -> str:
    t = tipo.strip().lower().replace("_", " ")
    t = ALIASES.get(t, t).replace(" ", "_").replace("-", "_")
    if t not in TIPOS:
        raise ValueError(f"Tipo de norma não suportado: {tipo!r}. Use um de: {', '.join(TIPOS)}")
    return t


# ---------------------------------------------------------------- Portal da Legislação (Planalto)

_BLOCOS_ATO = [(2004, 2006), (2007, 2010), (2011, 2014), (2015, 2018), (2019, 2022), (2023, 2026), (2027, 2030)]


def _bloco_ato(ano: int) -> str | None:
    for a, b in _BLOCOS_ATO:
        if a <= ano <= b:
            return f"_ato{a}-{b}"
    return None


def caminhos_planalto(tipo: str, numero: int | str, ano: int) -> list[str]:
    """Caminhos prováveis sob /ccivil_03, da compilada para a simples."""
    tipo = normaliza_tipo(tipo)
    n = str(numero).replace(".", "")
    if tipo == "constituicao":
        return [f"/constituicao/constituicaocompilado.htm", f"/constituicao/constituicao.htm"]
    if tipo == "emenda_constitucional":
        return [f"/constituicao/emendas/emc/emc{n}.htm"]
    if tipo == "lei_complementar":
        bases = [f"/leis/lcp/lcp{n}"]
    elif tipo == "decreto_lei":
        bases = [f"/decreto-lei/del{n}"]
    else:
        pasta = {"lei": "lei", "decreto": "decreto", "medida_provisoria": "mpv"}[tipo]
        pref = {"lei": "l", "decreto": "d", "medida_provisoria": "mpv"}[tipo]
        bases = []
        bloco = _bloco_ato(ano)
        if bloco:
            bases.append(f"/{bloco}/{ano}/{pasta}/{pref}{n}")
        if tipo == "lei":
            if 2001 <= ano <= 2003:
                bases.append(f"/leis/{ano}/l{n}")
            bases.append(f"/leis/l{n}")
        elif tipo == "decreto":
            if 2001 <= ano <= 2003:
                bases.append(f"/decreto/{ano}/d{n}")
            bases.append(f"/decreto/d{n}")
        elif tipo == "medida_provisoria":
            bases.append(f"/mpv/{ano}/{n}")
    urls = []
    for b in bases:
        urls += [f"{b}compilado.htm", f"{b}compilada.htm", f"{b}.htm"]
    return urls


def candidatos_planalto(tipo: str, numero: int | str, ano: int, raiz: str = PORTAL) -> list[str]:
    """URLs prováveis numa raiz (portal novo por padrão), da compilada para a simples."""
    return [raiz + c for c in caminhos_planalto(tipo, numero, ano)]


def para_classico(url: str) -> str:
    """Endereço equivalente no portal clássico (os caminhos foram preservados)."""
    return re.sub(r"^https?://[^/]+/ccivil_03", CLASSICO, url, flags=re.I)


def para_portal(url: str) -> str:
    """Endereço equivalente no Novo Portal da Legislação."""
    return re.sub(r"^https?://[^/]+/ccivil_03", PORTAL, url, flags=re.I)


def ancora_artigo(artigo: str) -> str:
    """'48' -> '#art48'; '1015' -> '#art1015'; '121-A' -> '#art121a' (padrão do portal novo)."""
    return "#art" + artigo.replace("-", "").lower()


def eh_portal_novo(url: str) -> bool:
    return "portaldalegislacao.presidencia.gov.br" in url.lower()


def metadados_pagina(html: str) -> dict:
    """Dados estruturados (schema.org Legislation) que o portal novo publica em cada ato."""
    import json as _json

    out: dict = {}
    for bloco in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            dados = _json.loads(bloco)
        except ValueError:
            continue
        for item in dados.get("@graph", [dados]) if isinstance(dados, dict) else []:
            if item.get("@type") == "Legislation":
                out = {
                    "nome": item.get("name"),
                    "ementa": item.get("description"),
                    "tipo_ato": item.get("legislationType"),
                    "data": item.get("legislationDate"),
                    "urn_lexml": item.get("legislationIdentifier"),
                    "url_canonica": item.get("url"),
                    "lexml": item.get("sameAs"),
                }
                return out
    return out


def _numero_formatado(n: str) -> str:
    n = n.replace(".", "")
    return f"{int(n):,}".replace(",", ".")


def _valida_planalto(numero: str):
    alvo = [_numero_formatado(numero), numero.replace(".", "")]

    def validar(r: Resposta) -> str | None:
        inicio = r.texto()[:20000]
        if not any(a in inicio for a in alvo):
            return f"página {r.url} não corresponde à norma nº {alvo[0]}"
        return None

    return validar


def _e_404(msg: str) -> bool:
    return "HTTP 404" in msg or "não corresponde" in msg


async def planalto_por_norma(tipo: str, numero: int | str, ano: int, forcar_ao_vivo: bool = False) -> Resposta:
    """Busca no Novo Portal da Legislação; se ele recusar ou falhar, no portal clássico.

    Os dois portais usam os mesmos caminhos. Se o portal novo responder 404 para
    todos os candidatos, a norma não está lá e o clássico também é consultado.
    """
    erros = []
    validar = None if normaliza_tipo(tipo) == "constituicao" else _valida_planalto(str(numero))
    for raiz in (PORTAL, CLASSICO):
        for url in candidatos_planalto(tipo, numero, ano, raiz):
            try:
                return await obter(url, forcar_ao_vivo=forcar_ao_vivo, validar=validar)
            except FonteIndisponivel as e:
                erros.append(str(e))
                if not _e_404(str(e)):
                    break  # bloqueio ou rede: passa para a próxima raiz
    raise FonteIndisponivel("Portal da Legislação e portal clássico: nenhuma URL candidata respondeu. " + " | ".join(erros[-3:]))


async def planalto_por_url(url: str, forcar_ao_vivo: bool = False) -> Resposta:
    """Lê a URL informada no portal novo; se falhar, o mesmo caminho no clássico."""
    if not DOMINIOS_PRESIDENCIA.match(url):
        raise ValueError("A URL precisa ser do Portal da Legislação (portaldalegislacao.presidencia.gov.br) ou do planalto.gov.br")
    primeira = para_portal(url) if "/ccivil_03/" in url.lower() else url
    try:
        return await obter(primeira, forcar_ao_vivo=forcar_ao_vivo)
    except FonteIndisponivel as e:
        if "/ccivil_03/" not in url.lower():
            raise
        try:
            return await obter(para_classico(url), forcar_ao_vivo=forcar_ao_vivo)
        except FonteIndisponivel as e2:
            raise FonteIndisponivel(f"portal novo: {e} | clássico: {e2}") from e2


# ---------------------------------------------------------------- Senado: busca

@dataclass
class NormaEncontrada:
    urn: str
    nome: str
    tipo: str
    numero: int | None
    assinatura: str | None
    ementa: str
    apelido: str | None
    urn_revogacao: str | None

    def como_dict(self) -> dict:
        d = self.__dict__.copy()
        d["revogada"] = bool(self.urn_revogacao)
        d["url_normas_leg_br"] = f"{NORMAS}/?urn={self.urn}"
        return d


async def buscar_catalogo(termo: str, ano_inicial: int = 1822, ano_final: int = 2100, limite: int = 10) -> tuple[list[NormaEncontrada], Resposta]:
    qs = urlencode({"q": termo, "anoInicial": ano_inicial, "anoFinal": ano_final})
    r = await obter(f"{SENADO}/sigen/api/catalogo/basico?{qs}", usar_cache=True)
    dados = r.json()
    hits = dados.get("searchHits", [])[:limite]
    out = []
    for h in hits:
        c = h.get("content", {})
        out.append(
            NormaEncontrada(
                urn=c.get("urn") or h.get("id"),
                nome=c.get("nome", ""),
                tipo=c.get("tipo", ""),
                numero=c.get("numero"),
                assinatura=c.get("assinatura"),
                ementa=c.get("ementa", ""),
                apelido=c.get("apelido"),
                urn_revogacao=c.get("urnRevogacao"),
            )
        )
    return out, r


async def resolver_urn(tipo: str, numero: int | str, ano: int) -> str:
    """Encontra a URN LexML de uma norma pelo tipo, número e ano."""
    tipo = normaliza_tipo(tipo)
    seg = TIPOS[tipo][0]
    if tipo == "constituicao":
        return "urn:lex:br:federal:constituicao:1988-10-05;1988"
    n = int(str(numero).replace(".", ""))
    candidatos, _ = await buscar_catalogo(str(n), ano, ano, limite=50)
    for c in candidatos:
        if c.urn and f":{seg}:" in c.urn and c.urn.endswith(f";{n}") and (c.assinatura or "").startswith(str(ano)):
            return c.urn
    # Tentativa por nome, quando a busca só pelo número não basta.
    candidatos, _ = await buscar_catalogo(f"{_numero_formatado(str(n))}", ano, ano, limite=50)
    for c in candidatos:
        if c.urn and f":{seg}:" in c.urn and c.urn.endswith(f";{n}"):
            return c.urn
    raise FonteIndisponivel(f"Norma não localizada no catálogo do Senado: {tipo} {n}/{ano}")


# ---------------------------------------------------------------- normas.leg.br

async def metadados_normas(urn: str) -> tuple[dict, Resposta]:
    qs = urlencode({"urn": urn, "tipo_documento": "maior-detalhe"})
    r = await obter(f"{NORMAS}/api/public/normas?{qs}")
    return r.json(), r


def versoes_texto(meta: dict) -> list[dict]:
    out = []
    for e in meta.get("encoding", []) or []:
        url = e.get("contentUrl", "")
        url = url.replace("/api/binario/", "/api/public/binario/") if "/api/public/" not in url else url
        out.append(
            {
                "nome": (e.get("name") or "").strip(),
                "versao": e.get("version"),  # "Original" ou "Current"
                "valor_legal": e.get("legislationLegalValue"),
                "data_publicacao": e.get("datePublished"),
                "url_texto": url,
            }
        )
    return out


def id_senado(meta: dict) -> str | None:
    for s in meta.get("sameAs", []) or []:
        m = re.search(r"DetalhaSigen\.action\?id=(\d+)", s)
        if m:
            return m.group(1)
    return None


async def texto_normas(urn: str, versao: str = "Current", forcar_ao_vivo: bool = False) -> tuple[Resposta, dict, dict]:
    meta, _ = await metadados_normas(urn)
    versoes = versoes_texto(meta)
    escolhida = next((v for v in versoes if (v["versao"] or "").lower() == versao.lower()), None)
    if not escolhida:
        disp = ", ".join(f"{v['versao']} ({v['nome']})" for v in versoes) or "nenhuma"
        raise FonteIndisponivel(f"Versão {versao!r} indisponível no normas.leg.br para {urn}. Disponíveis: {disp}")
    r = await obter(escolhida["url_texto"], forcar_ao_vivo=forcar_ao_vivo)
    return r, meta, escolhida


# ---------------------------------------------------------------- Senado: dados abertos

def _txt(el, tag):
    x = el.find(tag)
    return x.text.strip() if x is not None and x.text else None


async def detalhe_senado(codigo: str) -> tuple[dict, Resposta]:
    r = await obter(f"{SENADO}/dadosabertos/legislacao/{quote(codigo)}")
    raiz = ET.fromstring(r.conteudo)
    doc = raiz.find(".//documento")
    if doc is None:
        raise FonteIndisponivel(f"Senado: documento {codigo} sem dados")
    ident = doc.find("identificacao")
    info = {
        "codigo": codigo,
        "norma": _txt(ident, "normaNome") if ident is not None else None,
        "apelido": _txt(ident, "apelido") if ident is not None else None,
        "url_documento": _txt(ident, "urlDocumento") if ident is not None else None,
        "publicacoes": [
            {k: _txt(p, k) for k in ("tipo", "fonte", "data", "pagina", "coluna", "dispositivo")}
            for p in doc.findall("./publicacoes/publicacao")
        ],
        "alteracoes_posteriores": [
            {
                "norma_posterior": _txt(v, "nomeNormaPosterior"),
                "data_assinatura": _txt(v, "datAssinatura"),
                "comentario": _txt(v, "comentario"),
                "itens": [{"dispositivo": _txt(i, "dispositivo"), "comentario": _txt(i, "comentario")} for i in v.findall("./itens/item")],
            }
            for v in doc.findall("./vides/vide")
        ],
        "dispositivos": [
            {
                "dispositivo": _txt(d, "nomeDispositivo"),
                "referencias": [
                    {"dispositivo": _txt(rf, "dispositivo"), "comentario": _txt(rf, "comentario"), "cod_norma_posterior": _txt(rf, "codNormaPosterior")}
                    for rf in d.findall("./refs/ref")
                ],
            }
            for d in doc.findall("./disps/disp")
        ],
    }
    return info, r


def filtra_dispositivos(info: dict, artigo_normalizado: str) -> list[dict]:
    """Dispositivos do Senado que pertencem ao artigo pedido (ex.: 'Art. 319', 'Art. 319, § 1')."""
    alvo = artigo_normalizado.upper()
    out = []
    for d in info.get("dispositivos", []):
        m = re.match(
            r"^\s*Art(?:igo)?\.?\s*(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:º|°|o)?\s*(?:-\s*([A-Z]{1,2})\b)?",
            d.get("dispositivo") or "",
            re.I,
        )
        if not m:
            continue
        chave = str(int(m.group(1).replace(".", "")))
        if m.group(2):
            chave += f"-{m.group(2).upper()}"
        if chave == alvo:
            out.append(d)
    return out


# ---------------------------------------------------------------- Câmara (Legin)

async def camara_por_url(url: str, forcar_ao_vivo: bool = False) -> Resposta:
    if not re.match(r"^https?://(www2?\.)?camara\.(leg|gov)\.br/", url, re.I):
        raise ValueError("A URL precisa ser do domínio camara.leg.br")
    return await obter(url, forcar_ao_vivo=forcar_ao_vivo)
