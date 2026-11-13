# AutoFlow RPA

Plataforma de portfólio para automação financeira com documentos e empresas fictícios.

A demonstração é pública. A [área privada](https://autoflow-rpa-api.onrender.com/workspace) oferece acesso por convite, sessões revogáveis e documentos separados por usuário. Veja [como emitir um convite e ativar uma conta](docs/accounts.md).

## Rodar todos os testes

Com Python e Docker Desktop funcionando, execute na raiz:

```powershell
python scripts/test_all.py
```

O ambiente é descartável, com PostgreSQL, Redis, Celery e Chromium reais. Nenhum banco de produção é usado. Falhas e testes pulados encerram o comando com erro. Veja os [comportamentos cobertos e detalhes do isolamento](docs/request-specs.md).

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

Abra http://localhost:8000/workspace para emitir convite, ativar uma conta e entrar. As rotas /api/v1 aceitam sessão individual com proteção CSRF nas escritas, ou X-API-Key para o acervo legado. No Swagger, **Authorize** informa essa chave operacional. Health e documentação são públicos. A auditoria de novas notas identifica o usuário; os marcadores local-operator, worker e legacy-unknown conservam seus significados operacionais. Não há RBAC de organizações nesta etapa.

## Docker

Com Docker Desktop em modo Linux e o .env configurado:

```powershell
docker compose up --build -d
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

Execute na raiz, em infraestrutura exclusiva de teste:

```powershell
python scripts/test_all.py
```

Os testes de concorrência exigem TEST_POSTGRES_URL apontando para um banco de testes. Criam e removem apenas schemas isolados com nomes aleatórios test_*. Não aponte para banco de produção. O workflow GitHub Actions fornece PostgreSQL e executa esses testes. Casos: upload simultâneo do mesmo documento, dois workers na mesma execução, documentos distintos da mesma nota e dois dispatchers concorrentes.

Resultados anteriores e detalhes do ambiente: [127 testes da primeira bateria](docs/test-results.md). A entrega de contas adiciona testes de autorização e usa a migração 0004. PostgreSQL, Redis, Celery e Chromium são executados no CI. Existe um aviso de depreciação no adaptador de testes Starlette/httpx.

## Integração contínua

O workflow `.github/workflows/ci.yml` executa testes completos com PostgreSQL, Redis, Celery e Chromium, audita dependências e constrói a imagem Docker. Dispara por push, pull request ou manualmente. O Render acompanha a branch main e está configurado para publicar após os checks passarem. O comando de início aplica as migrations antes de iniciar a API.

## Conciliação em lote e relatórios

O botão **Executar demonstração completa** processa cinco entradas fictícias no backend: notas 101 e 104 conciliadas e confirmadas, nota 102 com valor divergente, reenvio da nota 101 bloqueado e nota 103 sem correspondência. O extrato também contém a nota 999 sem documento, exibida como pendência de conciliação. O valor confirmado inicial é R$ 211,10; a duplicidade não entra novamente na soma.

O pacote ZIP público contém quatro PDFs sintéticos e `extrato.csv`. A interface aceita o envio manual de um a seis PDFs canônicos com um CSV UTF-8, limitado a 100 KB no total pelo cliente. No servidor, cada PDF tem limite de 64 KB, o extrato 16 KB/50 linhas e o corpo multipart público 128 KB. Documentos não fornecidos pelo projeto são recusados individualmente; não envie dados reais. O CSV tem cabeçalho exato `cnpj,numero,serie,valor`, valores positivos com ponto e duas casas decimais e uma única linha por identidade normalizada de nota.

Cada avanço processa um documento, com extração real do PDF, comparação por CNPJ/número/série, verificação do valor e confirmação em um adaptador de destino em memória. Uma falha em um documento não impede o processamento dos demais. A versão esperada protege reenvios e avanços concorrentes. Um UUID de envio torna a criação idempotente; reutilizá-lo com arquivos diferentes retorna conflito. A central permite retomar um lote após recarregar a página, enquanto a sessão continuar válida.

Depois do processamento, divergências de valor aceitam correção da origem simulada e aprovação com justificativa, ou rejeição. O valor original do extrato permanece na auditoria. Sem correspondência, a aprovação é bloqueada: rejeite ou envie um novo lote com o extrato corrigido. Decisões concorrentes têm um único efeito. Uma nova conciliação na mesma sessão não repete notas já confirmadas. A contabilidade dos lotes é separada da demonstração individual.

Relatórios CSV e JSON incluem resultado por documento, valores, protocolos e auditoria; linhas do extrato sem documento aparecem nos dois formatos. A exportação CSV neutraliza células que poderiam ser interpretadas como fórmulas. JSON preserva os eventos e timestamps. O valor confirmado soma apenas documentos registrados pelo lote atual; documentos de referência de outros lotes não são contados de novo.

Limites: dois lotes por sessão, seis documentos por lote, até 128 sessões ativas e TTL compartilhado de 15 minutos. O estado é volátil e requer o mesmo processo HTTP único da demonstração anterior. O fluxo público não usa Celery/Redis, não realiza pagamentos e não acessa um ERP externo. Cada passo é uma requisição real ao backend, não uma animação que inventa resultados. OCR, IA e Power Automate não foram adicionados nesta etapa.

Rotas sob `/demo/batches`, com `X-Demo-Session` UUID (exceto o ZIP):

- `GET /samples.zip`: exemplos fictícios.
- `POST /example?request_id=UUID`: lote completo pré-configurado.
- `POST /`: multipart `request_id`, `files` e `statement`.
- `GET /summary` e `GET /{id}`: acompanhamento.
- `POST /{id}/advance?expected_version=N`: processa um documento.
- `POST /{id}/items/{item_id}/review`: decisão com justificativa.
- `GET /{id}/report?format=csv|json`: exportação da conciliação e auditoria.

Os PDFs podem ser regenerados com `python scripts/create_batch_samples.py`.

## Assistente por R.E., voz e texto

### Nota e e-mail de cobrança fictício

Ao abrir uma nota autorizada, o botão **Gerar nota e enviar cobrança** executa uma única operação: gera o PDF conforme o perfil, preenche o e-mail e registra automaticamente um envio simulado. O remetente demonstrativo é `cobranca@cobranca.com`, o destinatário fictício informado é `empresa1@.com.br` (formato inválido para envio real), e o assunto é **Valores pendentes com nossa empresa**. A mensagem informa o número da nota, a razão social fictícia, o saldo devedor e o prazo adicional de dois dias corridos, com a nota em anexo.

Não há SMTP, API externa de e-mail nem transmissão da cobrança a terceiros. O PDF anexado e o protocolo ficam na sessão de até 20 minutos. Repetir a operação para a mesma nota na mesma sessão retorna o mesmo protocolo e os mesmos bytes do PDF, sem duplicar o registro de envio. Outro R.E. ou nova sessão não acessa esse histórico nem seus anexos. As mensagens são modelos fictícios de portfólio e não representam uma verificação real de vencimento ou cobrança.

Rotas: `POST /assistant/documents/{id}/collection` com corpo `{}` e CSRF; `GET /assistant/collections`; `GET /assistant/collections/{protocolo}/pdf`. Remetente, destinatário e texto são definidos no servidor; o cliente não pode sobrescrevê-los.

A captura usa uma instância nova após cada encerramento normal ou `no-speech`, com retomada após 250 ms, buffer de texto separado e identificação da sessão para ignorar eventos antigos. Não há limite de quatro dígitos ou três pausas. Após 90 segundos sem novos trechos, o microfone é parado e o texto fica disponível para retomada explícita. Falhas de rede, permissão ou acesso ao microfone exibem a causa e não reiniciam automaticamente. A interface mostra os dígitos efetivamente reconhecidos e sua quantidade; não infere zeros ausentes. Os testes incluem 11 dígitos com interrupção após o quarto, várias retomadas, eventos atrasados e confirmação final.

O acesso ao assistente aparece em destaque no topo da página inicial. A transcrição parcial atualiza o campo enquanto o navegador reconhece a fala, sem consultar a API para cada palavra. O reconhecimento é contínuo e mantém os trechos entre pausas. Uma consulta por voz só é enviada quando o comando termina com a palavra “consulte”, reconhecida como resultado final. Se o serviço encerrar normalmente a captura ou sinalizar ausência de fala, ela é retomada preservando o texto; outros erros e parada explícita interrompem essa retomada. Parar o microfone nunca executa a consulta. A digitação continua disponível com envio explícito pelo botão Consultar. Digitar durante a captura interrompe a transcrição para preservar a correção manual; o botão Consultar também pode enviar o texto visível. A interface exibe o andamento da consulta. Os testes de regressão simulam eventos de reconhecimento no Node.js, sem microfone; latência e disponibilidade reais do serviço de voz continuam dependendo do navegador e da conexão.

A página `/assistente` oferece uma simulação de acesso corporativo isolada das contas privadas. O funcionário digita R.E. e senha demonstrativos; depois pode falar ou digitar o mesmo comando. R.E. `05` é funcionário: consulta nota, valor devedor da nota e razão social fictícia completa. R.E. `10` é diretoria: recebe os mesmos campos, mais endereço e telefone fictícios, valor total da dívida e parcelas restantes. Ambos consultam as duas unidades demonstrativas. Campos exclusivos da diretoria são omitidos das respostas de busca, detalhes e PDF do funcionário, no servidor. O valor da nota e o saldo devedor da nota são distintos da dívida total do acordo demonstrativo; as parcelas restantes pertencem ao acordo dessa ficha. A senha pública é `AutoflowDemo2026!`. Todas as pessoas, identificadores e notas deste assistente são fictícios, sem valor fiscal. Esses acessos não autenticam funcionários de uma empresa real.

O backend aplica o escopo na busca, nos detalhes e no PDF, independentemente da interface. O cookie opaco é HttpOnly, SameSite Strict e Secure em HTTPS; POSTs autenticados exigem token CSRF. A sessão dura até 20 minutos, é revogável e volátil, com limite de 128 sessões e 100 eventos por sessão. A auditoria não armazena áudio nem a transcrição integral com CPF/CNPJ. A sessão do assistente não autoriza a API privada de documentos.

Buscas aceitam `nota 101`, CPF/CNPJ com pontuação, dígitos ditados individualmente e `listar minhas notas`. Identificadores incompletos não são preenchidos por inferência. Há comandos de contexto como `abrir a segunda nota`, `qual o valor`, `mostrar histórico`, `baixar PDF` e `sair`. O PDF é uma representação sintética dos campos da nota demonstrativa, não um documento fiscal recuperado de fonte externa.

O microfone usa SpeechRecognition/webkitSpeechRecognition em português do Brasil, somente após ação do usuário. Compatibilidade, permissão do microfone e serviço de transcrição dependem do navegador; a digitação permanece disponível. O navegador pode enviar áudio ao seu serviço de reconhecimento, conforme o aviso exibido. O aplicativo não captura áudio na entrada por R.E. e não grava áudio. A política de microfone é liberada somente na página `/assistente`; as demais páginas mantêm `microphone=()`.

Esta etapa não integra SSO, diretório corporativo, R.E.s reais, documentos privados existentes nem consulta governamental por CPF/CNPJ. Uma integração empresarial futura precisa associar o R.E. autenticado a permissões administradas e à fonte documental autorizada. Não use as credenciais públicas da simulação em produção.

Referência de reconhecimento de voz: https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API

## Evoluções futuras do ambiente completo

Adicionar recuperação de conta, métricas de falha e reenvio operacional autorizado. Integrações empresariais externas, organizações/RBAC, frontend Next.js, OCR e IA continuam pendentes. O produto permanece destinado a dados fictícios de portfólio.

## Central de execuções e revisão humana

A interface pública oferece três cenários com transições confirmadas no backend:

- **Sucesso:** extrai a nota fictícia 42, confere R$ 123,45, registra no adaptador de destino e confirma o protocolo.
- **Divergência:** extrai a nota fictícia 43, de R$ 123,45, e compara com R$ 150,00 na origem simulada. O fluxo para antes do lançamento. O visitante pode corrigir o valor da origem e aprovar, ou rejeitar. Uma justificativa de 10 a 300 caracteres é obrigatória e fica na auditoria.
- **Duplicidade:** exige um lançamento de referência. Após concluir o sucesso, reenvia a nota 42 e bloqueia um novo registro, conservando o protocolo original.

A central lista as execuções da sessão e permite consultar evidências, revisar pendências ou retomar uma execução interrompida. A auditoria pode ser baixada em JSON. Os indicadores contam conclusões, pendências e duplicidades reais da sessão demonstrativa; o valor registrado soma lançamentos únicos, e o tempo médio considera apenas execuções concluídas, incluindo espera por revisão. Sem conclusões, o tempo aparece como indisponível. O histórico de exemplos permanece separado e identificado como ilustrativo.

Rotas adicionais, com `X-Demo-Session` UUID:

- `GET /demo/automation/summary`: execuções, métricas e orçamento restante da sessão.
- `POST /demo/automation/runs?scenario=success|divergence|duplicate`: cria uma execução.
- `POST /demo/automation/runs/{id}/review`: decisão com `action`, `expected_step`, `reason` e, para aprovar, `corrected_source_amount` igual ao valor da nota.

Revisões só são aceitas para a sessão proprietária e na etapa de divergência. Decisões repetidas, concorrentes ou fora de etapa são recusadas sem repetir efeitos. A nota 43 é uma fixture sintética versionada, gerada por `scripts/create_divergence_sample.py`.

O limite continua sendo cinco execuções por sessão, até 128 sessões e TTL de 15 minutos desde a criação. O estado é volátil e por processo, requer um único worker HTTP e desaparece ao reiniciar o serviço. Revisões representam decisões demonstrativas do visitante da sessão, não aprovação empresarial autenticada. Esta entrega não adiciona OCR, IA, processamento em lote, Power Automate nem integração com ERP real.

## Interface para recrutadores

A página inicial apresenta um dashboard responsivo, com visual escuro, filtros, busca e demonstração pública. Os indicadores e registros iniciais são ilustrativos. O PDF sintético de /demo/sample é o único aceito em /demo/analyze, verificado por SHA-256 antes da extração, sem gravar no banco. A área /workspace oferece acesso individual aos dados persistidos. A interface usa HTML, CSS e JavaScript servidos pelo FastAPI; Next.js permanece no roadmap. O repositório GitHub permanece privado.

## Automação demonstrativa entre sistemas

O botão Ver automação em ação abre uma execução de seis etapas no backend: extrair PDF, consultar uma conta a pagar fixa, conferir o valor, criar um lançamento no adaptador de destino, consultar novamente esse lançamento e concluir os eventos de auditoria. Cada etapa exige uma requisição à API com a versão esperada; reenvios concorrentes da mesma versão não avançam duas vezes. A segunda execução na mesma sessão bloqueia o lançamento duplicado e conserva o protocolo original.

Os dois ERPs públicos são adaptadores simulados dentro do processo Python. O estado fica em memória por até 15 minutos, limitado a 128 sessões e cinco execuções por sessão. Ao atingir a capacidade, novas sessões são recusadas sem expulsar sessões ativas. Reiniciar o processo apaga a demonstração. Não há pagamentos nem gravação no PostgreSQL nesse fluxo público. O lock é por processo e exige um único worker HTTP, como configurado no Render. A interface apresenta eventos e protocolo. O robô Playwright separado funciona localmente e no CI, conforme a seção seguinte.

## Robô Playwright

A próxima etapa está implementada como módulo opcional local/CI: [instruções do RPA](docs/rpa-browser.md). Inclui ERP fictício com formulário, preenchimento e salvamento por navegador real, confirmação após recarregar a página, prevenção de duplicidade, screenshots, vídeo e trace. A execução pública gratuita continua usando o fluxo demonstrativo de backend; não executa Chromium no Render.
