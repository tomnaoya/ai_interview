import os, shutil, secrets
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, DATA_DIR
from auth import get_current_admin
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")
RESUME_DIR = os.path.join(DATA_DIR, "uploads", "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)


@router.get("/applicants", response_class=HTMLResponse)
async def list_applicants(
    request: Request,
    company_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    query = db.query(models.Applicant).join(models.Company)
    if company_id:
        query = query.filter(models.Applicant.company_id == company_id)
    if status:
        query = query.filter(models.Applicant.status == status)
    applicants = query.order_by(models.Applicant.created_at.desc()).all()
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/applicants.html", {
        "request": request, "admin": admin, "applicants": applicants,
        "companies": companies, "active_page": "applicants",
        "filter_company": company_id, "filter_status": status,
    })


@router.get("/applicants/new", response_class=HTMLResponse)
async def new_applicant_form(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    jobs = db.query(models.Job).filter(models.Job.is_active == True).all()
    return templates.TemplateResponse("admin/applicant_form.html", {
        "request": request, "admin": admin, "applicant": None,
        "companies": companies, "jobs": jobs, "active_page": "applicants"
    })


@router.post("/applicants/new")
async def create_applicant(
    request: Request,
    company_id: int = Form(...),
    job_id: str = Form(""),
    name: str = Form(...),
    name_kana: str = Form(""),
    email: str = Form(...),
    phone: str = Form(""),
    birth_date: str = Form(""),
    address: str = Form(""),
    education: str = Form(""),
    work_experience: str = Form(""),
    notes: str = Form(""),
    resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    resume_path = None
    if resume and resume.filename:
        ext = os.path.splitext(resume.filename)[1]
        filename = f"{os.urandom(8).hex()}{ext}"
        dest = os.path.join(RESUME_DIR, filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(resume.file, f)
        resume_path = f"/uploads/resumes/{filename}"

    applicant = models.Applicant(
        company_id=company_id,
        job_id=int(job_id) if job_id else None,
        name=name, name_kana=name_kana, email=email, phone=phone,
        birth_date=birth_date, address=address, education=education,
        work_experience=work_experience, notes=notes, resume_path=resume_path,
    )
    db.add(applicant)
    db.commit()
    return RedirectResponse("/admin/applicants", status_code=302)


@router.get("/applicants/{applicant_id}", response_class=HTMLResponse)
async def view_applicant(
    applicant_id: int, request: Request,
    db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    applicant = db.query(models.Applicant).get(applicant_id)
    if not applicant:
        raise HTTPException(404)
    interviews = db.query(models.Interview).filter(
        models.Interview.applicant_id == applicant_id
    ).order_by(models.Interview.created_at.desc()).all()
    jobs = db.query(models.Job).filter(
        models.Job.company_id == applicant.company_id,
        models.Job.is_active == True,
    ).all()
    return templates.TemplateResponse("admin/applicant_detail.html", {
        "request": request, "admin": admin, "applicant": applicant,
        "interviews": interviews, "jobs": jobs, "active_page": "applicants"
    })


@router.post("/applicants/{applicant_id}/interview-link")
async def create_interview_link(
    applicant_id: int,
    request: Request,
    job_id: int = Form(...),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    token = secrets.token_urlsafe(32)
    interview = models.Interview(
        applicant_id=applicant_id, job_id=job_id, token=token, status="waiting"
    )
    db.add(interview)
    db.commit()
    base_url = str(request.base_url).rstrip("/")
    link = f"{base_url}/interview/{token}"
    return JSONResponse({"link": link, "interview_id": interview.id})


@router.post("/applicants/{applicant_id}/edit")
async def update_applicant(
    applicant_id: int,
    company_id: int = Form(...),
    job_id: str = Form(""),
    name: str = Form(...),
    name_kana: str = Form(""),
    email: str = Form(...),
    phone: str = Form(""),
    birth_date: str = Form(""),
    address: str = Form(""),
    education: str = Form(""),
    work_experience: str = Form(""),
    notes: str = Form(""),
    status: str = Form("pending"),
    resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    applicant = db.query(models.Applicant).get(applicant_id)
    if not applicant:
        raise HTTPException(404)
    applicant.company_id = company_id
    applicant.job_id = int(job_id) if job_id else None
    applicant.name = name
    applicant.name_kana = name_kana
    applicant.email = email
    applicant.phone = phone
    applicant.birth_date = birth_date
    applicant.address = address
    applicant.education = education
    applicant.work_experience = work_experience
    applicant.notes = notes
    applicant.status = status
    if resume and resume.filename:
        ext = os.path.splitext(resume.filename)[1]
        filename = f"{os.urandom(8).hex()}{ext}"
        dest = os.path.join(RESUME_DIR, filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(resume.file, f)
        applicant.resume_path = f"/uploads/resumes/{filename}"
    db.commit()
    return RedirectResponse(f"/admin/applicants/{applicant_id}", status_code=302)
