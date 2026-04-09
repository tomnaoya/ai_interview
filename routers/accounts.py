from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_admin, get_password_hash
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/accounts", response_class=HTMLResponse)
async def list_accounts(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    accounts = db.query(models.CompanyAccount).join(models.Company).order_by(
        models.CompanyAccount.created_at.desc()
    ).all()
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/accounts.html", {
        "request": request, "admin": admin, "accounts": accounts,
        "companies": companies, "active_page": "accounts"
    })


@router.get("/accounts/new", response_class=HTMLResponse)
async def new_account_form(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/account_form.html", {
        "request": request, "admin": admin, "account": None,
        "companies": companies, "active_page": "accounts"
    })


@router.post("/accounts/new")
async def create_account(
    company_id: int = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(""),
    role: str = Form("user"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    existing = db.query(models.CompanyAccount).filter(models.CompanyAccount.email == email).first()
    if existing:
        raise HTTPException(400, "このメールアドレスは既に使用されています")
    account = models.CompanyAccount(
        company_id=company_id, email=email,
        password_hash=get_password_hash(password), name=name, role=role,
    )
    db.add(account)
    db.commit()
    return RedirectResponse("/admin/accounts", status_code=302)


@router.get("/accounts/{account_id}/edit", response_class=HTMLResponse)
async def edit_account_form(
    account_id: int, request: Request,
    db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    account = db.query(models.CompanyAccount).get(account_id)
    if not account:
        raise HTTPException(404)
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/account_form.html", {
        "request": request, "admin": admin, "account": account,
        "companies": companies, "active_page": "accounts"
    })


@router.post("/accounts/{account_id}/edit")
async def update_account(
    account_id: int,
    company_id: int = Form(...),
    email: str = Form(...),
    password: str = Form(""),
    name: str = Form(""),
    role: str = Form("user"),
    is_active: str = Form("on"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    account = db.query(models.CompanyAccount).get(account_id)
    if not account:
        raise HTTPException(404)
    account.company_id = company_id
    account.email = email
    account.name = name
    account.role = role
    account.is_active = (is_active == "on")
    if password:
        account.password_hash = get_password_hash(password)
    db.commit()
    return RedirectResponse("/admin/accounts", status_code=302)


@router.post("/accounts/{account_id}/delete")
async def delete_account(
    account_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    account = db.query(models.CompanyAccount).get(account_id)
    if account:
        account.is_active = False
        db.commit()
    return RedirectResponse("/admin/accounts", status_code=302)
