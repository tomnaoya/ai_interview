import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_admin
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/jobs", response_class=HTMLResponse)
async def list_jobs(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    jobs = db.query(models.Job).join(models.Company).order_by(models.Job.created_at.desc()).all()
    return templates.TemplateResponse("admin/jobs.html", {
        "request": request, "admin": admin, "jobs": jobs, "active_page": "jobs"
    })


@router.get("/jobs/new", response_class=HTMLResponse)
async def new_job_form(
    request: Request, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/job_form.html", {
        "request": request, "admin": admin, "job": None,
        "companies": companies, "active_page": "jobs",
    })


def _parse_job_form(form_data: dict) -> dict:
    """Parse common form fields into job dict"""
    def safe_int(v, default=0):
        try: return int(v)
        except: return default

    def safe_json(v, default):
        try: return json.loads(v)
        except: return default

    expires_raw = form_data.get("expires_at", "")
    expires_at = None
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(expires_raw)
        except: pass

    return dict(
        title=form_data.get("title", ""),
        contact_email=form_data.get("contact_email", ""),
        expires_at=expires_at,
        interview_language=form_data.get("interview_language", "ja"),
        interview_type=form_data.get("interview_type", "avatar"),
        avatar_gender=form_data.get("avatar_gender", "female"),
        show_evaluation=(form_data.get("show_evaluation", "1") == "1"),
        share_result=(form_data.get("share_result", "0") == "1"),
        retry_count=safe_int(form_data.get("retry_count", 0)),
        score_answer=safe_int(form_data.get("score_answer", 70)),
        score_speaking=safe_int(form_data.get("score_speaking", 20)),
        score_posture=safe_int(form_data.get("score_posture", 10)),
        keywords=safe_json(form_data.get("keywords_json", "[]"), []),
        penalty_traits=safe_json(form_data.get("penalty_traits_json", "[]"), []),
        grade_criteria=safe_json(form_data.get("grade_criteria_json", "[]"), []),
        ai_role=form_data.get("ai_role", ""),
        ai_evaluation_prompt=form_data.get("ai_evaluation_prompt", ""),
        interview_title_ja=form_data.get("interview_title_ja", "面接"),
        interview_title_en=form_data.get("interview_title_en", "Interview"),
        interview_title_vi=form_data.get("interview_title_vi", "Phong van"),
        complete_title_ja=form_data.get("complete_title_ja", ""),
        complete_body_ja=form_data.get("complete_body_ja", ""),
        complete_title_en=form_data.get("complete_title_en", ""),
        complete_body_en=form_data.get("complete_body_en", ""),
        complete_title_vi=form_data.get("complete_title_vi", ""),
        complete_body_vi=form_data.get("complete_body_vi", ""),
        ai_questions=safe_json(form_data.get("ai_questions_json", "[]"), []),
        ai_max_turns=len(safe_json(form_data.get("ai_questions_json", "[]"), [])),
        company_id=safe_int(form_data.get("company_id", 0)),
        is_active=(form_data.get("is_active", "on") == "on"),
    )


@router.post("/jobs/new")
async def create_job(
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    form = await request.form()
    data = _parse_job_form(dict(form))
    job = models.Job(**data)
    db.add(job)
    db.commit()
    return RedirectResponse("/admin/jobs", status_code=302)


@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
async def edit_job_form(
    job_id: int, request: Request,
    db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(404)
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/job_form.html", {
        "request": request, "admin": admin, "job": job,
        "companies": companies, "active_page": "jobs",
    })


@router.post("/jobs/{job_id}/edit")
async def update_job(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(404)
    form = await request.form()
    data = _parse_job_form(dict(form))
    for k, v in data.items():
        setattr(job, k, v)
    db.commit()
    return RedirectResponse("/admin/jobs", status_code=302)


@router.post("/jobs/{job_id}/delete")
async def delete_job(
    job_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    job = db.query(models.Job).get(job_id)
    if job:
        job.is_active = False
        db.commit()
    return RedirectResponse("/admin/jobs", status_code=302)


@router.post("/jobs/{job_id}/issue-url")
async def issue_interview_url(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """応募者を自動登録して面接URLを発行する"""
    import secrets as _secrets
    from datetime import datetime as _dt

    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(404, "求人が見つかりません")

    body = await request.json()
    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    if not name or not email:
        raise HTTPException(400, "氏名とメールアドレスは必須です")

    # 応募者を登録（同じメール+求人があれば再利用）
    applicant = db.query(models.Applicant).filter(
        models.Applicant.email == email,
        models.Applicant.job_id == job_id,
    ).first()
    if not applicant:
        applicant = models.Applicant(
            company_id=job.company_id,
            job_id=job_id,
            name=name,
            name_kana=body.get("name_kana", ""),
            email=email,
            phone=body.get("phone", ""),
            status="interview_scheduled",
        )
        db.add(applicant)
        db.commit()
        db.refresh(applicant)

    # 面接レコード作成
    token = _secrets.token_urlsafe(32)
    interview = models.Interview(
        applicant_id=applicant.id,
        job_id=job_id,
        token=token,
        status="waiting",
    )
    db.add(interview)
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    return JSONResponse({
        "url": f"{base_url}/interview/{token}",
        "token": token,
        "applicant_id": applicant.id,
        "interview_id": interview.id,
    })
