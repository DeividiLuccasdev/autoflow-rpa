# Contas por convite

A demonstração pública permanece em `/`. A área privada fica em `/workspace`, com link Minha área no cabeçalho. Não há cadastro aberto nem envio automático de e-mail.

## Primeiro acesso

1. Na área privada, abra **Operador · emitir convite**.
2. Informe o e-mail do destinatário e a chave operacional `AUTOFLOW_API_KEY`, disponível nas variáveis de ambiente do serviço no Render. Não compartilhe essa chave com convidados.
3. Gere o convite. O código é exibido uma única vez, vale 24 horas e deve ser entregue ao destinatário por um canal privado.
4. Em **Ativar convite**, o destinatário informa seu e-mail, código e uma senha de pelo menos 15 caracteres.
5. Em **Entrar**, usa e-mail e senha. A área mostra somente suas notas, auditoria e execuções.

O operador também pode emitir convites por `POST /auth/invitations` com `X-API-Key` e JSON `{ "email": "destinatario@example.com" }`. A chave não é gravada no navegador e não concede acesso às notas das novas contas. Usuários individuais não podem emitir convites. Não há conta ou senha padrão.

## Sessões e senhas

Senhas usam PBKDF2-HMAC-SHA256 com 600.000 iterações e salt aleatório individual. Não são armazenadas em texto puro. O cookie da sessão é opaco, HttpOnly, SameSite=Strict e Secure em HTTPS/Render. No banco fica somente seu hash. As sessões duram oito horas; logout revoga a sessão atual no banco. Escritas autenticadas por cookie exigem o token CSRF obtido em `/auth/login` ou `/auth/me`, no cabeçalho `X-CSRF-Token`.

Login e ativação compartilham limite de dez requisições por minuto por conexão/IP, no processo único usado neste deploy. O limite não é distribuído; ampliar workers ou réplicas exige armazenamento compartilhado para ele. Erros de login não distinguem conta inexistente de senha inválida. Respostas de validação de autenticação não devolvem valores de senhas ou convites. Corpos de autenticação têm limite de 8 KiB.

Referências: [armazenamento de senhas OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) e [gerenciamento de sessões OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Dados e migração

A migração 0004 cria usuários, convites e sessões, adiciona proprietário aos registros e muda a unicidade de notas e hashes para incluir esse proprietário. A reivindicação de convite e a criação da conta são transacionais; tentativas simultâneas consomem o código uma única vez. As notas, documentos e execuções existentes recebem o proprietário reservado `legacy`. Não são atribuídos automaticamente a nenhuma conta.

Notas de usuários diferentes podem ter a mesma identidade fiscal e o mesmo PDF. No mesmo usuário, continuam bloqueadas as duplicidades. Filtros de proprietário são aplicados na consulta de notas, auditoria e execuções; o worker conserva o proprietário ao criar nota e documento. A política é aplicada pela API e pelo worker, não por PostgreSQL RLS. A conexão de aplicação não deve ser entregue a usuários finais.

O downgrade não é automático: restaurar unicidade global exige reconciliar notas válidas de contas distintas. Não reverta para uma versão antiga que consulta registros globalmente após ativar contas. Não há transferência do acervo legado, recuperação de senha por e-mail, MFA nem painel de administração de contas nesta etapa.

O Render gratuito continua com fila desativada. O upload síncrono autenticado funciona; Celery e Redis são validados no ambiente separado do CI.

## Validação

Execute `python scripts/test_all.py` na raiz com Docker Desktop ativo. A suíte preserva os testes antigos e adiciona request specs PostgreSQL de convite, login, logout, expiração, CSRF, autorização, concorrência e processamento com dois proprietários por workers reais. O único ajuste de expectativa antigo autorizado foi a versão de migration de 0003 para 0004; as verificações de preservação e processamento foram mantidas.
