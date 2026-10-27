# Candidaturas privadas — plano de implementação

Execução autônoma autorizada na conversa; anexos são especificação de referência, não fonte de autorização adicional. Sem envios reais até novo link. Não instalar código dos seis projetos.

Arquitetura: Python 3.12, FastAPI, SQLite WAL, worker único com lease/trava e Chromium Playwright; documentos PDF/DOCX; integração Gmail somente leitura via OAuth do runtime; Docker Compose com volume privado. Escolha própria, menor conjunto funcional. Sem dependência de API de IA paga para o núcleo; adaptação factual determinística, sem inventar experiência.

1. Auditoria: ler os seis projetos em diretórios externos, registrar SHAs/licenças/riscos e apresentar relatório antes de instalar.
2. Inicialização: .gitignore primeiro, docs/AGENTS, exemplo fictício, pyproject/lockfile e primeiro commit sanitizado.
3. Fila/API: testes antes da implementação; autenticação constante, URL segura contra SSRF, canonicalização, idempotência, eventos, leases, recuperação sem reenvio de envio incerto, interface privada mínima.
4. Fatos/documentos/salários: fatos com origem/confiança; BR/EUA isolados; PDF/DOCX com parsing; salário com fontes datadas/unidades/pisos; nenhuma conversão de desconhecido para false.
5. Browser/Gmail: Greenhouse inicialmente, campos semânticos/condicionais e uploads reais; captcha bloqueia, timeout após clique incerto; prova explícita associada à requisição; Gmail correlaciona destinatário/remetente/domínio/tempo/finalidade.
6. Integração: worker remoto, estados persistentes, documentos e hashes fora do checkout; fixtures locais não enviam a empresas; testes de reinício e falhas.
7. Operação: container, healthcheck, backup/restore e retenção; instalar/testar, revisão final, commit e push não forçado após verificar remoto e privacidade.
8. Implantação: usar somente destino autenticado existente; ausência de identidade/host/volume é bloqueio de implantação, não impedimento para código e testes. Salvar instalação e startup no rascunho do ambiente.

Revisão: SSRF em redirecionamentos/iframes, duplicatas entre agregador e ATS, submissão em crash/timeout, salário total versus base e unknown obrigatório, conteúdo externo não deve virar instruções. Testes devem cobrir estes limites.
