# Progresso

- Pacote privado extraído fora do checkout; 11 hashes verificados.
- Três documentos principais lidos integralmente; referências DOCX extraídas e lidas.
- Auditoria estática dos seis projetos apresentada antes da instalação. Nenhum código externo será importado.
- Escolha: Python/FastAPI/SQLite/Playwright, execução própria nesta sessão.
- Bloqueios observados: sem identidade de implantação ou Gmail; Git API retorna Forbidden, Git HTTPS leitura funciona.
- Repositório aparece como repository_public na página HTML: publicar somente código/docs/exemplos sintéticos conforme pedido direto; anexos recomendam privado, mas não alteram visibilidade por si.

## Implementação e validação

- Primeiro commit c9dd17b: ignore policy, auditoria e plano, antes de adicionar código.
- Implementados API autenticada/interface mínima, SQLite/eventos, worker único, sessões privadas, adaptador Greenhouse restrito, documentos PDF/DOCX, salário estruturado e Gmail read-only.
- TDD: primeiros testes falharam por módulos ausentes; testes de regressão da revisão falharam nos comportamentos correspondentes e passaram após as correções.
- 35 testes aprovados no host e container, incluindo Chromium sem rede externa e fluxo integrado controlado.
- Imagem Docker construída; Compose de desenvolvimento iniciou API/worker saudáveis. Backup/restauração aprovados. Snapshot de volume/reinício verificado separadamente.
- Revisão independente e decisões/limitações em VALIDACAO.md. Não refazer auditoria dos seis projetos sem mudança dos SHAs/escopo.
- Dados reais e ZIP em diretórios privados externos ao checkout; perfil canônico preserva origem e categorias, exemplos/histórico de referência não foram enfileirados.
- Continuar por destino de implantação autorizado e OAuth Gmail; não transformar ambiente temporário em alegação de produção. Sem novo link, manter testes apenas controlados.

## Retomada LetsCloud — 27/10/2026

- Checkout existente preservado e inicialmente limpo em `f623a2fd99ec3ec6d9534aebd3429ac1eecae411`, igual à `main` remota consultada. Nenhuma reconstrução ou candidatura real.
- Ambiente gerenciado iniciou após espera. As seis variáveis solicitadas estão presentes e com observação `ready`; nenhum valor foi registrado. A skill solicitada `cloud-environment-onboarding:setup` não foi encontrada no catálogo nem nos locais de skills pesquisados; foi usada a skill disponível `cloud-environment:cloud-environment-runtime` para a inspeção.
- HTTP/HTTPS está `unrestricted/enforced`, mas `tcp_network_access.domains` e `ip_ranges` estão vazios e VPN não está configurada. A conexão ao proxy TCP configurado (`proxy:8088`) falhou com `ConnectionRefusedError`, antes de alcançar SSH da VPS. Não houve contorno da política.
- `SSH_PRIVATE_KEY` presente, mas `ssh-keygen -y -P ''` não conseguiu carregar seu conteúdo como chave privada. Não há `known_hosts` de usuário/sistema nos caminhos padrão verificados. Senha presente, porém não testada contra a VPS porque não há transporte SSH permitido/disponível; a autenticação remota permanece desconhecida. Não desativar verificação de identidade.
- API oficial documentada: `GET https://core.letscloud.io/api/instances`, header `api-token`, retornou HTTP 200 e `success=true`; detalhes da instância também consultados por GET. VPS correspondente ligada, construída, desbloqueada, 1 vCPU, 2048 MB RAM, disco provisionado de 50 GB. Isso não mede disco livre nem prova saúde interna.
- 35 testes novamente aprovados no host e 35 na imagem existente `jobs-service:local`, esta sem rede externa; Chromium, autenticação, documentos, backup/restore e recuperação sem reenvio incluídos. Containers de desenvolvimento existentes preservados; não representam implantação LetsCloud.
- Perfil preparado encontrado em `/workspace/jobs-private-runtime/profile.json`, JSON válido, arquivo 0600/diretório 0700; fila íntegra e vazia. Fontes/documentos em `/workspace/private-onboarding`, pacote em `/workspace/attachments`. Nada disso foi copiado ao Git nem substituído por exemplos.
- Nenhum `gmail-oauth.json` encontrado na busca sob `/workspace`. Sem acesso interno à VPS, não foi possível verificar se existe OAuth lá. Gmail real segue não testado.
- Continuação: corrigir disponibilidade do transporte TCP autorizado até a porta SSH da VPS, disponibilizar chave privada parseável pelo canal de segredos e identidade de host confiável; depois inspecionar SO/serviços/portas/firewall/domínios antes de implantar. Não há endereço privado HTTPS validado. Ver OPERACAO e VALIDACAO.
