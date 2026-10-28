"""Explain lexical evidence matching; never invent candidate facts or ATS scores."""
import re
import unicodedata
from collections import Counter
from .policy import verified_fact

STOP=set('the and with for from that this have will your our are you into across their experience role team teams work working responsibilities qualifications required preferred position skills years knowledge ability sobre para como uma um dos das com por seu sua voce nos mais pela pelo aos nas sao ser ter experiencia cargo vaga empresa equipe anos requisitos responsabilidades desejavel conhecimento habilidades'.split())
SYNONYMS={'payments':'payment','pagamento':'payment','pagamentos':'payment','partnerships':'partner','partners':'partner','parceria':'partner','parcerias':'partner','partner':'partner','products':'product','produto':'product','produtos':'product','operacoes':'operation','operations':'operation','operation':'operation','estrategia':'strategy','strategic':'strategy','estrategico':'strategy','lideranca':'leadership','gestao':'management','financial':'finance','financeiro':'finance','financeira':'finance'}


def terms(text):
    text=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()
    return [SYNONYMS.get(t,t) for t in re.findall(r'[a-z][a-z0-9+#.-]{2,}',text) if t not in STOP]


def tailor(profile,job):
    facts=[f for f in profile.get('facts',[]) if verified_fact(f)]
    counts=Counter(terms(job.get('title','')+' '+job.get('description','')))
    keywords=[t for t,_ in counts.most_common(30)]
    by_id={f['id']:set(terms(f['text'])) for f in facts}
    ranked=sorted(facts,key=lambda f:-sum(counts[t] for t in by_id[f['id']] if t in counts))
    ai=job.get('ai_selection')
    if ai:
        order={id:index for index,id in enumerate(ai['ranked_fact_ids'])}
        ranked=sorted(ranked,key=lambda f:order.get(f['id'],len(order)))
    matches=[{'term':t,'fact_ids':[f['id'] for f in ranked if t in by_id[f['id']]]} for t in keywords]
    return ranked,{'method':'ai_evidence_ranking' if ai else 'lexical_evidence_matching','ai':{k:ai[k] for k in ('provider','model','matches')} if ai else None,'ai_error':job.get('ai_error'),'ats':job.get('ats','DESCONHECIDO'),
        'target':{'title':job['title'],'company':job['company'],'language':job.get('language','en')},
        'matched':[m for m in matches if m['fact_ids']],
        'not_evidenced':[m['term'] for m in matches if not m['fact_ids']],
        'selected_fact_ids':[f['id'] for f in ranked[:3]],
        'evidence':[{'id':f['id'],'text':f['text']} for f in ranked],
        'checks':{'single_column':True,'no_tables':True,'extractable_text':True,'verified_facts_only':True},
        'limitations':['Correspondencia lexical nao comprova atendimento integral de um requisito.','Nao e uma nota ATS nem garantia de aprovacao.','Fatos permanecem no idioma original; nao ha traducao automatica de qualificacoes.','Revise documentos e requisitos antes de enviar; use o formato aceito no portal.']}
