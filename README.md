# mcp-legislacao-br

Servidor [MCP](https://modelcontextprotocol.io) para consultar **legislação federal brasileira em fontes oficiais** e conferir a vigência de dispositivos, artigo por artigo:

| Fonte | O que entrega |
|---|---|
| **Planalto** (Presidência da República) | Texto compilado, com a redação revogada (tachada) separada da vigente |
| **Câmara dos Deputados** | Compilação monovigente (via normas.leg.br) e páginas do Legin |
| **Senado Federal** | Busca no catálogo de normas, publicações no DOU e alterações registradas por dispositivo |

## Por que rodar localmente

O portal do Planalto bloqueia requisições vindas de servidores em nuvem (devolve "Acesso Negado"). Rodando no seu computador, o servidor acessa as fontes pela sua própria conexão, como um navegador comum. Ele também baixa só o documento principal, sem imagens nem scripts, e por isso não trava quando um arquivo auxiliar do portal demora.

## Ferramentas

| Ferramenta | Uso |
|---|---|
| `buscar_legislacao` | Busca por número, apelido ("Código de Processo Civil") ou ementa |
| `artigo_planalto` | Um artigo no Planalto: caput, parágrafos, incisos e alíneas, só com a redação vigente ou também com a revogada marcada como `[[REVOGADO: ...]]` |
| `texto_planalto` | Texto integral, paginado |
| `artigo_camara` | Um artigo na compilação da Câmara (`Current`) ou na publicação original (`Original`) |
| `metadados_norma` | Ficha da norma: URN, apelidos, ementa, versões, normas revogadas, publicações e alterações posteriores |
| `alteracoes_artigo` | Alterações e revogações registradas pelo Senado para um artigo |
| `conferir_vigencia` | Cruza as três fontes, compara as redações e aponta divergências |

Toda resposta traz `fonte`, `url`, `consultado_em` (data e hora UTC) e `origem` (`ao vivo` ou `cache`).

### Identificação da norma

Informe `tipo`, `numero` e `ano`, por exemplo `lei`, `13105`, `2015`. Tipos aceitos: `lei`, `lei_complementar` (ou `lc`), `decreto_lei` (ou `dl`), `decreto`, `medida_provisoria` (ou `mp`), `constituicao` (ou `cf`) e `emenda_constitucional` (ou `ec`). Você também pode passar a `url` do Planalto ou a `urn` LexML.

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

O Planalto exibe a redação revogada ou substituída **tachada** (`<strike>`). O servidor separa esses trechos, inclusive os tachados no meio de um parágrafo, e devolve como `texto_vigente` só o que não está tachado. As notas de redação, como "(Redação dada pela Lei nº ...)", são preservadas.

`conferir_vigencia` compara a redação do Planalto com a da Câmara, desconsiderando acentos, pontuação, ordinais (`1º`/`1o`) e notas de redação. Qualquer diferença aparece como **DIVERGÊNCIA**.

## Limitações

- O texto das fontes é compilado e não substitui o publicado no Diário Oficial da União.
- A URL do Planalto é montada pelos padrões de endereço do portal e conferida pelo número da norma na página. Normas com endereço fora do padrão exigem o parâmetro `url`.
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
