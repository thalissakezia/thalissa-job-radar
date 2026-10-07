# Thalissa Job Radar

Radar automático de vagas criado para reduzir repetição, separar **vaga publicada** de **vaga encontrada** e deixar a IA fora da etapa de coleta.

## Versão 0.1

A primeira versão coleta vagas em duas frentes:

- **FreeHire**: vagas de tecnologia/dados vindas de ATS e páginas de empresas.
- **Gupy**: busca no portal público da Gupy.

Depois o programa:

1. normaliza as vagas;
2. elimina duplicatas entre buscas e fontes;
3. usa SQLite durante a execução;
4. mantém um histórico persistente em `data/seen_jobs.json`;
5. aplica regras objetivas de localização, senioridade e aderência;
6. grava apenas as novidades em `reports/latest.md`.

A coleta é agendada no GitHub Actions para **08h, 11h e 16h (horário de Brasília)** e também pode ser executada manualmente.

## O que ainda não entrou

- LinkedIn/Indeed via JobSpy;
- leitura de posts do feed do LinkedIn;
- classificação final por IA;
- notificação por e-mail/Telegram/ChatGPT;
- candidatura automática.

Essas partes entram somente depois de validarmos se as fontes atuais estão trazendo vagas reais e recentes de forma estável.

## Segurança

Nenhuma senha, cookie, token do LinkedIn ou dado pessoal é necessário nesta versão. Não coloque credenciais diretamente no código.

## Arquivos principais

- `config/search.json` — termos e filtros.
- `radar/sources.py` — coletores.
- `radar/scoring.py` — regras de aderência.
- `radar/store.py` — histórico/deduplicação.
- `run.py` — orquestração.
- `reports/latest.md` — resultado mais recente.
- `.github/workflows/radar.yml` — execução automática.

## Estado

**MVP em construção.** A primeira execução real deve ser validada antes de usar o relatório como fonte única para candidaturas.
