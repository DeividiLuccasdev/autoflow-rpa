# Revisão de segurança - 01/11/2026

Escopo: código do AutoFlow, dependências instaladas no ambiente de desenvolvimento, configurações de build e verificações HTTP de baixo impacto no endereço público. Não é certificação de segurança, pentest exaustivo ou garantia de ausência de falhas. Nenhum teste de carga ou ataque destrutivo foi executado no serviço.

## Problemas confirmados e corrigidos

- Sem controle de frequência: middleware passa a limitar criação/análise da demonstração a 15 requisições/minuto por endereço de conexão, avanço a 90 e API privada a 60. Respostas 429 têm Retry-After. Tabela de controle tem limite de memória. Não usa X-Forwarded-For recebido como chave; se o proxy agrupar clientes, o limite pode ser compartilhado. Proteção é por processo, para o deploy demonstrativo de um worker. Não substitui proteção distribuída contra DDoS.
- Upload privado era lido antes da autenticação: verificação de chave agora ocorre antes de consumir o corpo. Dependência de autenticação nas rotas foi mantida como proteção adicional.
- Upload público usava o teto geral de 5 MiB: corpo público agora é limitado a 128 KiB antes do parser multipart; o endpoint continua limitando o arquivo a 64 KiB e aceita somente o hash do PDF fictício conhecido.
- Ausência de políticas do navegador: adicionados CSP, bloqueio de iframe, nosniff, Referrer-Policy e Permissions-Policy. CSP da página principal não libera scripts inline. Swagger recebe exceção específica para seu inicializador e CDN. HSTS é enviado em HTTPS e no ambiente Render.
- Requisições mutáveis com Origin de outro domínio agora são recusadas. Não foi liberado CORS genérico.
- Uma sessão nova podia expulsar sessões ativas: lotação agora rejeita novas sessões com 429 sem apagar sessões em uso. Consulta de execução inexistente deixou de criar sessão, reduzindo a possibilidade de ocupar o armazenamento por essa rota.
- O scanner detectou avisos conhecidos no pip 25.0.1. Atualizado para 26.2.2 no ambiente local; builds do Docker, Render e CI passam a exigir pip >=26.2,<27. A contagem original continha identificadores repetidos, portanto não representa doze falhas diferentes na aplicação.

## Verificações

- Antes da correção, consulta privada sem chave retornou 401 e tentativa de escapar do diretório de assets retornou 404.
- pip-audit --local após a atualização: nenhuma vulnerabilidade conhecida encontrada no ambiente auditado, incluindo as dependências da ferramenta. O resultado é limitado à base de avisos consultada e às versões instaladas; não analisa a lógica da aplicação, sistema operacional ou pacotes JavaScript externos do Swagger.
- Testes novos cobrem políticas HTTP, origem malformada/externa, limite de frequência e tentativa de contorná-lo com X-Forwarded-For, autenticação antes do corpo, limite do corpo público, armazenamento limitado e preservação de sessões ativas.
- CI passa a executar pip-audit e bloquear a entrega se houver vulnerabilidades conhecidas. PostgreSQL e concorrência são verificados no GitHub Actions.

## Limitações que permanecem explícitas

O demo não deve receber dados reais. A etapa posterior de [contas por convite](accounts.md) adiciona identidade individual, CSRF e separação financeira; a chave compartilhada permanece somente para o acervo legado e emissão de convites. Ainda não há RBAC de organizações. Estado da demonstração e limites de frequência são locais ao processo e somem no reinício. O parser privado não está isolado em subprocesso; somente o PDF canônico é aceito publicamente. Uso de produção exige recuperação de contas, isolamento do parser, controle de taxa distribuído, política de retenção/backups e monitoramento. O banco gratuito permanece sujeito aos limites do plano contratado.
