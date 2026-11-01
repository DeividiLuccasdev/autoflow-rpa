# Validação de contas — 1 de novembro de 2026

Commit de aplicação: `70b64f42fad88a68ec0fcd79db169a542e72592e`.

[Execução completa no CI](https://github.com/DeividiLuccasdev/autoflow-rpa/actions/runs/41335014590): **145 testes aprovados em 56,98 segundos**, sem falhas ou testes pulados. A auditoria de dependências não encontrou vulnerabilidades conhecidas. Há um aviso de depreciação do TestClient, já presente na entrega anterior.

São 18 novos request specs sobre contas e isolamento, somados aos 127 anteriores. As rotas, transações e autenticação usam PostgreSQL real. O cenário de processamento envia o mesmo PDF por dois usuários e verifica com Redis, beat e dois workers reais que as notas e documentos conservam seus proprietários. Não há mock de autenticação, banco ou regra de negócio.

Na máquina local passaram 17 cenários de conta sem fila e 76 testes selecionados de regressão/migração. A tela foi inspecionada no navegador, incluindo alternância para ativação de convite. Não foi acrescentado E2E novo. O E2E existente continua na suíte.

Nenhum bug foi revelado pelos cenários executados. A única expectativa preexistente alterada foi a versão literal da migração de 0003 para 0004, com autorização explícita do responsável pelo produto; verificações de preservação de dados e processamento foram mantidas.

Comando único, na raiz e com Docker Desktop ativo: `python scripts/test_all.py`.
