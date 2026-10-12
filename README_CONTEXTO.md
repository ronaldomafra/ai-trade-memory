# Pacote de contexto para agente de desenvolvimento

Este pacote contém a especificação **da POC a ser implementada**, não a POC já pronta.

## Arquivos
- `AGENTS.md`: instruções curtas que devem ser lidas pelo agente automaticamente.
- `docs/SPEC.md`: especificação completa, regras, arquitetura, persistência,
  integração OpenRouter/JEV, aprendizado, etapas e critérios de aceite.

## Uso
1. Copie o conteúdo do pacote para a raiz de um repositório Python vazio.
2. Inicie o Codex ou Claude Code na raiz desse repositório.
3. Instrua-o a ler `AGENTS.md` e implementar o projeto conforme `docs/SPEC.md`,
   pelo plano E00–E11, executando testes e atualizando docs/STATUS_DESENVOLVIMENTO.md a cada etapa.
4. Forneça `OPENROUTER_API_KEY` **somente no ambiente local quando necessário**.
5. A POC não deve conter credenciais de exchange nem enviar ordens reais.

Desenho vigente D051/D052/SPEC 1.50: consultar docs/PLANO_DESENVOLVIMENTO_V1.md,
docs/STATUS_DESENVOLVIMENTO.md e docs/ESCOPO_POC_V1.md. Após Marcos 1–5,
integrar transferência automática, REST/WSS/token/2FA e TUI remota; lifecycle no servidor.
A futura interface HTML está fora do escopo; a implementação deve exportar
JSON/CSV e manter eventos JSONL e SQLite para esse trabalho posterior.

## Guia para execução completa

[PLANO_DESENVOLVIMENTO_V1.md](docs/PLANO_DESENVOLVIMENTO_V1.md) define a ordem, dependências, módulos, testes e aceite. [TRANSFERENCIA_APRENDIZADO.md](docs/TRANSFERENCIA_APRENDIZADO.md) especifica a camada estrangeira de C. Não declarar implementação ou homologação pela existência destes documentos.
