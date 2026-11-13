# API privada

Todas as rotas abaixo exigem sessão individual (cookie + `X-CSRF-Token` nas escritas) ou `X-API-Key` para o acervo legado. Cada usuário enxerga apenas as próprias notas, documentos e execuções.

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/invoices` | Cadastro JSON de nota |
| `POST` | `/api/v1/invoices/upload` | Upload de PDF com extração síncrona |
| `GET` | `/api/v1/invoices` | Lista paginada (`limit`, `offset`) |
| `GET` | `/api/v1/invoices/{id}/events` | Trilha de auditoria da nota |
| `POST` | `/api/v1/executions` | Upload assíncrono; retorna `202` e o ID da execução |
| `GET` | `/api/v1/executions` | Lista de execuções |
| `GET` | `/api/v1/executions/{id}` | Status de uma execução |
| `GET` | `/health`, `/ready` | Liveness e readiness (banco + migração) |

## Validações

- CNPJ com dígitos verificadores, número e série numéricos e normalizados, valor positivo com até duas casas.
- Deduplicação no banco por emitente, número e série (por usuário) e pelo SHA-256 do documento.
- Repetição retorna `409` sem novos efeitos.

## Formato do PDF

Use [`examples/nota-ficticia.pdf`](../examples/nota-ficticia.pdf) no Swagger. O extrator aceita somente o layout fictício do projeto, com cada campo uma única vez em sua própria linha:

```text
CNPJ emitente: 12.345.678/0001-95
Numero: 42
Serie: 1
Valor total: 123.45
```

- Até 5 MiB e 10 páginas, sem senha, com texto selecionável.
- O parser não interpreta DANFE/NFS-e e não tem OCR ou IA.
- O original e o SHA-256 ficam no banco; nomes enviados não são usados como caminhos.
- O corpo é limitado antes do parser multipart (5 MiB + 64 KiB) e o recebimento a 30 segundos (15 segundos sem dados).

## Fila assíncrona

O comportamento de reserva, tentativas e recuperação está descrito em [fila e concorrência](queue.md).
