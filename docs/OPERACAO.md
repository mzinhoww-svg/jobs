# Operação e retomada

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
