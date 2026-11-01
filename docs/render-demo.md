# Demonstração gratuita no Render

O render.yaml cria somente uma API web Free e um PostgreSQL Free. Não cria workers, Redis ou agendador. O endpoint de fila retorna 503 sem gravar pendências; o upload síncrono permanece disponível. A chave de API é gerada pelo Render e não deve ser colocada no Git ou compartilhada em capturas de tela.

1. No painel do Render, escolha New > Blueprint e conecte somente o repositório DeividiLuccasdev/autoflow-rpa.
2. Confira os dois recursos Free e a região Oregon. Se já houver um PostgreSQL gratuito na conta, não substitua nem exclua esse banco; verifique a disponibilidade antes de continuar.
3. Revise a criação dos recursos. O banco gratuito expira em 30 dias e a API dorme após 15 minutos de inatividade. Não use dados reais; faça exportação dos dados fictícios que quiser preservar antes da expiração.
4. A API aplica Alembic antes de iniciar, com um único worker HTTP. O health check /ready verifica conexão e presença da tabela de notas.
5. Após o deploy, consulte /health e /ready. Para usar /docs, copie a chave de Environment no painel e informe-a em Authorize. Teste o PDF examples/nota-ficticia.pdf: primeiro upload retorna 201 e a repetição retorna 409.

Deploys futuros usam After CI Checks Pass. A primeira instalação pode iniciar o primeiro deploy durante a criação; confirme o CI do commit antes de aplicar. Não há acesso público ao PostgreSQL no Blueprint. A URL HTTPS da API e a documentação serão públicas, mas as rotas /api/v1 exigem a chave.

Este modo demonstra cadastro, extração e auditoria. Não representa a infraestrutura completa de RPA. Ainda faltam usuários individuais, limitação de taxa, observabilidade e política operacional para exposição além de uma demonstração controlada.

Referências: https://render.com/docs/free e https://render.com/docs/blueprint-spec.
