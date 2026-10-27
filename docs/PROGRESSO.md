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
