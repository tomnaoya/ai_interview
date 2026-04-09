from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_admin
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")

DEFAULT_POLICY = """# プライバシーポリシー

## 1. 個人情報の収集について
当システムでは、採用面接サービスの提供に必要な範囲で個人情報を収集します。

## 2. 収集する情報
- 氏名、連絡先情報（電話番号、メールアドレス）
- 学歴・職歴情報
- 面接の録音・記録（テキスト形式）
- 面接評価データ

## 3. 利用目的
収集した個人情報は以下の目的に使用します：
- 採用選考の実施と評価
- 採用担当者への情報提供
- サービスの改善

## 4. 第三者提供
収集した個人情報は、法令に基づく場合を除き、第三者に提供しません。

## 5. 安全管理
収集した個人情報は適切なセキュリティ措置を講じて管理します。

## 6. 保存期間
面接データは面接完了後1年間保存します。

## 7. 問い合わせ
個人情報に関するお問い合わせは、各企業の担当者までご連絡ください。
"""


@router.get("/privacy", response_class=HTMLResponse)
async def list_policies(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    policies = db.query(models.PrivacyPolicy).order_by(models.PrivacyPolicy.updated_at.desc()).all()
    return templates.TemplateResponse("admin/privacy.html", {
        "request": request, "admin": admin, "policies": policies, "active_page": "privacy"
    })


@router.get("/privacy/new", response_class=HTMLResponse)
async def new_policy_form(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/privacy_form.html", {
        "request": request, "admin": admin, "policy": None,
        "companies": companies, "default_content": DEFAULT_POLICY, "active_page": "privacy"
    })


@router.post("/privacy/new")
async def create_policy(
    title: str = Form(...),
    content: str = Form(...),
    version: str = Form("1.0"),
    company_id: str = Form(""),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    policy = models.PrivacyPolicy(
        title=title, content=content, version=version,
        company_id=int(company_id) if company_id else None,
    )
    db.add(policy)
    db.commit()
    return RedirectResponse("/admin/privacy", status_code=302)


@router.get("/privacy/{policy_id}/edit", response_class=HTMLResponse)
async def edit_policy_form(
    policy_id: int, request: Request,
    db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    policy = db.query(models.PrivacyPolicy).get(policy_id)
    if not policy:
        raise HTTPException(404)
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/privacy_form.html", {
        "request": request, "admin": admin, "policy": policy,
        "companies": companies, "default_content": DEFAULT_POLICY, "active_page": "privacy"
    })


@router.post("/privacy/{policy_id}/edit")
async def update_policy(
    policy_id: int,
    title: str = Form(...),
    content: str = Form(...),
    version: str = Form("1.0"),
    company_id: str = Form(""),
    is_active: str = Form("on"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    policy = db.query(models.PrivacyPolicy).get(policy_id)
    if not policy:
        raise HTTPException(404)
    policy.title = title
    policy.content = content
    policy.version = version
    policy.company_id = int(company_id) if company_id else None
    policy.is_active = (is_active == "on")
    db.commit()
    return RedirectResponse("/admin/privacy", status_code=302)


@router.post("/privacy/{policy_id}/delete")
async def delete_policy(
    policy_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    policy = db.query(models.PrivacyPolicy).get(policy_id)
    if policy:
        db.delete(policy)
        db.commit()
    return RedirectResponse("/admin/privacy", status_code=302)
