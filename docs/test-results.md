# Resultado dos testes — 1 de novembro de 2026

> **Registro histórico** da primeira bateria completa. Etapas posteriores adicionaram contas, conciliação em lote e assistente (veja também [validação de contas](accounts-validation.md)). O estado atual da suíte é o do [CI](https://github.com/DeividiLuccasdev/autoflow-rpa/actions/workflows/ci.yml).

Execução completa no GitHub Actions: [run 41333818072](https://github.com/DeividiLuccasdev/autoflow-rpa/actions/runs/41333818072).

Commit testado: `077625d8fc2266a7b776b8fd91642358f8c98508`.

- 127 testes aprovados em 44,14 segundos.
- 0 falhas, 0 erros, 0 testes pulados.
- 63 novos request specs; 64 testes preexistentes preservados.
- PostgreSQL 16, Redis 7, Celery worker/beat e Chromium reais, em infraestrutura exclusiva do CI.
- Auditoria de dependências: nenhuma vulnerabilidade conhecida encontrada.
- Um aviso de depreciação do TestClient sobre futura adoção de httpx2; não é falha de teste.

O relatório JUnit está no artefato `integration-test-results` da execução. O runner falha se encontrar qualquer skip. Nenhum teste preexistente foi apagado, pulado ou afrouxado. Nenhuma regra de produção foi modificada nesta entrega. Não foi criado novo E2E.

## Bugs encontrados

Nenhum bug de aplicação foi revelado pelos cenários executados. Isso representa a cobertura desta suíte, não uma garantia de ausência de outros bugs.

## Limitações e execução local

Na máquina local, 118 testes passaram usando PostgreSQL 18 e Chromium; os nove cenários do arquivo de fila foram verificados no ambiente completo do CI. Docker local retornou falta de acesso ao serviço, então o runner Compose não pôde ser executado nesta máquina. A configuração Compose foi validada com `docker compose config --quiet`.

Para executar todos depois de uma alteração, inicie o Docker Desktop e rode `python scripts/test_all.py` na raiz do projeto. Esse comando prepara toda a infraestrutura descartável; não é necessário cadastrar credenciais de produção.

Login individual, pagamentos e autorização financeira entre usuários não existem no produto atual. Consulte [cobertura e limites](request-specs.md).
