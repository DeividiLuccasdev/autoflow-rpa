# Fila, concorrência e recuperação

A fila é durável no banco; o Redis recebe somente identificadores de execução.

## Estados

`queued` → `completed` | `needs_review` | `duplicate` | `failed`

`processing` existe apenas dentro da transação do worker e não é um progresso persistido visível.

## Publicação (dispatcher)

- A execução é persistida antes de qualquer publicação.
- O dispatcher reserva atomicamente uma janela antes de enviar ao Redis; dois dispatchers não reservam a mesma janela.
- Cada reserva incrementa `dispatch_attempts`. A espera cresce exponencialmente: 60, 120, 240, 480 e 960 segundos.
- Após cinco reservas sem conclusão, a execução vira `failed` quando a última janela expira. Esse orçamento inclui falhas de publicação e mensagens que não chegaram ao worker.
- O beat agenda a varredura a cada 10 segundos; cada varredura considera até 100 pendências. Quedas entre reserva e publicação são recuperadas após a janela.
- Não há reenvio manual de estados terminais.

## Processamento (worker)

- O worker faz um `UPDATE` condicional (`status = 'queued'`) e grava todos os efeitos locais na mesma transação. Entregas duplicadas resultam em um único efeito.
- Uma falha desfaz a gravação e libera a tarefa para nova tentativa.
- Restrições únicas garantem a identidade da nota e do documento. Apenas a restrição de duplicidade conhecida vira `duplicate` (SQLSTATE e nome da constraint no PostgreSQL); demais erros são falhas.
- Timeout de 30 segundos (suave) e 45 segundos (forçado) em Linux; `acks_late` e `reject_on_worker_lost` ativados.

## Garantias e limites

Mensagens antigas podem ser reentregues, mas estados terminais impedem repetir os efeitos. Essas garantias cobrem o banco local, não operações em ERP externo. Reservas não são uma promessa de execução exatamente uma vez.

Os cenários cobertos por testes com PostgreSQL, Redis e Celery reais incluem upload simultâneo do mesmo documento, dois workers na mesma execução, documentos distintos da mesma nota, dois dispatchers concorrentes, Redis indisponível e tentativas esgotadas. Detalhes em [request specs](request-specs.md).
