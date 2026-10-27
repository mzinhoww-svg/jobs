"""Safe dashboard views. Never return raw pages, profiles, sessions or credentials."""
import json


def payload(row):
    try:
        value=json.loads(row['payload'])
        return value if isinstance(value,dict) else {}
    except (TypeError,ValueError):
        return {}


def result_view(row):
    data=payload(row)
    job=data.get('job') if isinstance(data.get('job'),dict) else {}
    salary=data.get('salary') if isinstance(data.get('salary'),dict) else {}
    result={'job':{k:job[k] for k in ('title','company','country','language') if k in job},
            'ats':data.get('ats'),'documents':data.get('documents',{}),'proof':data.get('proof')}
    result['salary']={k:salary[k] for k in ('chosen','currency','period','kind','sources','rationale') if k in salary}
    return result


def summary(row):
    result=result_view(row)
    return {**{k:row[k] for k in ('id','url','status','reason','mode','created','updated','attempts')},
            'job':result['job'],'ats':result['ats'],
            'has_documents':bool(result['documents']),
            'has_proof':row['status']=='ENVIADA_COMPROVADA' and bool(result['proof']),
            'can_resume':not row['intent'] and row['owner'] is None and row['status'] in ('BLOQUEADA','AGUARDANDO_VERIFICACAO','DOCUMENTOS_PRONTOS')}
