# Demonstração gratuita no Render

O render.yaml cria somente uma API web Free e um PostgreSQL Free. Não cria workers, Redis ou agendador. O endpoint de fila retorna 503 sem gravar pendências; o upload síncrono permanece disponível. A chave de API é gerada pelo Render e não deve ser colocada no Git ou compartilhada em capturas de tela.

1. No painel do Render, escolha New > Blueprint e conecte somente o repositório DeividiLuccasdev/autoflow-rpa.
2. Confira os dois recursos Free e a região Oregon. Se já houver um PostgreSQL gratuito na conta, não substitua nem exclua esse banco; verifique a disponibilidade antes de continuar.
3. Revise a criação dos recursos. O banco gratuito expira em 30 dias e a API dorme após 15 minutos de inatividade. Não use dados reais; faça exportação dos dados fictícios que quiser preservar antes da expiração.
4. A API aplica Alembic antes de iniciar, com um único worker HTTP. O health check /ready verifica conexão e presença da tabela de notas.
5. Após o deploy, consulte /health e /ready. Para usar /docs, copie a chave de Environment no painel e informe-a em Authorize. Teste o PDF examples/nota-ficticia.pdf: primeiro upload retorna 201 e a repetição retorna 409.

Deploys futuros usam After CI Checks Pass. A primeira instalação pode iniciar o primeiro deploy durante a criação; confirme o CI do commit antes de aplicar. Não há acesso público ao PostgreSQL no Blueprint. A URL HTTPS da API e a documentação são públicas; as rotas /api/v1 exigem sessão individual ou chave operacional restrita ao acervo legado. Acesse /workspace e siga as [instruções de convite](accounts.md) para ativar contas. A migração 0004 mantém os registros existentes separados das novas contas.

Este modo demonstra contas individuais, cadastro, extração e auditoria, com limite de taxa local ao processo. Não representa a infraestrutura completa de RPA. Observabilidade, recuperação de contas, isolamento do parser e política operacional continuam necessários para uso além de uma demonstração controlada.

Referências: https://render.com/docs/free e https://render.com/docs/blueprint-spec.
