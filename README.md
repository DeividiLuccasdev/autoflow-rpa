# AutoFlow RPA

Plataforma de portfólio para automação financeira com documentos e empresas fictícios.

## Implementado

FastAPI com cadastro JSON e upload de PDF, validação determinística de CNPJ/valores, deduplicação no banco, auditoria e execução assíncrona Celery/Redis. PostgreSQL no Docker; SQLite para desenvolvimento local e testes rápidos. Migrações Alembic substituem create_all no início da API.

## Rodar localmente

Na pasta backend, com Python 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app --env-file ../.env --reload
```

O arquivo .env da raiz já foi gerado localmente com uma chave aleatória e está ignorado pelo Git. Em outra máquina, gere-o na raiz do projeto:

```powershell
python -c "import secrets; from pathlib import Path; p=Path('.env'); assert not p.exists(), 'Arquivo ja existe'; p.write_text('AUTOFLOW_API_KEY='+secrets.token_hex(32)+'\n', encoding='utf-8')"
```

Abra http://localhost:8000/docs e use **Authorize** para informar a chave AUTOFLOW_API_KEY do arquivo .env. Todas as rotas /api/v1 exigem X-API-Key; health e documentação são públicos. Sem chave configurada, as rotas protegidas retornam 503. Credencial inválida retorna 401. Essa é uma credencial única de operador para demonstração: não há usuários individuais, RBAC ou isolamento por empresa. A auditoria distingue local-operator, worker e legacy-unknown; isso não identifica uma pessoa.

## Docker

Com Docker Desktop em modo Linux e o .env configurado:

```powershell
docker compose up --build -d
docker compose run --rm api python -m pytest -q
docker compose down
```

O serviço migrate aplica Alembic antes da API. API, worker e scheduler rodam juntos; sem worker/Redis, o endpoint de execuções aceita o arquivo e permanece em queued. Banco e Redis não expõem portas no host; API usa apenas 127.0.0.1:8000. A senha PostgreSQL do Compose é exclusiva da demonstração local. Containers da aplicação executam com usuário sem privilégios; API/worker têm limites de CPU e memória.

## Banco antigo

A migração do SQLite desta sessão foi aplicada, com backup fora dos entregáveis. Para outro banco criado pelo MVP anterior, faça backup e confira o schema antes de usar `alembic stamp 0001` seguido de `alembic upgrade head`. Não use stamp em banco desconhecido ou vazio. Em banco novo, use somente upgrade head. Não inicie múltiplos processos de migração simultaneamente.

## Experimentar

- POST /api/v1/invoices: cadastro JSON.
- POST /api/v1/invoices/upload: extração síncrona do PDF.
- GET /api/v1/invoices: lista paginada.
- GET /api/v1/invoices/{id}/events: auditoria.
- POST /api/v1/executions: upload assíncrono, retorna 202 e ID.
- GET /api/v1/executions e GET /api/v1/executions/{id}: acompanhamento.

Use examples/nota-ficticia.pdf no Swagger. A extração aceita somente o layout fictício com cada campo uma única vez em sua própria linha:

```text
CNPJ emitente: 12.345.678/0001-95
Numero: 42
Serie: 1
Valor total: 123.45
```

PDF até 5 MiB e 10 páginas, sem senha, com texto selecionável. Parser não interpreta DANFE/NFS-e e não possui OCR/IA. O original e SHA-256 ficam no banco; nomes enviados não são caminhos. A aplicação limita o corpo antes do parser multipart a 5 MiB + 64 KiB de overhead e o recebimento a 30 segundos (15 segundos sem dados). Limites de publicação e taxa ainda precisam de proxy/controle próprio antes de expor o sistema.

## Concorrência e recuperação

O banco persiste a execução antes da publicação. O dispatcher reserva atomicamente uma janela antes de enviar ao Redis; dois dispatchers não reservam a mesma janela. A cada reserva, incrementa dispatch_attempts. A espera cresce: 60, 120, 240, 480 e 960 segundos. Após cinco reservas sem conclusão, a execução vira failed quando a última janela expira. Esse orçamento inclui falhas de publicação e mensagens que não chegaram ao worker; não é contador de processamentos bem-sucedidos. Não há reenvio manual de estados terminais.

Beat agenda a varredura a cada 10 segundos; cada varredura considera até 100 pendências. Quedas entre reserva e publicação são recuperadas após a janela. Entrega duplicada ainda é possível em sistemas distribuídos: worker faz UPDATE condicional e grava todos os efeitos locais em uma transação. Uma falha desfaz a gravação e libera a tarefa para nova tentativa. Restrições únicas garantem a identidade da nota e do documento. Apenas erros da restrição de duplicidade conhecida recebem esse tratamento; demais erros são falhas.

Estados: queued, completed, needs_review, duplicate e failed. processing ocorre dentro da transação e não é progresso persistido visível. Worker tem timeout de 30 segundos suave e 45 segundos forçado em Linux. Mensagens antigas podem ser reenviadas, mas estados terminais impedem repetir os efeitos. Essas garantias cobrem o banco local, não operações em ERP externo. Reservas não são uma promessa de execução exatamente uma vez.

## Testes

Execute na pasta backend:

```powershell
.venv\Scripts\python -m pytest -q
```

Os testes de concorrência exigem TEST_POSTGRES_URL apontando para um banco de testes. Criam e removem apenas schemas isolados com nomes aleatórios test_*. Não aponte para banco de produção. O workflow GitHub Actions fornece PostgreSQL e executa esses testes. Casos: upload simultâneo do mesmo documento, dois workers na mesma execução, documentos distintos da mesma nota e dois dispatchers concorrentes.

Verificação em 01/11/2026: 40 testes passaram, sem skips, usando SQLite e uma instância temporária PostgreSQL 18. Migrações foram verificadas nos dois bancos; o SQLite local foi atualizado até 0003. pip check e validação do Compose passaram. Docker/Redis/Celery ainda não foram executados juntos neste ambiente. Existe um aviso de depreciação no adaptador de testes Starlette/httpx, sem falhas de teste.

## Integração contínua

O workflow `.github/workflows/ci.yml` executa testes com PostgreSQL, verifica dependências e, após os testes passarem, constrói a imagem Docker. Dispara por push, pull request ou manualmente. Usa permissões de leitura, limite de duração e cancelamento de execuções substituídas. Não publica imagens nem faz deploy: CD continua pendente da escolha do ambiente de hospedagem. A primeira execução no GitHub precisa ser confirmada depois do envio do código.

## Próximos passos

Validar integração real Redis/Celery, adicionar reenvio operacional autorizado e métricas de falha. Depois, criar ERPs simulados e confirmar cada ação externa antes de repetir. Frontend Next.js, usuários individuais/permissões, OCR e IA continuam pendentes. Este incremento permanece destinado ao ambiente local com dados fictícios.

## Interface para recrutadores

A página inicial agora apresenta um dashboard responsivo, com visual escuro, filtros, busca, detalhes de validação e demonstração pública. Os indicadores e registros iniciais são ilustrativos e estão identificados na interface. O PDF sintético fornecido em /demo/sample é o único documento aceito em /demo/analyze: a comparação de SHA-256 acontece antes da extração. A resposta usa o extrator real, mas não grava notas ou documentos no banco. Histórico da demonstração é mantido na sessão do navegador. As rotas /api/v1 continuam exigindo chave. A interface desta entrega usa HTML, CSS e JavaScript servidos pelo FastAPI; Next.js permanece no roadmap. O repositório GitHub permanece privado.

## Automação demonstrativa entre sistemas

O botão Ver automação em ação abre uma execução de seis etapas no backend: extrair PDF, consultar uma conta a pagar fixa, conferir o valor, criar um lançamento no adaptador de destino, consultar novamente esse lançamento e concluir os eventos de auditoria. Cada etapa exige uma requisição à API com a versão esperada; reenvios concorrentes da mesma versão não avançam duas vezes. A segunda execução na mesma sessão bloqueia o lançamento duplicado e conserva o protocolo original.

Os dois ERPs são adaptadores simulados dentro do processo Python, não serviços empresariais externos. O estado fica somente em memória por até 15 minutos, limitado a 128 sessões e cinco execuções por sessão. Sessões antigas podem ser removidas ao atingir o limite; reiniciar o processo apaga a demonstração. Não há pagamentos, dados reais ou gravação no PostgreSQL nesse fluxo público. O lock é por processo e este modo exige um único worker HTTP, como já configurado no Render. A interface adiciona o resultado ao histórico da sessão e apresenta eventos com horários e protocolo. A pausa visual entre etapas apenas facilita a leitura dos resultados já executados. Automação de navegador com Playwright continua pendente.

## Robô Playwright

A próxima etapa está implementada como módulo opcional local/CI: [instruções do RPA](docs/rpa-browser.md). Inclui ERP fictício com formulário, preenchimento e salvamento por navegador real, confirmação após recarregar a página, prevenção de duplicidade, screenshots, vídeo e trace. A execução pública gratuita continua usando o fluxo demonstrativo de backend; não executa Chromium no Render.
