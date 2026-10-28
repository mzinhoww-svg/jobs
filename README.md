# Candidaturas privadas

Serviço Python com entrada HTTP autenticada, fila SQLite durável e um worker Chromium/Playwright por perfil. Código e testes usam exemplos fictícios; perfil, documentos, sessões e histórico ficam **fora do checkout**.

**Estado:** desenvolvimento funcional validado em formulários controlados. Isso não equivale a implantação permanente nem a candidatura real comprovada. O executor temporário do Codex não é um servidor de produção.

## Preparar o desenvolvimento

Requisitos: Python 3.12+, uv, Chromium em `/usr/bin/chromium`; Docker opcional. Use o checkout já isolado, sem criar worktree.

```sh
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv run python -m jobs_service.admin init --data-dir /srv/jobs-private
```

O diretório deve ser gravável e privado; use um caminho externo ao checkout. `init` gera um token aleatório de permissão 0600, não o imprime e não sobrescreve dados existentes. Importe o perfil canônico privado com `admin import-profile --data-dir ... --source ...`; não use exemplos como dados reais.

Configure `JOBS_DATA_DIR`, `JOBS_TOKEN_FILE` e `JOBS_ALLOWED_HOSTS` no processo (consulte `.env.example`; não há carregamento automático de .env). Cadastre apenas hosts de portais oficiais e seus recursos necessários. Mantenha a política de saída do host/proxy coerente com essa lista.

```sh
python -m uvicorn jobs_service.api:factory --factory --host 127.0.0.1 --port 8787 --no-access-log
python -m jobs_service.worker
```

Ambos usam a mesma configuração privada. O painel na raiz permite validar o token, colar URL, selecionar `apply`, `prepare` ou `analyze` e acompanhar fila, estados, histórico, documentos e comprovação. A opção “Lembrar neste navegador” salva o token localmente somente após autenticação válida; use apenas em dispositivo pessoal. Sair remove o token salvo. Sem essa opção, ele fica somente na memória da página. Atrás de ingresso privado com HTTPS, ela é o canal de entrada de fallback. Esta conversa **não** está automaticamente conectada à fila.

## API

Use `Authorization: Bearer <token privado>`; nunca coloque token na URL, Git, chat ou histórico de shell. `examples/client.http` é ilustrativo e sanitizado.

- `POST /applications`: `{ "url": "https://portal-oficial/...", "mode": "apply" }`. `apply` representa comando explícito de candidatura; `prepare` e `analyze` não preenchem nem fazem upload.
- `GET /applications` e `GET /applications/{id}`: estados, motivos, histórico e resultado mínimo.
- `GET /applications/{id}/documents/cv.pdf` (também DOCX e carta): download autenticado.
- `POST /applications/{id}/resume`: retoma bloqueios anteriores ao envio depois de corrigir fatos/acesso. Não retoma envio incerto.
- `GET /healthz`: valida acesso ao banco sem revelar identidade ou segredos.

Não existe MCP registrado neste cliente. É possível integrar um cliente autorizado à API, mas essa conexão precisa ser configurada e testada antes de prometer entrada por chat.

## Fluxo e limites verificados

O worker resolve redirecionamentos iniciais com validação de destino, reconhece Greenhouse direto/regional/embutido, lê JobPosting JSON-LD e escolhe BR/EUA pelo país de contratação, nunca pela moeda. Se o portal não fornecer dados suficientes, a candidatura fica bloqueada com motivo específico; `contexts/{id}.json` privado pode complementar observações com fonte, data e confirmação. Consulte o exemplo sanitizado.

Documentos de uma coluna são produzidos em PDF com texto selecionável e DOCX. Somente fatos confirmados com fonte, data ISO e source_kind validado entram no texto; fatos de referência permanecem separados. A adaptação determinística ordena evidências por relação com a descrição. Não há integração paga de IA nem promessa de revisão editorial por um modelo. As cartas são rascunhos concisos; não é um redator universal de cartas de 250–400 palavras. Só os idiomas `en`/`pt` têm templates.

A pesquisa salarial atual captura faixa-base estruturada publicada para a posição e aceita pesquisa complementar privada com fontes datadas, moeda e período. Não existe busca salarial abrangente em múltiplos portais. Sem faixa/pesquisa verificável, não responde salário nem envia. O valor varia com a faixa e evidências de aderência; o critério é uma heurística transparente, não score do ATS. BRL/USD têm pisos privados configuráveis; outras moedas exigem pesquisa/conversão implementada antes do uso. Composição de remuneração desconhecida não é inventada.

O adaptador Greenhouse inicial usa rótulos e opções explícitas, lê novamente valores, verifica bytes do anexo e bloqueia desconhecidos obrigatórios, CAPTCHA e campos não implementados. Formulários controlados foram testados; nenhum envio live Greenhouse está certificado. Lever, Ashby, Workday, Gupy e demais ATS não têm adaptadores de candidatura nesta versão. Cadastro de contas, fluxos de login complexos, magic links e MFA ainda exigem adaptadores específicos; não são contornados.

Gmail é módulo read-only OAuth para identidade, mensagens da candidatura e OTP correlacionado por conta/domínio/requisição/intervalo. A integração do worker atende campo de código de verificação já visível; não é um motor genérico de autenticação em múltiplas etapas. Credenciais devem estar em `gmail-oauth.json` privado com `client_id`, `client_secret`, `refresh_token` e escopo `gmail.readonly` (ou access token válido). Nunca obtenha esses valores pelo chat. A conexão real não foi fornecida/testada. Sem ela, verificações ficam bloqueadas. Não há envio de e-mails a recrutadores.

Persistir intenção antes do clique evita reenvio automático após crash/timeout. Confirmação precisa ser nova e inequívoca; status HTTP, botão clicado e arquivo selecionado não são prova de envio. Casos incertos exigem reconciliação com portal/recibo, sem nova submissão. Não se usa vaga de referência para testes reais.

## Containers e implantação

```sh
docker build --secret id=system_ca,src=/etc/ssl/certs/ca-certificates.crt -t jobs-service:local .
docker run --rm --network none --shm-size=256m --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges jobs-service:local python -m unittest discover -s tests -v
docker compose up -d
```

No ambiente gerenciado, `BUILDX_CONFIG=/workspace/.buildx` evita escrita no HOME somente leitura, sem substituir as credenciais do Docker. O CA é montagem temporária de build; não é copiado à imagem. Pip exige os hashes do lockfile, apt mantém assinaturas e TLS não é desabilitado. A imagem executa como UID 10001, sem privilégios extras; o Chromium usa o comportamento padrão do Playwright sem sandbox do Chromium. Isolamento do container/host e egress confiável continuam necessários.

Compose cria volume privado, inicialização, API e worker com restart, healthchecks, encerramento limpo e trava única. A API fica ligada ao loopback do host; **não** cria ingresso público/privado, domínio, HTTPS, VPN ou infraestrutura permanente. Não expõe debugging do browser. Configure ingresso privado e volume durável cifrado no destino autorizado. Faça a carga do perfil e OAuth por canal de segredos, preservando UID/permissões; o volume nasce sem perfil pessoal.

Um container no executor do Codex valida empacotamento, mas não prova disponibilidade quando a tarefa termina. Consulte `docs/VALIDACAO.md` e `docs/OPERACAO.md` para resultados e bloqueios.

## Documentação

- `AUDITORIA_REPOSITORIOS.md`: seis origens, commits, licenças e decisões anteriores à instalação.
- `docs/PLANO.md`: arquitetura e etapas.
- `docs/OPERACAO.md`: retomada, backup e retenção.
- `docs/VALIDACAO.md`: evidências e lacunas de acesso/implantação.
- `docs/PROGRESSO.md`: continuidade sem refazer auditoria ou etapas concluídas.

## Atualizar uma VPS já instalada

Para a instalação existente em `~/jobs`, com o arquivo privado `../candidaturas.vps.json`:

```sh
cd ~/jobs
git pull --ff-only
bash deploy/update-ui.sh
```

O atualizador verifica projeto e volume existentes, testa a imagem, cria backup privado da base e documentos, preserva o token e atualiza somente API e worker. Em falha de ativação, tenta restaurar a imagem anterior. Não altera Caddy nem outros projetos. Use `bash deploy/update-ui.sh --check` para verificar os pré-requisitos sem atualizar. O backup exclui credenciais e sessões; preserve separadamente os segredos privados.

Depois de `PAINEL_ATUALIZADO`, recarregue a página com Ctrl+Shift+R (Mac: Cmd+Shift+R). Informe o token atual da aplicação, não a chave de IA ou uma senha criada em outra variável. O painel valida a autenticação antes de mostrar os dados. Não envie o token pelo chat.

O painel mostra disponibilidade do worker, perfil confirmado, pesquisa e filtros, histórico real de eventos e exportação JSON. Não apresenta estimativa fictícia de porcentagem. Workday não tem adaptador de envio; o painel explica essa limitação. Appllama não está integrado: exportar JSON não sincroniza com esse serviço. Nenhuma conexão Gmail do ChatGPT é transferida para a aplicação, e esta atualização não modifica Gmail.

Os testes controlados não comprovam uma candidatura real nem validam o perfil pessoal em produção. O serviço deve permanecer bloqueado quando faltarem dados confirmados ou suporte ao ATS.

## Acesso sem token (opção explícita)

Para a VPS já instalada, execute `git pull --ff-only` e `bash deploy/disable-token.sh` dentro do checkout. O script guarda a configuração privada anterior, define `JOBS_AUTH_MODE=none` somente na API e usa o atualizador existente. A página abre diretamente no painel, sem armazenar ou pedir token. O arquivo do token existente não é apagado.

**Com essa opção, qualquer pessoa com o endereço pode ler candidaturas, baixar documentos, adicionar vagas e solicitar ações disponíveis na fila.** O limite de ATS e as verificações de comprovação continuam valendo. Use apenas quando esse acesso público for intencional. Para voltar à proteção, configure `JOBS_AUTH_MODE=bearer` na API do arquivo privado de Compose e recrie somente a API. Valores desconhecidos impedem a inicialização; o padrão permanece `bearer`.

## Leitura de URL, IA e documentos para outros ATS

Na versão 0.3, cole uma URL HTTPS pública. O leitor Chromium remoto tenta extrair o anúncio. OpenRouter ou AI Gateway podem analisar o texto com `deepseek/deepseek-v4.1-flash`; a configuração é privada, por `bash deploy/configure-ai.sh openrouter` (ou `gateway`), que valida a credencial antes de salvar. Tavily é um extrator opcional quando `TAVILY_API_KEY` estiver configurada no worker; a implementação usa API direta, sem depender de um MCP conectado ao chat.

O envio automático continua restrito ao adaptador Greenhouse validado em testes controlados. Para outros ATS, são preparados CV e carta em PDF/DOCX, pacote ZIP e relatório de evidências/lacunas para envio manual. Se o portal não puder ser lido, preencha a descrição manual no painel. Perfil pessoal e chave de IA precisam existir no volume privado da VPS; não são herdados desta conversa. A matriz, os limites e o estado dos testes reais estão em [docs/PLATAFORMAS.md](docs/PLATAFORMAS.md).
