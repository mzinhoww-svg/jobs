# Operação e retomada

## Acesso LetsCloud na retomada de 27/10/2026

A implantação na VPS existente está autorizada. Não solicitar novamente autorização de rotina nem credenciais pelo chat. A API funciona com `API_LETSCLOUD_KEY` no header `api-token` para `https://core.letscloud.io/api/instances`; usar somente GET para inspeção, sem registrar resposta integral (ela pode incluir senha inicial). Não usar o hostname genérico `api.letscloud.io` como evidência de validade da chave: a documentação aponta `core.letscloud.io/api`.

Para continuar, é necessário que a configuração suportada do ambiente permita TCP para o destino indicado em `IP_letsCloud`, porta SSH, e que o proxy TCP esteja disponível. A fotografia atual tem listas TCP vazias, sem VPN, e o proxy recusou conexão. Não tentar conexão direta nem outro proxy para contornar a restrição. `SSH_PRIVATE_KEY` está presente, porém não carregou como chave privada; verificar/corrigir a vinculação pelo gerenciador de segredos, sem enviar seu conteúdo ao chat. A senha existente pode ser usada apenas se transporte e cliente suportarem, preservando a verificação da identidade do host. Não houve tentativa de login remoto.

Falta uma identidade de host confiável: não foram encontrados arquivos `known_hosts` nos caminhos padrão verificados. Obter fingerprint/chave de host por canal autenticado do provedor ou inventário confiável e validar antes de aceitar. `ssh-keyscan` isolado não autentica a identidade; não usar `StrictHostKeyChecking=no`.

Após acesso: inventariar SO, uso de RAM/disco, Docker/Compose, containers, portas, firewall, DNS e certificados; preservar serviços e alterações existentes. Escolher ingresso HTTPS e armazenamento persistente com base nesse inventário. Aplicar e validar inicialização automática, healthchecks e backup/restauração sem reiniciar serviços alheios. Não há URL privada de produção para compartilhar nesta retomada.

Fontes privadas preservadas em `/workspace/private-onboarding`, pacote em `/workspace/attachments` e perfil canônico preparado em `/workspace/jobs-private-runtime/profile.json`. Não substituir por `examples`. Conferir hashes e permissões antes da transferência segura para volume privado na VPS. A fila preparada estava íntegra e vazia; não importar histórico de referência como candidaturas.

Gmail permanente exige OAuth da conta correta, escopo `gmail.readonly`, armazenado como `gmail-oauth.json` no diretório privado do serviço, 0600 e proprietário do worker. Configurar consentimento/credenciais por canal seguro externo ao chat; não herdar a conexão do plugin. Nenhum arquivo assim foi encontrado sob `/workspace`; não foi possível procurar dentro da VPS. Após disponibilizar OAuth, executar `Gmail(arquivo, email_confirmado_do_perfil).verify_identity()` no executor permanente, sem imprimir e-mail/tokens. Testar correlação com contexto autorizado antes de declarar verificações por Gmail funcionais; nunca enviar e-mail.

Quando o ingresso privado HTTPS estiver validado, compartilhar links pela interface: abrir o endereço, inserir token privado por canal seguro, colar a URL oficial e escolher `analyze`, `prepare` ou `apply`. `apply` autoriza envio daquela URL e só deve ser usado com novo link explicitamente autorizado. Esta conversa não enfileira links automaticamente. Até lá, não apresentar o loopback de desenvolvimento como endereço de produção.

## Dados e confiança

O pacote recebido não é versionado. O perfil privado preserva categorias e fontes do JSON original. CVs de referência não comprovam envio nem verificam independentemente seus fatos. O histórico recuperado não foi importado como fila de candidaturas. Não há link novo autorizado para envio real.

Diretório privado: `profile.json`, `queue.sqlite3`/WAL, `applications/{id}/` (documentos, manifesto e pesquisa salarial), `contexts/{id}.json`, `browser-state.json`, `api-token` e opcional `gmail-oauth.json`. Diretórios 0700, arquivos 0600; use armazenamento de nuvem cifrado e acesso limitado. Não copiar isso ao Git, imagem Docker ou logs. A raiz privada deve pertencer ao mesmo usuário do serviço.

Para complementar uma vaga bloqueada, leia o motivo via API, verifique a fonte profissional/oficial e salve os campos necessários no contexto privado. Somente respostas com fonte/data/confirmação explícita são usadas. Respostas de cidadania, diploma, autorização, sponsorship, consentimento e salários nunca recebem defaults genéricos. O-1 não implica autorização para qualquer empregador.

## Estados e retomada

Estados: RECEBIDA, EM_ANALISE, DOCUMENTOS_PRONTOS, EM_PREENCHIMENTO, AGUARDANDO_VERIFICACAO, ENVIADA_COMPROVADA, ENVIO_INCERTO, DUPLICADA, VAGA_ENCERRADA, INCOMPATIVEL_REMUNERACAO, INCOMPATIVEL_REQUISITO e BLOQUEADA.

`reason` é um código sem detalhes pessoais. `documents` contém tamanho/hash; não é comprovante de candidatura. `proof` registra digest/contexto de confirmação explícita. Preserve eventos e correções.

- Bloqueio anterior ao envio: corrigir a fonte/acesso e usar `/resume`.
- Erro transitório anterior ao envio: até três tentativas com backoff.
- Timeout/crash depois da intenção de submit: ENVIO_INCERTO; nunca reexecutar às cegas. Conferir portal e recibo relacionado, sem tratar OTP como recibo. Reconciliação automática de envios incertos ainda não existe; exige operação assistida documentada.
- CAPTCHA/MFA: bloqueio honesto. Nenhum solver, stealth, rotação ou fallback por e-mail.
- Um bloqueio não impede o processamento dos próximos links.

O worker mantém lease, heartbeat e trava de processo. Apenas um worker por perfil/volume. Após desligamento abrupto, aguarde expiração da lease (180 s) para recuperar trabalho anterior ao envio. A intenção é durável e leva a estado incerto, não a reenvio. Não escale múltiplos workers SQLite para o mesmo perfil.

## Backup e recuperação

Pare somente o worker deste serviço. A API pode permanecer ativa. O comando usa SQLite backup e impede snapshot enquanto o worker mantém a trava.

```sh
python -m jobs_service.admin backup --data-dir /srv/jobs-private --target /srv/jobs-backups/snapshot-YYYYMMDD
python -m jobs_service.admin restore --source /srv/jobs-backups/snapshot-YYYYMMDD --data-dir /srv/jobs-restored
```

Use caminhos externos ao checkout. O destino não pode existir. Backup contém perfil, banco, contextos e documentos e inclui manifesto SHA-256; não inclui token de API, OAuth ou sessão do navegador. Restore verifica integridade e gera um token novo. Religue integrações por mecanismo seguro. Hash verifica integridade acidental, não substitui assinatura/cifra/autenticidade do local de backup.

Política inicial: manter documentos/evidências enquanto a candidatura estiver ativa e até 90 dias após encerramento; backups por 30 dias em armazenamento cifrado. Não há agendamento de expurgo automático nesta versão: fazer revisão manual autenticada, preservar metadados mínimos de deduplicação e não apagar evidência de envio incerto antes de reconciliar. Nenhuma automação periódica de busca de vagas foi criada.

## Implantação permanente ainda necessária

É preciso um destino já autorizado com execução contínua de containers ou processos, volume durável, acesso de implantação, ingresso privado com HTTPS e política de saída. A máquina gerenciada de desenvolvimento não fornece essas garantias por manter um processo ativo. Nenhum custo recorrente foi contratado.

Gmail requer OAuth `gmail.readonly` no executor de produção e teste mínimo de identidade da conta. Uma conexão de outro cliente não é herdada. Nenhum segredo deve ser fornecido no chat. Ajustar hosts permitidos para cada portal oficial e recursos necessários; cada redirect inicial é validado, redirects inesperados no browser são bloqueados. O proxy do runtime gerenciado resolve DNS e aplica a política externa; uma implantação própria exige controle equivalente, inclusive contra DNS rebinding.

## Falha de configuração da IA

Se a atualização terminou mas apareceu `AI_SETUP_FAILED: AI_PROVIDER_FAILED`, a integração não foi ativada e a chave nova não foi salva. Para obter um diagnóstico sem rebuild nem alterar a configuração, atualize o checkout e execute `bash deploy/diagnose-ai.sh openrouter` (ou `gateway`). Informe a chave no campo oculto. O script envia somente uma vaga e uma evidência sintéticas e imprime `AI_DIAGNOSTIC` com HTTP, categoria e resultado de validação; não imprime chave, resposta livre nem perfil.

`INSUFFICIENT_CREDITS` identifica HTTP 402; `CREDENTIAL_REJECTED` identifica 401/403; `MODEL_OR_ENDPOINT_NOT_FOUND` identifica 404; `RATE_LIMITED` identifica 429; `MODEL_OUTPUT_TRUNCATED` distingue uma resposta 200 interrompida por limite de tokens. Esses códigos orientam a próxima correção. O diagnóstico não ativa a IA nem declara sucesso quando a chamada falha.

Se a chave já responde mas a configuração falha com `JOB_METADATA_INCOMPLETE`, o problema é o antigo teste que usava uma vaga fictícia. A configuração atual valida somente a conexão e uma resposta JSON mínima do modelo, independentemente da análise de vagas. Execute `git pull --ff-only` e `bash deploy/configure-ai.sh openrouter`. Containers da versão 0.3 executam o novo configurador sem rebuild. `AI_CONFIGURED` comprova conexão e gravação privada da chave; análise e candidatura reais continuam dependendo de validação própria.
