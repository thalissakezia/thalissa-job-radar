# Fontes e dependências de terceiros

- **FreeHire** — https://github.com/strelov1/freehire — MIT. O radar usa a API pública do projeto.
- **JobSpy / python-jobspy 1.2.0** — https://github.com/speedyapply/JobSpy — MIT. Dependência instalada para coletar LinkedIn Jobs e Indeed Brasil.
- **Gupy** — o radar lê dados públicos embutidos no HTML da página de busca atual. O endpoint JSON antigo do portal deixou de responder em outubro de 2026.

## Observações operacionais

O JobSpy documenta que o LinkedIn é mais restritivo e pode aplicar rate limit. O radar não usa login, senha, cookie nem token pessoal do LinkedIn. Se o LinkedIn bloquear uma execução, a falha fica registrada em **Saúde das fontes** e Gupy/FreeHire/Indeed continuam funcionando.

A estrutura de páginas e endpoints públicos pode mudar; por isso cada fonte tem diagnóstico explícito em vez de falhar silenciosamente.
