# mcp-legislacao-br

Servidor [MCP](https://modelcontextprotocol.io) para consultar **legislação federal brasileira em fontes oficiais** e conferir a vigência de dispositivos, artigo por artigo:

| Fonte | O que entrega |
|---|---|
| **Novo Portal da Legislação** (Presidência da República, [portaldalegislacao.presidencia.gov.br](https://portaldalegislacao.presidencia.gov.br/)) | Fonte primária desde 13/11/2026: texto compilado, com a redação revogada separada da vigente, link direto do artigo e URN LexML do ato |
| **Portal clássico do Planalto** (www.planalto.gov.br) | Reserva automática, com os mesmos caminhos, quando o portal novo recusa ou falha |
| **Câmara dos Deputados** | Compilação monovigente (via normas.leg.br) e páginas do Legin |
| **Senado Federal** | Busca no catálogo de normas, publicações no DOU e alterações registradas por dispositivo |

## Por que rodar localmente

Os portais da Presidência bloqueiam requisições automatizadas vindas de servidores em nuvem: o portal novo desvia o acesso para `gov.br/planalto` e o clássico devolve "Acesso Negado". O servidor reconhece os dois bloqueios, não insiste e passa para a fonte seguinte. Rodando no seu computador, o servidor acessa as fontes pela sua própria conexão, como um navegador comum. Ele também baixa só o documento principal, sem imagens nem scripts, e por isso não trava quando um arquivo auxiliar do portal demora.

## Ferramentas

| Ferramenta | Uso |
|---|---|
| `buscar_legislacao` | Busca por número, apelido ("Código de Processo Civil") ou ementa |
| `artigo_planalto` | Um artigo no Portal da Legislação (portal novo, com o clássico como reserva): caput, parágrafos, incisos e alíneas, só com a redação vigente ou também com a revogada marcada como `[[REVOGADO: ...]]` |
| `texto_planalto` | Texto integral, paginado |
| `artigo_camara` | Um artigo na compilação da Câmara (`Current`) ou na publicação original (`Original`) |
| `metadados_norma` | Ficha da norma: URN, apelidos, ementa, versões, normas revogadas, publicações e alterações posteriores |
| `alteracoes_artigo` | Alterações e revogações registradas pelo Senado para um artigo |
| `conferir_vigencia` | Cruza as três fontes, compara as redações e aponta divergências |

Toda resposta traz `fonte`, `url`, `consultado_em` (data e hora UTC) e `origem` (`ao vivo` ou `cache`). As respostas do Portal da Legislação trazem também `portal` (`Novo Portal da Legislação` ou `clássico (reserva)`), `url_artigo` (endereço do dispositivo com a âncora do portal novo, por exemplo `#art48`), `url_classico` e, quando lidas no portal novo, `urn_lexml` e a ficha `ato` (nome, ementa, data e link do LexML).

### Identificação da norma

Informe `tipo`, `numero` e `ano`, por exemplo `lei`, `13105`, `2015`. Tipos aceitos: `lei`, `lei_complementar` (ou `lc`), `decreto_lei` (ou `dl`), `decreto`, `medida_provisoria` (ou `mp`), `constituicao` (ou `cf`) e `emenda_constitucional` (ou `ec`). Você também pode passar a `url` do portal novo ou do Planalto (as duas são lidas primeiro no portal novo) ou a `urn` LexML.

O artigo aceita os formatos `"319"`, `"1.015"`, `"12-A"` e `"5º"`.

## Instalação

Requer Python 3.10 ou superior.

### Com `uv` (recomendado)

```bash
uvx --from git+https://github.com/wall-e-assessor/mcp-legislacao-br mcp-legislacao-br
```

### Com `pip`

```bash
pip install git+https://github.com/wall-e-assessor/mcp-legislacao-br
```

## Configuração no Claude Desktop

Edite o `claude_desktop_config.json`. No Windows ele fica em `%APPDATA%\Claude\claude_desktop_config.json`; no macOS, em `~/Library/Application Support/Claude/claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "legislacao-br": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/wall-e-assessor/mcp-legislacao-br", "mcp-legislacao-br"]
    }
  }
}
```

Se instalou com `pip`, use `"command": "mcp-legislacao-br"` sem `args`. Reinicie o Claude Desktop depois de salvar.

Outros clientes MCP (Claude Code, Cursor, VS Code e afins) aceitam o mesmo comando via `stdio`. No Claude Code:

```bash
claude mcp add legislacao-br -- uvx --from git+https://github.com/wall-e-assessor/mcp-legislacao-br mcp-legislacao-br
```

## Configuração opcional (variáveis de ambiente)

| Variável | Padrão | Efeito |
|---|---|---|
| `LEGISLACAO_TENTATIVAS` | `3` | Tentativas por requisição |
| `LEGISLACAO_TIMEOUT_CONEXAO` | `15` | Segundos para conectar |
| `LEGISLACAO_TIMEOUT_LEITURA` | `60` | Segundos para receber a página |
| `LEGISLACAO_CACHE_HORAS` | `24` | Validade do cache local |
| `LEGISLACAO_CACHE_DIR` | `%LOCALAPPDATA%\mcp-legislacao-br\cache` ou `~/.cache/mcp-legislacao-br` | Pasta do cache |

`conferir_vigencia` consulta sempre ao vivo. Se a fonte falhar, as ferramentas devolvem a última versão em cache com um `aviso` e a data da obtenção. Sem cache, devolvem um `marcador` de fonte indisponível.

## Como o texto vigente é obtido

O portal novo marca a redação revogada ou substituída com `<del>` e o clássico com `<strike>`; as duas aparecem **tachadas**. No portal novo, só o corpo do ato é lido, para que o sumário lateral não se confunda com os artigos. O servidor separa esses trechos, inclusive os tachados no meio de um parágrafo, e devolve como `texto_vigente` só o que não está tachado. As notas de redação, como "(Redação dada pela Lei nº ...)", são preservadas.

`conferir_vigencia` compara a redação do Portal da Legislação com a da Câmara, desconsiderando acentos, pontuação, ordinais (`1º`/`1o`) e notas de redação. Qualquer diferença aparece como **DIVERGÊNCIA**.

## Limitações

- O texto das fontes é compilado e não substitui o publicado no Diário Oficial da União.
- A URL é montada pelos padrões de endereço do portal (os mesmos no novo e no clássico) e conferida pelo número da norma na página. Normas com endereço fora do padrão exigem o parâmetro `url`.
- O formato HTML das fontes pode mudar sem aviso. Abra uma *issue* se algum artigo não for localizado.
- A conferência é automatizada e não substitui a leitura jurídica.

## Uso responsável

O servidor faz consultas pontuais, sob demanda, identifica-se no `User-Agent` e guarda cache local para não repetir downloads. Não o use para raspagem em massa das fontes.

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest
```

## Licença

[MIT](LICENSE) © 2026 Hudson Travassos
