# TUI V1 — contrato de desenvolvimento

**D051/D052 · SPEC 1.50/15.4.** Textual local/remota após núcleo/transferência/API. Ainda não implementada.
[Plano E10](PLANO_DESENVOLVIMENTO_V1.md) · [Arquitetura](ARQUITETURA.md).

## Referência

![Referência visual preservada](referencias/tui-dashboard-referencia.png)

Imagem intacta; fundo escuro/bordas/ciano/verde/teclado adaptados ao terminal. Valores/mecanismos ilustrados não substituem SPEC, capital ou aprendizado.

## Fluxos

1. Endereço do core, login/senha/2FA e conexão HTTPS/WSS remota.
2. Listar/selecionar sessões e saúde; nova ou restaurar run_id.
3. Nova: perfil/par/template/ajustes permitidos/dataset opcional/transferência antes de iniciar; backend valida/importa/persiste.
4. Restaurar: estado/configuração/capital/posições/memória/travas/ciclos; sem reset/reimport/retrotrade.
5. Dashboard/atalhos/filtros/import-export/ajuda, com sair/logout mantendo motores.

REST para comandos/consultas/dataset; WS para eventos/etapas observáveis/preços/decisões. Lifecycle Docker fica no servidor. TUI sem DB/broker/daemon, edição intrassessão ou modo real.

## Dashboard

| Área | Conteúdo |
| --- | --- |
| Cabeçalho | Sessão/par/perfil/intervalo, PAPER ONLY, conexão/saúde/horário. |
| Esquerda | Carteira: patrimônio/caixa/ativo/PnL/retorno/drawdown/trades fechados. |
| Centro | Candles/preço e curvas A/B/C por carteira. |
| Direita | Posições/fills, proposta/validação/execução/motivo, memória/custo. |
| Comparação | A técnica/B sem memória/C com memória local e/ou transferida. |
| Aprendizado | Fontes/destino/local-transferida/contagens/janela/validação/estado e motivo. |
| Rodapé | Processamento observável/eventos/cursor/filtros/atalhos. |

Layout adaptável/abas para terminal menor; testar legibilidade e resize. Não prometer reprodução pixel a pixel.

## Dados e comportamento

- 100 USDT por carteira; Decimal/string do motor, USD/custo IA unknown separado.
- Símbolo/quantidades dinâmicos, sem valores da imagem.
- Local >=30/50, 60d/três padrões totais; transferência com gates e origem explícita, inclusive VALIDATING/SUSPENDED.
- Confiança JEV, probabilidade de ação e taxa histórica são conceitos diferentes; BUY sugerido não é fill.
- Desconexão/estado antigo explícitos; snapshot/watermark/cursor/dedupe/replay.
- GET/renderização não chamam JEV/operam. Processo continua sem cliente.
- Tokens/segredos fora de logs; etapas do bot não são raciocínio interno do modelo.
- Ajuda usa [estratégias](ESTRATEGIAS.md)/SPEC, sem expor todo detalhe interno como configuração.

Testar login/2FA/read-only, criação/config/sem dataset/restore, duas sessões/pares, gráficos/resize, vazio/degradado, WS perdido/cursor, transferência e saída. [Textual](https://textual.textualize.io/) e [testes](https://textual.textualize.io/guide/testing/) sustentam escolha, não comprovam implementação.
