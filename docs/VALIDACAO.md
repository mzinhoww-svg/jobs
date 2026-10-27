# Validação e estado da entrega

Data: 2026-10-27. Não há candidatura real autorizada nesta implantação. Nenhuma vaga ou documento de referência foi usado para enviar candidatura.

## Nova verificação da retomada LetsCloud

Em 27/10/2026, `uv run python -m unittest discover -s tests -v` aprovou os 35 testes em 12,611 s. A imagem existente `jobs-service:local` aprovou os mesmos 35 em 10,113 s com `--network none --shm-size=256m --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges`. São testes controlados, incluindo Chromium e reinício lógico da fila sem reenvio. Não houve reinício da VPS nem validação de persistência em produção.

API LetsCloud autenticada validada por GET no endpoint oficial; VPS correspondente ligada, 1 vCPU, 2 GB de RAM, disco provisionado de 50 GB. SSH não alcançado: política TCP sem destinos liberados e conexão ao proxy TCP configurado recusada. Chave privada cadastrada não carregou no `ssh-keygen`; senha não testada remotamente. Nenhuma identidade de servidor foi aceita ou ignorada. Inspeção interna de SO, disco livre, Docker, serviços, firewall e domínios permanece bloqueada por acesso, assim como configuração e validação de HTTPS, backup agendado e recuperação na VPS.

Perfil e documentos privados foram localizados fora do checkout; perfil válido com permissões privadas, banco com `integrity_check=ok` e zero entradas. Não há OAuth Gmail encontrado no workspace; disponibilidade na VPS desconhecida. Não se declara Gmail funcional. Os resultados históricos abaixo continuam sendo evidências de desenvolvimento, não de produção. A autorização da VPS agora existe; o bloqueio atual é transporte/autenticação verificável, não ausência de autorização do usuário.

## Verificado

- 35 testes `unittest` executados e aprovados no Python 3.12 do ambiente e na imagem Docker, inclusive Chromium real em rede externa desabilitada.
- Entrada autenticada rejeita ausência de token e modo omitido; URL explícita com modo válido entra na fila persistente. Hosts não aprovados e destinos locais literais são rejeitados.
- API HTTP real: health 200, chamada sem autenticação 401, entrada autenticada 201. Worker real reconheceu perfil ausente no armazenamento de smoke e registrou bloqueio honesto, sem tentar envio.
- Fila SQLite: deduplicação, identidade canônica entre URLs, promoção analyze/prepare → apply, promoção durante execução, trava/lease, limite de retentativas e intenção persistida antes do clique. Conclusão/prova/liberação de lease são uma transação.
- Fluxo integrado controlado: URL Greenhouse fictícia → leitura da vaga → perfil BR → salário de faixa publicada → PDF/DOCX → formulário → upload dos bytes reais → confirmação nova da requisição → ENVIADA_COMPROVADA. Esse estado no teste pertence exclusivamente à fixture, não a uma empresa real.
- Testes de timeout, texto antigo de sucesso, mudança irrelevante no DOM, requisição errada, campo obrigatório desconhecido, reset de valor, dropdown condicional, anexo vazio, CAPTCHA e reinício sem reenvio.
- Detecção Greenhouse por host direto/regional/iframe; gh_jid sozinho não prova ATS. Nenhuma alegação de suporte live a outros ATS.
- Documentos não vazios, hashes, parsing PDF/DOCX, ausência de layout em tabelas, isolamento BR/EUA e fonte TrueType incorporada. PDF sintético renderizado para revisão visual. Documentos reais não foram enviados.
- Salário varia com a faixa e preserva piso-base/unidade; salário total, moeda sem conversão e evidência insuficiente bloqueiam. Não há pesquisa salarial geral live comprovada.
- Gmail em fixtures: destinatário/domínio/intervalo, requisição exata, finalidade de verificação de candidatura, autenticação DMARC do remetente e expiração. OAuth real não disponível; teste do worker registra esse impedimento.
- Backup/restauração com SQLite backup, documentos e manifesto de integridade; token/sessão/OAuth não entram no backup. Restore não sobrescreve destino existente e emite novo token.
- Imagem construída com TLS/assinaturas/hashes preservados; executa como UID 10001. API/worker em Compose possuem volume, healthchecks, restart e API ligada somente ao loopback do host. Um teste de reinício de container verifica banco e download autenticado de PDF preservado; somente o registro sintético desse teste é removido depois.

## Revisão final

Revisão independente encontrou seis problemas importantes e foram acrescentados testes que falharam antes das correções: prova falsa por texto pré-existente, modo omitido permitindo apply, impossibilidade de promover análise/preparação para apply, correlação Gmail frouxa, conclusão em duas transações e origem insuficientemente tipada de fatos. A suíte passou após as correções. Sem alegação de revisão externa dos serviços live.

Fatos aceitos precisam de `confirmation=confirmed`, `source`, data ISO e `source_kind` em `candidate_declaration`, `professional_record`, `official_job_posting` ou `verified_employer_source`. `generated_document` e fontes desconhecidas são excluídos. Valores de contato estruturados sem confirmação também são excluídos. Exemplos são sintéticos; fatos pessoais não estão no Git.

Decisões do executor: manter implementação independente em vez de importar os seis produtos, pela incompatibilidade e riscos auditados; usar somente recursos existentes e não contratar serviços pagos; publicar apenas código/documentação/exemplos sanitizados no repositório selecionado, cuja página se identifica como público. Os anexos recomendam repositório privado, mas não são por si um pedido de alteração de visibilidade. A publicação de código sanitizado segue o pedido direto da conversa.

Limitações menores registradas da revisão: gravação de sessão do navegador ainda não é atômica e falha de inicialização/cleanup pode deixar processo até o worker terminar; parser de caminho Greenhouse ainda tolera sufixo após ID numérico e não tem mapa de aliases de boards. Isso pode exigir intervenção/produzir duplicidade incorreta em URLs malformadas; não autoriza reenvio após intenção. O risco de glyphs/portabilidade do PDF foi resolvido com fonte incorporada e validação das frases; CI usa a mesma imagem Docker testada, em vez de presumir um pacote Chromium do runner.

## Não verificado / bloqueado

| Recurso | Evidência atual | Falta concreta |
|---|---|---|
| Implantação permanente | Executor de desenvolvimento e containers locais disponíveis; manifesto de identidades vazio | Destino autorizado de execução contínua, credencial/mecanismo de implantação, volume durável e ingresso privado HTTPS |
| Gmail de produção | Sem conexão/OAuth vinculado neste executor | OAuth da conta correta no executor de produção; teste mínimo de identidade e verificação correlacionada |
| Entrada pelo chat/MCP | Apenas API e interface de fallback implementadas | Registrar/testar ponte no cliente se esse canal for desejado |
| ATS live | Formulários controlados somente | Novo link explicitamente autorizado e validação do portal real, sem usar vagas de referência |
| Pesquisa salarial abrangente | Faixa estruturada da vaga/contexto privado | Fonte de pesquisa externa adequada e validação dos comparáveis por empresa/localidade/regime |
| Redação avançada | Template factual determinístico | Não há integração de IA nem redator universal de carta longa; não foi contratada API |
| Login/cadastro/magic link/MFA | Sessão privada e campo OTP básico | Adaptadores específicos testados; nunca contornar CAPTCHA/MFA |
| Retenção automática | Política/manual e backups testados | Sem expurgo agendado; revisão manual conforme política |

Nenhum desses itens é resolvido por um PID, healthcheck ou saída zero de teste. O serviço **não é declarado operacional em produção**. O registro da configuração no rascunho do ambiente não publica versão nem implanta produção. Revise/salve as alterações e publique o ambiente no produto quando desejar reusar a configuração de desenvolvimento; isso continua distinto de provisionar o serviço permanente.
