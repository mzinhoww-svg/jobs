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

Ambos usam a mesma configuração privada. A interface simples na raiz permite colar URL, selecionar `apply`, `prepare` ou `analyze` e consultar estados com token. O token fica apenas na memória da página; não é salvo em localStorage. Atrás de ingresso privado com HTTPS, ela é o canal de entrada de fallback. Esta conversa **não** está automaticamente conectada à fila.

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
