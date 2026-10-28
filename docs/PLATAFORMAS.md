# Cobertura de plataformas e documentos

Objetivo: permitir preparar documentos para vagas de qualquer plataforma, com entrada manual da descrição quando a leitura automática não estiver disponível. O envio permanece limitado ao adaptador comprovado; preparação nunca será apresentada como candidatura enviada.

Decisão de implementação: manter Python/FastAPI/Playwright, ampliar identificação de ATS e leitura dos domínios conhecidos, incluir descrição manual sem navegação externa, gerar relatório de correspondência entre requisitos e fatos confirmados e pacote para download. Não usar reescrita sem evidências nem percentuais de aprovação. Nenhum serviço no computador pessoal é necessário.

Plano:
- [x] Testar identificação de plataformas e persistência de descrição manual sem contornar restrições de rede.
- [x] Separar preparação de documentos da disponibilidade do adaptador de envio; produzir fallback e histórico explícitos.
- [x] Gerar documentos e relatório de aderência rastreável e pacote ZIP; testar conteúdo extraído e ausência de dados internos no pacote.
- [x] Expor opções no painel e validar fluxo real no Chromium.
- [x] Executar suíte completa, revisar e publicar; atualização da VPS é etapa distinta.

Limites: páginas com login, CAPTCHA ou conteúdo inacessível exigem descrição colada ou interação humana no portal. Apenas identificar um ATS não implementa seu envio. Nenhuma nota ATS ou promessa de aprovação será exibida. A descrição da vaga nunca autoriza inventar histórico, autorizações legais, certificados ou idiomas. Sem perfil confirmado não é possível produzir um CV verdadeiro.

## Implementação 0.3

| Portal | Leitura da URL | CV/carta e relatório | Envio automático |
|---|---|---|---|
| Greenhouse | Chromium; iframe/requisição identificados | PDF + DOCX + ZIP | Adaptador existente, testes controlados |
| Workday, Lever, Ashby, Gupy, SmartRecruiters | Leitor público; depende do acesso ao anúncio | Mesma preparação | Não implementado; envio manual |
| iCIMS, Taleo, SuccessFactors, LinkedIn, Indeed | Leitor público; login/bloqueios podem impedir leitura | Mesma preparação | Não implementado; envio manual |
| Site próprio ou outro ATS | Leitor público; domínio privado proibido | Mesma preparação | Não implementado; envio manual |

“Leitura” descreve o mecanismo implementado, não uma certificação de compatibilidade com cada portal. Quando o anúncio não for público ou legível, a descrição manual é o fallback. Não há contorno de CAPTCHA nem uso do Chrome do computador pessoal. O Chromium é remoto, com contexto novo para leitura, sem cookies de candidatura, apenas GET e sem WebSocket. Cada destino é verificado e fixado em IP público, mantendo Host e TLS SNI. A leitura direta requer saída HTTPS funcional; proxies que não preservem SNI ao conectar por IP podem impedir a leitura. Tavily é opcional, via API HTTPS no serviço; nenhum MCP Tavily está instalado nesta sessão.

## IA

`deepseek/deepseek-v4.1-flash` foi confirmado nos catálogos oficiais de OpenRouter e AI Gateway. Ambos têm cliente implementado. O modelo extrai metadados e ordena fatos confirmados, vinculando evidências a citações literais da vaga. Não recebe token do painel, cookies ou contatos pessoais; não tem ferramentas de shell/browser e não pode inventar novas qualificações nos documentos. A composição usa evidências canônicas e traduções privadas, sem prometer aprovação ATS.

A IA só é ativada com configuração privada explícita. Chave configurada no ChatGPT/Codex não é automaticamente instalada na VPS. `bash deploy/configure-ai.sh openrouter` verifica a instalação existente, reutiliza a imagem 0.3 e pede a chave com entrada oculta, faz uma chamada real com dados sintéticos e só então grava `/var/lib/jobs/ai-config.json` com permissão 0600. Para usar o outro provedor: `bash deploy/configure-ai.sh gateway`. A configuração permanece no volume privado, fora do Git, e a próxima tarefa já a utiliza. Chamadas ao provedor podem consumir os créditos da conta. Em um painel sem autenticação, visitantes também podem disparar essas tarefas.

O teste real com a credencial AI Gateway disponível nesta sessão foi recusado por autenticação. Catálogo público acessível não comprova uma chave válida. A chave OpenRouter anunciada pelo usuário não estava exposta como `OPENROUTER_API_KEY` no executor no momento da verificação. A ativação na VPS permanece dependente de uma credencial válida; não declarar a IA operacional até `AI_CONFIGURED` e uma vaga processada com sucesso.

## Perfil privado

Dados pessoais não fazem parte deste repositório. `bash deploy/import-profile.sh /caminho/privado/profile.json` importa um perfil fora do checkout para o volume já instalado, preservando cópia da versão anterior. O perfil deve ter identidade e fatos confirmados com proveniência. Cargos, datas, idiomas e métricas de referência continuam pendentes quando não confirmados. Sem SSH funcional, preparar o arquivo no executor não comprova a importação na VPS.
