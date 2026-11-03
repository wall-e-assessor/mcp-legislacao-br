"""Acesso HTTP com novas tentativas, tempo limite e cache local datado.

Só o documento principal é baixado (nada de imagens, estilos ou scripts), o que
evita o travamento observado quando um arquivo auxiliar do Planalto demora.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import __version__

USER_AGENT = (
    f"mcp-legislacao-br/{__version__} "
    "(consulta pontual de legislacao; +https://github.com/wall-e-assessor/mcp-legislacao-br) python-httpx"
)
TENTATIVAS = int(os.environ.get("LEGISLACAO_TENTATIVAS", "3"))
TIMEOUT = httpx.Timeout(
    connect=float(os.environ.get("LEGISLACAO_TIMEOUT_CONEXAO", "15")),
    read=float(os.environ.get("LEGISLACAO_TIMEOUT_LEITURA", "60")),
    write=15.0,
    pool=15.0,
)
TTL_HORAS = float(os.environ.get("LEGISLACAO_CACHE_HORAS", "24"))

BLOQUEIO_RE = re.compile(r"Acesso Negado|requisi[çc][ãa]o foi bloqueada", re.I)


class FonteIndisponivel(Exception):
    """A fonte não respondeu com conteúdo utilizável e não há cache."""


@dataclass
class Resposta:
    url: str
    conteudo: bytes
    tipo: str
    consultado_em: str  # ISO 8601 (UTC) da obtenção do conteúdo
    origem: str  # "ao vivo" ou "cache"
    aviso: str | None = None

    def texto(self) -> str:
        return self.conteudo.decode(detecta_charset(self.conteudo, self.tipo), errors="replace")

    def json(self):
        return json.loads(self.conteudo.decode("utf-8", errors="replace"))


def detecta_charset(conteudo: bytes, content_type: str = "") -> str:
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        return _normaliza_charset(m.group(1))
    m = re.search(rb"<meta[^>]+charset=[\"']?([\w\-]+)", conteudo[:4096], re.I)
    if m:
        return _normaliza_charset(m.group(1).decode("ascii", "ignore"))
    try:
        conteudo.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "windows-1252"


def _normaliza_charset(cs: str) -> str:
    cs = cs.lower()
    return "windows-1252" if cs in {"iso-8859-1", "latin-1", "latin1", "us-ascii"} else cs


def pasta_cache() -> Path:
    base = os.environ.get("LEGISLACAO_CACHE_DIR")
    if base:
        p = Path(base)
    elif os.name == "nt":
        p = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "mcp-legislacao-br" / "cache"
    else:
        p = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mcp-legislacao-br"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _arquivos_cache(url: str) -> tuple[Path, Path]:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    base = pasta_cache()
    return base / f"{h}.bin", base / f"{h}.json"


def _le_cache(url: str) -> Resposta | None:
    dados, meta = _arquivos_cache(url)
    if not (dados.exists() and meta.exists()):
        return None
    m = json.loads(meta.read_text("utf-8"))
    return Resposta(url=url, conteudo=dados.read_bytes(), tipo=m.get("tipo", ""), consultado_em=m["consultado_em"], origem="cache")


def _grava_cache(r: Resposta) -> None:
    dados, meta = _arquivos_cache(r.url)
    dados.write_bytes(r.conteudo)
    meta.write_text(json.dumps({"url": r.url, "tipo": r.tipo, "consultado_em": r.consultado_em}), "utf-8")


def _idade_horas(iso: str) -> float:
    dt = datetime.fromisoformat(iso)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


_cliente: httpx.AsyncClient | None = None


def cliente() -> httpx.AsyncClient:
    global _cliente
    if _cliente is None:
        _cliente = httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
        )
    return _cliente


async def obter(url: str, *, usar_cache: bool = True, forcar_ao_vivo: bool = False, validar=None) -> Resposta:
    """Baixa a URL com novas tentativas.

    - Cache dentro do prazo (LEGISLACAO_CACHE_HORAS) é usado, salvo forcar_ao_vivo.
    - Se a fonte falhar, devolve o cache antigo com aviso. Sem cache, levanta
      FonteIndisponivel.
    - `validar(resposta) -> str | None` devolve mensagem de erro quando o
      conteúdo não serve (por exemplo, página de bloqueio).
    """
    em_cache = _le_cache(url) if usar_cache else None
    if em_cache and not forcar_ao_vivo and _idade_horas(em_cache.consultado_em) < TTL_HORAS:
        return em_cache

    erro = "erro desconhecido"
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = await cliente().get(url)
            if resp.status_code == 404:
                raise FonteIndisponivel(f"HTTP 404 em {url}")
            resp.raise_for_status()
            r = Resposta(
                url=str(resp.url),
                conteudo=resp.content,
                tipo=resp.headers.get("content-type", ""),
                consultado_em=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                origem="ao vivo",
            )
            if BLOQUEIO_RE.search(r.conteudo[:3000].decode("latin-1", "ignore")):
                raise httpx.HTTPError("a fonte devolveu página de bloqueio (Acesso Negado)")
            if validar and (msg := validar(r)):
                raise FonteIndisponivel(msg)
            if usar_cache:
                r.url = url
                _grava_cache(r)
            return r
        except FonteIndisponivel:
            raise
        except (httpx.HTTPError, OSError) as e:
            erro = f"{type(e).__name__}: {e}"
            if tentativa < TENTATIVAS:
                await asyncio.sleep(2 ** (tentativa - 1))

    if em_cache:
        em_cache.aviso = (
            f"Fonte sem resposta após {TENTATIVAS} tentativas ({erro}). "
            f"Conteúdo do cache local obtido em {em_cache.consultado_em}; reconferir ao vivo antes de uso definitivo."
        )
        return em_cache
    raise FonteIndisponivel(f"{url}: {erro} (após {TENTATIVAS} tentativas, sem cache)")
