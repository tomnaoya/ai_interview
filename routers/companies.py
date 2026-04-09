import os, shutil
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, DATA_DIR
from auth import get_current_admin
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads", "logos")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("/companies", response_class=HTMLResponse)
async def list_companies(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    companies = db.query(models.Company).order_by(models.Company.created_at.desc()).all()
    return templates.TemplateResponse("admin/companies.html", {
        "request": request, "admin": admin, "companies": companies, "active_page": "companies"
    })


@router.get("/companies/new", response_class=HTMLResponse)
async def new_company_form(
    request: Request, admin=Depends(get_current_admin)
):
    return templates.TemplateResponse("admin/company_form.html", {
        "request": request, "admin": admin, "company": None, "active_page": "companies"
    })


@router.post("/companies/new")
async def create_company(
    request: Request,
    name: str = Form(...),
    name_kana: str = Form(""),
    industry: str = Form(""),
    size: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    description: str = Form(""),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    logo_path = None
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1]
        filename = f"{os.urandom(8).hex()}{ext}"
        dest = os.path.join(UPLOAD_DIR, filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(logo.file, f)
        logo_path = f"/uploads/logos/{filename}"

    company = models.Company(
        name=name, name_kana=name_kana, industry=industry, size=size,
        address=address, phone=phone, website=website, description=description,
        logo_path=logo_path,
    )
    db.add(company)
    db.commit()
    return RedirectResponse("/admin/companies", status_code=302)


@router.get("/companies/{company_id}/edit", response_class=HTMLResponse)
async def edit_company_form(
    company_id: int, request: Request,
    db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(404)
    return templates.TemplateResponse("admin/company_form.html", {
        "request": request, "admin": admin, "company": company, "active_page": "companies"
    })


@router.post("/companies/{company_id}/edit")
async def update_company(
    company_id: int,
    request: Request,
    name: str = Form(...),
    name_kana: str = Form(""),
    industry: str = Form(""),
    size: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
    website: str = Form(""),
    description: str = Form(""),
    is_active: str = Form("on"),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    company = db.query(models.Company).get(company_id)
    if not company:
        raise HTTPException(404)
    company.name = name
    company.name_kana = name_kana
    company.industry = industry
    company.size = size
    company.address = address
    company.phone = phone
    company.website = website
    company.description = description
    company.is_active = (is_active == "on")
    if logo and logo.filename:
        ext = os.path.splitext(logo.filename)[1]
        filename = f"{os.urandom(8).hex()}{ext}"
        dest = os.path.join(UPLOAD_DIR, filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(logo.file, f)
        company.logo_path = f"/uploads/logos/{filename}"
    db.commit()
    return RedirectResponse("/admin/companies", status_code=302)


@router.post("/companies/{company_id}/delete")
async def delete_company(
    company_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    company = db.query(models.Company).get(company_id)
    if company:
        company.is_active = False
        db.commit()
    return RedirectResponse("/admin/companies", status_code=302)
