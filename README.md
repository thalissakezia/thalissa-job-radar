# Thalissa Job Radar

Radar automático de vagas para encontrar oportunidades novas sem repetir resultados antigos.

## Fontes atuais

- **Gupy** — portal público atual, lido diretamente da página de busca.
- **FreeHire** — agregador de ATS e páginas de empresas.
- **JobSpy** — busca recente no **LinkedIn Jobs** e **Indeed Brasil**.

O JobSpy roda sem login do LinkedIn. No LinkedIn, o radar faz uma passagem priorizando **Easy Apply** e outra geral. Como o próprio JobSpy informa que LinkedIn é a fonte mais restritiva, falhas/rate limit aparecem na seção **Saúde das fontes** e não derrubam as outras buscas.

## Regras já aplicadas

- remoto/remoto em português e `remote` em inglês são tratados como a mesma modalidade;
- Indeed usa explicitamente **Brazil**;
- valores `R$`, `BRL`, real/reais são normalizados para **BRL** e exibidos como **R$**;
- vagas presenciais/híbridas fora das cidades permitidas são descartadas;
- títulos de pleno/sênior/liderança são descartados;
- Easy Apply recebe prioridade adicional;
- e-mail encontrado no anúncio é preservado;
- links diretos de candidatura são preservados quando a fonte fornece;
- histórico impede a mesma vaga de reaparecer como novidade.

## Agenda

GitHub Actions executa o radar às **08h, 11h e 16h (horário de Brasília)**. O JobSpy olha uma janela de 30 horas para tolerar eventuais falhas de uma execução, mas o histórico faz com que uma vaga já vista não volte como nova.

## Arquivos principais

- `config/search.json` — termos, janelas e locais.
- `radar/sources.py` — Gupy, FreeHire e JobSpy.
- `radar/scoring.py` — filtro e pontuação.
- `radar/store.py` — histórico/deduplicação.
- `run.py` — relatório.
- `reports/latest.md` — novidades da última execução.
- `.github/workflows/radar.yml` — agendamento.

## Próximas camadas

- comparação requisito por requisito com o currículo;
- leitura de posts públicos/recrutadores do LinkedIn separada da aba Jobs;
- entrega das vagas filtradas no ChatGPT e por e-mail;
- melhorias de ranking após validar falsos positivos/negativos.

Nenhuma candidatura é enviada automaticamente.
