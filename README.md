# Thalissa Job Radar

Radar automático de vagas para encontrar oportunidades novas sem repetir resultados antigos e escolher o currículo mais adequado para cada oportunidade.

## Fontes atuais

- **Gupy**
- **FreeHire**
- **LinkedIn Jobs via JobSpy**
- **Indeed Brasil via JobSpy**

## Comparação com currículo

O radar possui três perfis estruturados, sem telefone/e-mail ou outros dados pessoais no código público:

- **BI / Dados**
- **Suporte / Atendimento**
- **Administrativo / Operações**

Para cada vaga aprovada pelos filtros, o sistema escolhe o perfil mais aderente e calcula uma **compatibilidade estimada**. O relatório mostra:

- percentual de compatibilidade;
- nível de confiança (alta, média ou baixa);
- currículo recomendado;
- pontos atendidos;
- possíveis lacunas;
- recomendação: **VALE CANDIDATAR**, **PODE VALER**, **REVISAR** ou **REVISAR DESCRIÇÃO**.

Quando a fonte não fornece a descrição completa, o sistema limita a pontuação e mostra confiança baixa, evitando inventar uma precisão que os dados não permitem.

## Regras atuais

- remoto/home office: **sem salário mínimo**;
- CLT, PJ, estágio e trainee: **todos aceitos**;
- `remote` e `remoto` são tratados como a mesma modalidade;
- salário brasileiro é normalizado para **BRL / R$**;
- presenciais/híbridas fora das cidades configuradas são descartadas;
- pleno/sênior/liderança são descartados;
- Easy Apply e contato por e-mail recebem prioridade no ranking operacional;
- histórico evita repetir a mesma vaga como novidade.

## Agenda

GitHub Actions executa às **08h, 11h e 16h (horário de Brasília)**.

## Relatórios

- `reports/latest.md` — somente vagas novas desde o histórico anterior.
- `reports/current_matches.md` — ranking atual das vagas compatíveis coletadas, inclusive as já vistas, útil para validar o sistema.

## Próximas camadas

- leitura separada de posts públicos/recrutadores do LinkedIn;
- entrega automática dos resultados no ChatGPT e por e-mail;
- calibração contínua do ranking com base em vagas boas/ruins marcadas pelo usuário.

Nenhuma candidatura é enviada automaticamente.
