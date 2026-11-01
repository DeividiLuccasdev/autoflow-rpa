# Testes de integração por requisição

Execute na raiz do projeto, com Python e Docker Desktop em funcionamento:

```powershell
python scripts/test_all.py
```

O comando cria um projeto Compose exclusivo, inicia PostgreSQL 16 e Redis 7 descartáveis, instala Chromium e executa a suíte completa. Retorna código diferente de zero se houver falha ou teste pulado. Ao terminar, remove apenas os recursos desse projeto de teste. Não usa o compose de desenvolvimento, arquivos .env, volumes ou credenciais de produção. A primeira execução precisa de internet para baixar imagens e dependências.

O CI executa o mesmo runner `backend/run_test_suite.py`, com serviços dedicados. O relatório JUnit fica no artefato `integration-test-results`. O job de navegador existente continua publicando suas evidências.

## Infraestrutura e isolamento

Os novos request specs ficam em `backend/tests/request_specs`. Cada teste financeiro cria um schema aleatório em um PostgreSQL de teste, aplica as migrations Alembic reais e injeta uma sessão SQLAlchemy real na aplicação. O teste chama as rotas FastAPI com TestClient; não substitui banco, validações, transações ou regras. As requisições concorrentes usam threads sincronizadas por uma barreira.

Os testes assíncronos usam Redis real, Celery worker e beat em processos separados, com fila e prefixo exclusivos por teste. O worker recebe a URL do mesmo schema de teste. A frequência de beat é de um segundo para observação; as regras de processamento, reserva e tentativas são as de produção. Entrega duplicada é enviada pelo broker real. Falhas de persistência são provocadas por uma restrição SQL temporária no schema exclusivo. A indisponibilidade de Redis usa CLIENT PAUSE no serviço descartável e se recupera automaticamente. Nunca execute esses testes em um Redis compartilhado com aplicações.

O runner recusa hosts externos e nomes de banco sem sufixo `_test`; exige Redis de teste no banco 15. A API importada pelos testes usa SQLite em memória como conexão padrão de segurança, mas todas as rotas financeiras destes request specs usam PostgreSQL. O ERP fictício separado usa SQLite temporário real, conforme a stack dele. Os testes legados foram preservados, inclusive seu uso de SQLite e mocks antigos; não são apresentados como novos request specs.

## Comportamentos cobertos

### describe Cadastro e upload financeiro

- it quando os campos são válidos, então normaliza, cadastra e audita na mesma transação.
- it quando campos são inválidos ou obrigatórios estão ausentes, então retorna 422 sem gravar.
- it quando valor é zero, negativo, tem casas decimais excedentes ou excede a capacidade, então rejeita.
- it quando a identidade se repete após normalização, então retorna 409 sem novos efeitos.
- it quando duas requisições cadastram a mesma nota simultaneamente, então somente uma persiste.
- it quando a auditoria falha no banco real, então desfaz a nota e não expõe detalhes SQL.
- it quando o PDF é válido, então preserva o documento e os eventos de auditoria.
- it quando o PDF é corrompido, protegido, vazio, ambíguo, incompleto ou excede limites, então rejeita sem efeitos.
- it quando JSON e PDF representam a mesma nota, então bloqueia duplicidade entre os canais.
- it quando uploads são simultâneos, então apenas um documento e seus eventos persistem.
- it quando o nome do arquivo contém caminho, então não cria arquivo nesse caminho.

### describe Acesso e consulta

- it quando a chave está ausente ou incorreta, então bloqueia leitura e escrita sem efeitos.
- it quando a configuração não tem chave, então falha fechado.
- it quando o registro não existe, então retorna 404.
- it quando a paginação é válida, então respeita ordem, limite e offset; quando inválida, então retorna 422.
- it quando a origem de uma escrita é externa, então bloqueia sem gravar.
- it quando a resposta é privada, então não permite cache.

### describe Execuções com fila real

- it quando a fila está desabilitada, então retorna 503 sem criar execução.
- it quando o mesmo PDF é enviado simultaneamente, então retorna a mesma execução.
- it quando Redis está temporariamente indisponível, então conserva a pendência e processa após recuperação.
- it quando o worker recebe PDF válido, então conclui, vincula a nota e audita como worker.
- it quando o PDF é inválido, então encaminha para revisão sem nota parcial.
- it quando a nota já existe, então marca duplicidade sem novos efeitos.
- it quando o broker entrega a mesma tarefa a dois workers, então há um único efeito financeiro.
- it quando as cinco tentativas já se esgotaram, então encerra como falha e não lança a nota.
- it quando a gravação falha, então desfaz efeitos parciais e retoma após recuperação.

### describe Demonstração pública e ERP fictício

- it quando recebe o PDF canônico, então extrai sem gravar dados financeiros; quando recebe outro PDF, então rejeita.
- it quando duas chamadas avançam a mesma etapa, então avança uma única vez.
- it quando sessão B tenta avançar execução de A, então retorna 404.
- it quando a sessão expirou, então não continua.
- it quando repete o fluxo completo, então conserva um lançamento e o mesmo protocolo.
- it quando atinge limites de execuções, sessões, corpo ou requisições por IP, então rejeita; sessões ativas são preservadas.
- it quando troca X-Forwarded-For, então não contorna o limite por conexão.
- it quando salva o formulário do ERP e recarrega, então conserva um lançamento.
- it quando dois formulários são enviados simultaneamente, então apenas um persiste.
- it quando o valor do formulário é inválido, então não grava.

## Limites de produto

O escopo inicial desta bateria não incluía usuários. A etapa seguinte, aprovada pelo responsável pelo produto, adicionou [contas por convite e isolamento financeiro](accounts.md), com novos request specs em `test_accounts_requests.py`. A chave operacional agora acessa somente o acervo legado. Checkout, gateway, webhook de pagamento, estoque e planos continuam fora do produto; não há teste fictício afirmando cobertura desses fluxos.

Nenhum E2E novo foi adicionado. O E2E Playwright existente é executado integralmente. Bugs reais encontrados devem permanecer falhando e ser registrados; expectativas não devem ser alteradas sem validação do responsável pelo produto.
