"""Leitura do HTML das normas e extração de artigos.

O Planalto marca a redação revogada ou alterada com <strike> (também aceitamos
<s> e <del>). O texto "vigente" é o texto com esses trechos removidos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

STRUCK_TAGS = {"strike", "s", "del"}
BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "blockquote", "center"}

# "Art. 1º", "Art. 1o", "Art. 10.", "Art. 1.015.", "Art. 12-A.", "Art. 3º-A", "Artigo 5º"
ART_RE = re.compile(
    r"^\s*Art(?:igo)?\.?\s*"
    r"(?P<num>\d{1,3}(?:\.\d{3})+|\d+)"
    r"\s*(?:º|°|ª|o(?=[\s.\-–]|$))?"
    r"\s*(?:[-–]\s*(?P<suf>[A-Z]{1,2})\b)?",
)
# Cabeçalhos estruturais que encerram um artigo.
HEADING_RE = re.compile(
    r"^\s*(PARTE|LIVRO|T[ÍI]TULO|CAP[ÍI]TULO|Cap[íi]tulo|SE[ÇC][ÃA]O|Se[çc][ãa]o|SUBSE[ÇC][ÃA]O|Subse[çc][ãa]o)\b"
)
END_RE = re.compile(r"^\s*(Bras[íi]lia,|Este texto n[ãa]o substitui)")
WS_RE = re.compile(r"[ \t\r\f\v ]+")


@dataclass
class Bloco:
    """Um parágrafo do documento."""

    vigente: str  # texto sem os trechos tachados
    completo: str  # texto com os trechos tachados marcados entre [[REVOGADO: ...]]
    tachado: bool = field(default=False)  # parágrafo inteiramente tachado


def _limpa(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto)
    texto = WS_RE.sub(" ", texto)
    linhas = [ln.strip() for ln in texto.split("\n")]
    return " ".join(ln for ln in linhas if ln).strip()


def _coleta(node, partes_vig: list[str], partes_comp: list[str], tachado: bool) -> None:
    if isinstance(node, NavigableString):
        if node.__class__.__name__ in {"Comment", "Doctype", "Declaration", "ProcessingInstruction"}:
            return
        s = str(node)
        partes_comp.append(s)
        if not tachado:
            partes_vig.append(s)
        return
    if not isinstance(node, Tag):
        return
    if node.name in {"script", "style", "head", "title", "noscript"}:
        return
    if node.name == "br":
        partes_comp.append("\n")
        if not tachado:
            partes_vig.append("\n")
        return
    novo_tachado = tachado or node.name in STRUCK_TAGS
    if novo_tachado and not tachado:
        partes_comp.append(" [[REVOGADO: ")
        for filho in node.children:
            _coleta(filho, partes_vig, partes_comp, True)
        partes_comp.append("]] ")
        return
    for filho in node.children:
        _coleta(filho, partes_vig, partes_comp, novo_tachado)


def _blocos_folha(soup: BeautifulSoup) -> list[Tag]:
    """Elementos de bloco que não contêm outros elementos de bloco."""
    folhas = []
    for el in soup.find_all(BLOCK_TAGS):
        if el.find(BLOCK_TAGS) is None:
            folhas.append(el)
    return folhas


def html_para_blocos(html: str | bytes, encoding: str | None = None) -> list[Bloco]:
    soup = BeautifulSoup(html, "lxml", from_encoding=encoding) if isinstance(html, bytes) else BeautifulSoup(html, "lxml")
    blocos: list[Bloco] = []
    for el in _blocos_folha(soup):
        vig: list[str] = []
        comp: list[str] = []
        ja_tachado = any(p.name in STRUCK_TAGS for p in el.parents if isinstance(p, Tag))
        _coleta(el, vig, comp, ja_tachado)
        completo = _limpa("".join(comp))
        if not completo:
            continue
        vigente = _limpa("".join(vig))
        if ja_tachado:
            completo = f"[[REVOGADO: {completo}]]"
        blocos.append(Bloco(vigente=vigente, completo=completo, tachado=not vigente))
    return blocos


def texto_documento(blocos: list[Bloco], somente_vigente: bool = True) -> str:
    campo = "vigente" if somente_vigente else "completo"
    return "\n".join(getattr(b, campo) for b in blocos if getattr(b, campo))


def normaliza_artigo(artigo: str | int) -> str:
    """'319' -> '319'; '1.015' -> '1015'; 'art. 12-a' -> '12-A'; '5º' -> '5'."""
    s = str(artigo).strip()
    s = re.sub(r"^\s*art(?:igo)?\.?\s*", "", s, flags=re.I)
    m = re.match(r"(\d[\d.]*)\s*(?:º|°|ª|o)?\s*(?:[-–]\s*([A-Za-z]{1,2}))?\s*$", s)
    if not m:
        raise ValueError(f"Número de artigo inválido: {artigo!r}")
    num = m.group(1).replace(".", "").rstrip(".")
    num = str(int(num))
    suf = m.group(2)
    return f"{num}-{suf.upper()}" if suf else num


def _chave_inicio(texto: str) -> str | None:
    m = ART_RE.match(texto)
    if not m:
        return None
    num = str(int(m.group("num").replace(".", "")))
    return f"{num}-{m.group('suf')}" if m.group("suf") else num


@dataclass
class Artigo:
    numero: str
    vigente: str
    completo: str
    revogado_integralmente: bool


def extrai_artigo(blocos: list[Bloco], artigo: str | int) -> Artigo | None:
    """Localiza o artigo e devolve o caput com parágrafos, incisos e alíneas.

    O artigo termina no início do artigo seguinte, num cabeçalho estrutural
    (Capítulo, Seção...) ou no fecho da norma. Se o mesmo artigo aparecer mais
    de uma vez (redação antiga tachada seguida da nova), todas as ocorrências
    contíguas entram no resultado.
    """
    alvo = normaliza_artigo(artigo)
    inicio = None
    for i, b in enumerate(blocos):
        if _chave_inicio(b.completo.replace("[[REVOGADO: ", "", 1)) == alvo or _chave_inicio(b.vigente) == alvo:
            inicio = i
            break
    if inicio is None:
        return None
    fim = len(blocos)
    for j in range(inicio + 1, len(blocos)):
        b = blocos[j]
        bruto = b.completo.replace("[[REVOGADO: ", "", 1)
        chave = _chave_inicio(b.vigente) or _chave_inicio(bruto)
        if chave is not None and chave != alvo:
            fim = j
            break
        if HEADING_RE.match(bruto) or END_RE.match(bruto):
            fim = j
            break
    trecho = blocos[inicio:fim]
    vigente = "\n".join(b.vigente for b in trecho if b.vigente)
    completo = "\n".join(b.completo for b in trecho if b.completo)
    return Artigo(
        numero=alvo,
        vigente=vigente,
        completo=completo,
        revogado_integralmente=not vigente.strip(),
    )


def normaliza_comparacao(texto: str) -> str:
    """Texto reduzido para comparar redações entre fontes."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\((?:reda[cç][aã]o dada|inclu[ií]d[oa]|vide|revogad[oa]|vig[eê]ncia|produ[cç][aã]o de efeitos)[^)]*\)", " ", t)
    t = t.replace("º", "o").replace("°", "o").replace("ª", "a")
    t = re.sub(r"(\d)o\b", r"\1", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return t.strip()
