import hashlib, os, secrets, uuid
from pathlib import Path
from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select
from reportlab.pdfgen import canvas
from .models import Base,engine,SessionLocal,Case,Evidence,Analysis,Review
from .pipeline import classify,redact,transcribe_media

app=FastAPI(title='SafeWatch AI MVP',version='0.1.0')
Base.metadata.create_all(bind=engine)  # MVP only: switch to Alembic migrations for production
UPLOAD_DIR=Path(os.getenv('UPLOAD_DIR','./uploads')); UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
MAX_BYTES=100*1024*1024
ALLOWED={'.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime','.mp3':'audio/mpeg','.wav':'audio/wav','.m4a':'audio/mp4'}
def session():
    with SessionLocal() as db: yield db

def auth(x_api_key: str|None=Header(None)):
    key=os.getenv('APP_API_KEY','change-me-before-deploying')
    admin=os.getenv('ADMIN_API_KEY','admin-change-me-before-deploying')
    if not x_api_key or not any(secrets.compare_digest(x_api_key,k) for k in (key,admin)):
        raise HTTPException(401,'Invalid API key')
    return 'admin' if secrets.compare_digest(x_api_key,admin) else 'user'
def admin(role=Depends(auth)):
    if role!='admin': raise HTTPException(403,'Reviewer access required')
    return role
class CaseIn(BaseModel):
    title: str=Field(min_length=3,max_length=200)
    url: str|None=None
    description: str=Field(default='',max_length=10000)
class AnalyzeIn(BaseModel):
    supplied_transcript: str=Field(default='',max_length=50000,description='Optional human-provided transcript')
class ReviewIn(BaseModel):
    reviewer: str=Field(min_length=2,max_length=100)
    decision: str=Field(pattern='^(approve|reject|needs_context)$')
    rationale: str=Field(min_length=5,max_length=10000)
def case_or_404(db,id):
    case=db.get(Case,id)
    if not case: raise HTTPException(404,'Case not found')
    return case
def serialize(c):
    return {'id':c.id,'title':c.title,'url':c.url,'description':c.description,'status':c.status,'created_at':c.created_at.isoformat(),
            'evidence':[{'id':e.id,'filename':e.filename,'bytes':e.bytes,'sha256':e.sha256} for e in c.evidence],
            'analysis':None if not c.analysis else {'transcript':redact(c.analysis.transcript),'language':c.analysis.language,'tags':c.analysis.tags,'indicators':c.analysis.indicators,'notes':c.analysis.model_notes},
            'reviews':[{'id':r.id,'reviewer':r.reviewer,'decision':r.decision,'rationale':redact(r.rationale),'created_at':r.created_at.isoformat()} for r in c.reviews]}
@app.get('/api/health')
def health():return {'status':'ok'}
@app.post('/api/cases',status_code=201)
def create_case(data:CaseIn,db:Session=Depends(session),_=Depends(auth)):
    if data.url:
        parsed=urlparse(data.url)
        if parsed.scheme!='https' or (parsed.hostname or '').lower() not in ('tiktok.com','www.tiktok.com','vm.tiktok.com','vt.tiktok.com','m.tiktok.com'):
            raise HTTPException(422,'Enter a valid TikTok HTTPS URL')
    c=Case(**data.model_dump());db.add(c);db.commit();db.refresh(c);return serialize(c)
@app.get('/api/cases')
def list_cases(db:Session=Depends(session),_=Depends(auth)):
    return [serialize(c) for c in db.scalars(select(Case).order_by(Case.id.desc())).all()]
@app.get('/api/cases/{case_id}')
def get_case(case_id:int,db:Session=Depends(session),_=Depends(auth)):
    return serialize(case_or_404(db,case_id))
@app.post('/api/cases/{case_id}/evidence',status_code=201)
async def upload_evidence(case_id:int,file:UploadFile=File(...),db:Session=Depends(session),_=Depends(auth)):
    c=case_or_404(db,case_id)
    extension=Path(file.filename or '').suffix.lower()
    if extension not in ALLOWED: raise HTTPException(415,'Unsupported media extension')
    if file.content_type not in (ALLOWED[extension],'application/octet-stream'):
        raise HTTPException(415,'Unsupported media MIME type')
    dest=UPLOAD_DIR / f'{uuid.uuid4().hex}{extension}';total=0;digest=hashlib.sha256()
    try:
        with dest.open('wb') as out:
            while chunk:=await file.read(1024*1024):
                total+=len(chunk)
                if total>MAX_BYTES: raise HTTPException(413,'100MB maximum')
                digest.update(chunk);out.write(chunk)
        if total==0: raise HTTPException(422,'Empty file')
        # In production also verify media container via ffprobe and malware scan.
        e=Evidence(case_id=c.id,filename=Path(file.filename or 'upload').name[:255],path=str(dest),sha256=digest.hexdigest(),bytes=total,media_type=ALLOWED[extension])
        db.add(e);db.commit();db.refresh(e)
        return {'id':e.id,'filename':e.filename,'bytes':total,'sha256':e.sha256}
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally: await file.close()
@app.post('/api/cases/{case_id}/analyze')
def analyze(case_id:int,payload:AnalyzeIn,db:Session=Depends(session),_=Depends(auth)):
    c=case_or_404(db,case_id)
    if not c.evidence and not payload.supplied_transcript.strip(): raise HTTPException(400,'Upload media or supply transcript')
    transcript=payload.supplied_transcript.strip();language='manual';notes='Human-supplied transcript; check against original video.'
    if not transcript and c.evidence:
        transcript,language,notes=transcribe_media(c.evidence[-1].path)
    result=classify(transcript)
    if not c.analysis:
        c.analysis=Analysis(case_id=c.id)
    c.analysis.transcript=transcript;c.analysis.language=language;c.analysis.tags=result['tags'];c.analysis.indicators=result['indicators'];c.analysis.model_notes=notes+' '+result['notes']
    c.status='needs_review';db.commit();db.refresh(c);return serialize(c)
@app.post('/api/cases/{case_id}/review')
def review(case_id:int,data:ReviewIn,db:Session=Depends(session),_=Depends(admin)):
    c=case_or_404(db,case_id)
    if not c.analysis: raise HTTPException(409,'Analyze before review')
    db.add(Review(case_id=case_id,**data.model_dump()))
    c.status={'approve':'approved','reject':'rejected','needs_context':'needs_context'}[data.decision]
    db.commit();db.refresh(c);return serialize(c)
@app.get('/api/cases/{case_id}/report.pdf')
def report(case_id:int,db:Session=Depends(session),_=Depends(auth)):
    c=case_or_404(db,case_id)
    if c.status!='approved' or not c.reviews or c.reviews[-1].decision!='approve':
        raise HTTPException(409,'Reviewer approval required before report export')
    buffer=BytesIO();pdf=canvas.Canvas(buffer,pagesize=(595,842));y=795
    def line(s):
        nonlocal y
        if y<75: pdf.showPage();y=795
        pdf.drawString(48,y, ''.join(ch if ord(ch)<128 else '?' for ch in s)[:100]);y-=18
    pdf.setFont('Helvetica',10)
    for s in ['SafeWatch AI - Human reviewed evidence summary',f'Case ID: {c.id}',f'Title: {redact(c.title)}',f'Status: {c.status}',f'URL: {c.url or "None"}', 'Potential indicators (not a platform moderation decision):']:
        line(s)
    for tag in c.analysis.tags if c.analysis else []: line(' - '+tag)
    line('Evidence SHA-256:')
    for e in c.evidence: line(e.sha256)
    line('Human review: '+ c.reviews[-1].decision)
    line('Rationale: '+redact(c.reviews[-1].rationale))
    line('Submit via official TikTok reporting interface. No automated takedown.')
    pdf.save();buffer.seek(0)
    return StreamingResponse(buffer,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="safewatch-case-{case_id}.pdf"'})
