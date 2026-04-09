from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_admin
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/interview-history", response_class=HTMLResponse)
async def list_interviews(
    request: Request,
    company_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    query = db.query(models.Interview)
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
    interview = db.query(models.Interview).get(interview_id)
    if not interview:
        raise HTTPException(404)
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
    interview = db.query(models.Interview).get(interview_id)
    if not interview:
        raise HTTPException(404)
    data = {
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
    }
    return JSONResponse(data)
