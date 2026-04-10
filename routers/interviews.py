from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from database import get_db
from auth import get_current_admin
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _load_interview(db: Session, interview_id: int):
    return db.query(models.Interview).options(
        joinedload(models.Interview.applicant).joinedload(models.Applicant.company),
        joinedload(models.Interview.job).joinedload(models.Job.company),
        joinedload(models.Interview.messages),
    ).filter(models.Interview.id == interview_id).first()


@router.get("/interview-history", response_class=HTMLResponse)
async def list_interviews(
    request: Request,
    company_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    query = db.query(models.Interview).options(
        joinedload(models.Interview.applicant).joinedload(models.Applicant.company),
        joinedload(models.Interview.job),
    )
    if company_id:
        query = query.join(models.Applicant).filter(models.Applicant.company_id == company_id)
    if status:
        query = query.filter(models.Interview.status == status)
    interviews = query.order_by(models.Interview.created_at.desc()).all()
    companies = db.query(models.Company).filter(models.Company.is_active == True).all()
    return templates.TemplateResponse("admin/interviews.html", {
        "request": request, "admin": admin, "interviews": interviews,
        "companies": companies, "active_page": "interviews",
        "filter_company": company_id, "filter_status": status,
    })


@router.get("/interview-history/{interview_id}", response_class=HTMLResponse)
async def view_interview(
    interview_id: int, request: Request,
    db: Session = Depends(get_db), admin=Depends(get_current_admin)
):
    interview = _load_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "面接データが見つかりません")
    return templates.TemplateResponse("admin/interview_detail.html", {
        "request": request, "admin": admin, "interview": interview,
        "active_page": "interviews"
    })


@router.get("/interview-history/{interview_id}/export")
async def export_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    interview = _load_interview(db, interview_id)
    if not interview:
        raise HTTPException(404)
    return JSONResponse({
        "interview_id": interview.id,
        "applicant": interview.applicant.name,
        "job": interview.job.title,
        "company": interview.applicant.company.name,
        "status": interview.status,
        "total_score": interview.total_score,
        "ai_recommendation": interview.ai_recommendation,
        "evaluation_summary": interview.evaluation_summary,
        "evaluation_details": interview.evaluation_details,
        "messages": [
            {"role": m.role, "content": m.content, "time": m.created_at.isoformat()}
            for m in interview.messages
        ],
    })


@router.post("/interview-history/{interview_id}/re-evaluate")
async def re_evaluate(
    interview_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """面接評価を再実行する"""
    from routers.interview_session import build_evaluation_prompt, MODEL, MODELS
    import anthropic, json
    interview = _load_interview(db, interview_id)
    if not interview:
        raise HTTPException(404)
    if interview.status != "completed":
        raise HTTPException(400, "完了した面接のみ再評価できます")

    client = anthropic.Anthropic(api_key=__import__("os").getenv("ANTHROPIC_API_KEY",""))
    eval_prompt = build_evaluation_prompt(interview.job, interview.messages)

    last_err = None
    for model_id in MODELS:
        try:
            resp = client.messages.create(
                model=model_id, max_tokens=2000,
                messages=[{"role":"user","content":eval_prompt}]
            )
            text = resp.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"): text = text[4:]
            data = json.loads(text)
            interview.total_score = data.get("total_score", 0)
            interview.evaluation_summary = data.get("summary","")
            interview.evaluation_details = data
            interview.ai_recommendation = data.get("recommendation","review")
            db.commit()
            return JSONResponse({"ok": True, "score": interview.total_score})
        except Exception as e:
            last_err = e
            continue

    raise HTTPException(500, f"評価失敗: {last_err}")
