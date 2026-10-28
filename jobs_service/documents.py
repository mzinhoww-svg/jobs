"""Generate readable single-column files solely from traceable facts."""
import hashlib
import html
import json
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader
from .policy import Blocked, verified_fact
from .tailoring import tailor


def generate_documents(profile, job, output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    language=job.get('language','en')
    if language not in ('en','pt'):
        raise Blocked('DOCUMENT_LANGUAGE_UNSUPPORTED')
    localized={**profile,'facts':[{**f,'text':f.get('translations',{}).get(language,f['text'])} for f in profile.get('facts',[])]}
    facts,tailoring=tailor(localized,job)
    contact=' | '.join(str(profile.get(k)) for k in ('location','preferred_email','phone','linkedin') if profile.get(k))
    heading='Experiência profissional' if language=='pt' else 'Professional experience'
    cv=[profile['full_name'],('Objetivo: ' if language=='pt' else 'Target role: ')+job['title'],contact,
        'Resumo profissional' if language=='pt' else 'Professional summary']+[f['text'] for f in facts[:2]]+[heading]+[f['text'] for f in facts]
    if language=='pt':
        letter=[profile['full_name'],contact,f"Candidatura: {job['title']} — {job['company']}",
                'Prezada equipe de seleção,',
                f"Apresento minha candidatura à posição de {job['title']}. As contribuições abaixo são os pontos do meu histórico que mais se relacionam ao escopo publicado:"]
    else:
        letter=[profile['full_name'],contact,f"Application: {job['title']} — {job['company']}",
                'Dear hiring team,',
                f"I am applying for the {job['title']} position at {job['company']}. The following contributions from my background are relevant to the published scope:"]
    letter += [f['text'] for f in facts[:3]]
    matches=(tailoring.get('ai') or {}).get('matches',[])
    if matches:
        by_id={f['id']:f['text'] for f in facts}
        letter += ['Conexão com os requisitos publicados' if language=='pt' else 'Connection to published requirements']
        for match in matches[:3]:
            letter += [('Requisito publicado: ' if language=='pt' else 'Published requirement: ')+match['requirement'],by_id[match['fact_id']]]
    letter += ['Atenciosamente,' if language=='pt' else 'Kind regards,',profile['full_name']]
    result={}
    font=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    bold=font.with_name('DejaVuSans-Bold.ttf')
    if not font.exists() or not bold.exists(): raise Blocked('DOCUMENT_FONT_MISSING')
    pdfmetrics.registerFont(TTFont('JobsSans',str(font)))
    pdfmetrics.registerFont(TTFont('JobsSansBold',str(bold)))
    for prefix,lines in [('cv',cv),('cover-letter',letter)]:
        doc=Document()
        doc.styles['Normal'].font.name='Arial'
        doc.styles['Normal'].font.size=Pt(11)
        for i,line in enumerate(lines): doc.add_paragraph(line,style='Title' if i==0 else None)
        doc.save(output/(prefix+'.docx'))
        styles=getSampleStyleSheet()
        styles['Title'].fontName='JobsSansBold'
        styles['BodyText'].fontName='JobsSans'
        story=[]
        for i,line in enumerate(lines):
            story.extend([Paragraph(html.escape(line),styles['Title' if i==0 else 'BodyText']),Spacer(1,8)])
        pdf=output/(prefix+'.pdf')
        SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=40,bottomMargin=40).build(story)
        extracted='\n'.join(p.extract_text() for p in PdfReader(pdf).pages)
        # Round trip catches broken PDFs, character loss and missing identities/title.
        required_text=[profile['full_name'],job['title'],profile['preferred_email']]
        required_text.extend(f['text'] for f in facts if prefix=='cv')
        for required in required_text:
            if ' '.join(required.split()) not in ' '.join(extracted.split()): raise Blocked('DOCUMENT_PARSING_FAILED')
        (output/(prefix+'.txt')).write_text(extracted)
        for ext in ('pdf','docx'):
            path=output/(prefix+'.'+ext)
            path.chmod(0o600)
            result[path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    (output/'tailoring-report.json').write_text(json.dumps(tailoring,ensure_ascii=False,indent=2))
    (output/'tailoring-report.json').chmod(0o600)
    (output/'document-manifest.json').write_text(json.dumps({'documents':result,'fact_ids':[f['id'] for f in facts]},indent=2))
    return result
