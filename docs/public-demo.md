# Demonstração pública

A página inicial é um centro de operações responsivo com três fluxos executados de verdade no backend. Cada passo é uma requisição real à API, não uma animação. Os dados são fictícios, nada é gravado no PostgreSQL e não há pagamentos nem ERP externo.

## Automação entre sistemas

**Ver automação em ação** abre uma execução de seis etapas: extrair o PDF, consultar uma conta a pagar no ERP de origem, conferir o valor, criar o lançamento no ERP de destino, consultar novamente o lançamento e concluir a auditoria.

- Cada etapa exige a versão esperada; reenvios concorrentes da mesma versão não avançam duas vezes.
- A segunda execução na mesma sessão bloqueia o lançamento duplicado e conserva o protocolo original.
- Os dois ERPs são adaptadores simulados dentro do processo Python.

## Central de execuções e revisão humana

| Cenário | O que acontece |
| --- | --- |
| **Sucesso** | Extrai a nota 42, confere R$ 123,45, registra no destino e confirma o protocolo. |
| **Divergência** | Extrai a nota 43 (R$ 123,45) e compara com R$ 150,00 na origem. O fluxo para antes do lançamento; o visitante corrige a origem e aprova, ou rejeita. Justificativa de 10 a 300 caracteres fica na auditoria. |
| **Duplicidade** | Após o sucesso, reenvia a nota 42 e bloqueia um novo registro, conservando o protocolo original. |

A central lista as execuções da sessão, permite consultar evidências, revisar pendências, retomar execuções e baixar a auditoria em JSON. Os indicadores contam resultados reais da sessão; o histórico de exemplos é identificado como ilustrativo.

Rotas (`X-Demo-Session` UUID):

- `GET /demo/automation/summary`
- `POST /demo/automation/runs?scenario=success|divergence|duplicate`
- `POST /demo/automation/runs/{id}/advance?expected_step=N`
- `POST /demo/automation/runs/{id}/review` — `action`, `expected_step`, `reason` e, para aprovar, `corrected_source_amount` igual ao valor da nota

## Conciliação em lote e relatórios

**Executar demonstração completa** processa cinco entradas:

- notas 101 e 104 conciliadas e confirmadas;
- nota 102 com valor divergente;
- reenvio da nota 101 bloqueado como duplicidade;
- nota 103 sem correspondência no extrato;
- a nota 999 do extrato, sem documento, aparece como pendência de conciliação.

O valor confirmado inicial é R$ 211,10; a duplicidade não entra na soma.

Também é possível enviar de um a seis PDFs do [pacote de exemplos](../backend/app/static/batch-samples) com um CSV UTF-8 de cabeçalho exato `cnpj,numero,serie,valor` (valores positivos com ponto e duas casas, uma linha por nota). Documentos que não pertencem ao pacote são recusados individualmente.

- Cada avanço processa um documento: extração real do PDF, comparação por CNPJ/número/série, verificação de valor e confirmação no destino simulado. Uma falha não impede os demais.
- Um UUID de envio torna a criação idempotente; reutilizá-lo com outros arquivos retorna `409`.
- Divergências aceitam correção da origem com justificativa, ou rejeição. Sem correspondência, a aprovação é bloqueada. Decisões concorrentes têm um único efeito.
- Relatórios CSV e JSON trazem resultado por documento, valores, protocolos e auditoria. O CSV neutraliza células que poderiam ser interpretadas como fórmulas.

Rotas sob `/demo/batches` (`X-Demo-Session` UUID, exceto o ZIP): `GET /samples.zip`, `POST /example?request_id=UUID`, `POST /` (multipart), `GET /summary`, `GET /{id}`, `POST /{id}/advance?expected_version=N`, `POST /{id}/items/{item_id}/review`, `GET /{id}/report?format=csv|json`.

Os PDFs podem ser regenerados com `python scripts/create_batch_samples.py`.

## Limites

| Recurso | Limite |
| --- | --- |
| Sessões ativas | 128 (novas sessões recebem `429`, sem expulsar as ativas) |
| TTL da sessão | 15 minutos desde a criação |
| Execuções por sessão | 5 |
| Lotes por sessão | 2, com até 6 documentos |
| PDF / extrato / corpo multipart | 64 KB / 16 KB e 50 linhas / 128 KB |

O estado é volátil e por processo: exige um único worker HTTP (como no Render) e some ao reiniciar o serviço.
