import os
import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import models
import anthropic

router = APIRouter()
templates = Jinja2Templates(directory="templates")
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


def build_system_prompt(job: models.Job, applicant: models.Applicant) -> str:
    questions_text = ""
    if job.ai_questions:
        questions_text = "\n".join([
            f"- [{q.get('category', '')}] {q.get('question', '')}"
            for q in job.ai_questions
        ])

    criteria_text = ""
    if job.ai_evaluation_criteria:
        criteria_text = "\n".join([
            f"- {c.get('name', '')}: {c.get('weight', 0)}%"
            for c in job.ai_evaluation_criteria
        ])

    return f"""{job.ai_persona or ''}

## 採用情報
- 企業名: {job.company.name}
- 求人タイトル: {job.title}
- 雇用形態: {job.employment_type or '未設定'}
- 勤務地: {job.location or '未設定'}

## 応募者情報
- 氏名: {applicant.name}
- 学歴: {applicant.education or '未記載'}
- 職務経歴: {applicant.work_experience or '未記載'}

## 面接で聞くべき質問（必ずしもこの順番である必要はなく、会話の流れに合わせて調整してください）
{questions_text}

## 評価基準
{criteria_text}

## 重要なルール
1. 質問は一度に必ず一つだけ行ってください
2. 応募者の回答に対して共感・承認を示してから次の質問に進んでください
3. 面接は丁寧で温かみのある雰囲気を保ってください
4. すべての質問が終わったら、面接終了の旨を伝え「[INTERVIEW_COMPLETE]」というタグを文末に付けてください
5. 回答が不明瞭な場合は適切にフォローアップ質問をしてください
6. 面接時間: 約{job.ai_interview_duration}分を目安にしてください
"""


def build_evaluation_prompt(job: models.Job, messages: list) -> str:
    conversation = "\n".join([
        f"{'面接官' if m.role == 'assistant' else '応募者'}: {m.content}"
        for m in messages
        if not m.content.startswith("[SYSTEM]")
    ])

    criteria_text = ""
    if job.ai_evaluation_criteria:
        criteria_text = "\n".join([
            f"- {c.get('name', '')}: {c.get('weight', 0)}%"
            for c in job.ai_evaluation_criteria
        ])

    return f"""以下の面接の会話記録を分析し、応募者を評価してください。

## 求人情報
- タイトル: {job.title}
- 企業: {job.company.name}

## 評価基準（合計100%）
{criteria_text}

## 面接会話記録
{conversation}

## 出力形式（必ずJSONのみで回答してください）
{{
  "total_score": 75,
  "recommendation": "pass",
  "summary": "総合評価のサマリー（200字程度）",
  "details": [
    {{"criterion": "評価基準名", "score": 80, "comment": "コメント", "weight": 20}},
    ...
  ],
  "strengths": ["強み1", "強み2"],
  "concerns": ["懸念点1", "懸念点2"],
  "interview_quality": "面接の質・応答の充実度についてのコメント"
}}

recommendation は "pass"(採用推薦), "review"(再検討), "fail"(不採用推薦) のいずれか。
total_score は 0-100 の数値。
必ずJSON形式のみで回答し、マークダウンの```は使用しないでください。"""


# ── Interview Pages ──────────────────────────────────────────────────────────

@router.get("/interview/{token}", response_class=HTMLResponse)
async def interview_start(
    token: str, request: Request, db: Session = Depends(get_db)
):
    interview = db.query(models.Interview).filter(models.Interview.token == token).first()
    if not interview:
        return HTMLResponse("<h1>無効なリンクです</h1>", status_code=404)
    if interview.status == "completed":
        return templates.TemplateResponse("interview/completed.html", {
            "request": request, "interview": interview
        })
    if interview.status == "expired":
        return HTMLResponse("<h1>このリンクは有効期限が切れています</h1>", status_code=410)

    # Get privacy policy
    policy = db.query(models.PrivacyPolicy).filter(
        models.PrivacyPolicy.company_id == interview.applicant.company_id,
        models.PrivacyPolicy.is_active == True,
    ).first()
    if not policy:
        policy = db.query(models.PrivacyPolicy).filter(
            models.PrivacyPolicy.company_id == None,
            models.PrivacyPolicy.is_active == True,
        ).first()

    return templates.TemplateResponse("interview/start.html", {
        "request": request,
        "interview": interview,
        "job": interview.job,
        "applicant": interview.applicant,
        "policy": policy,
    })


@router.post("/interview/{token}/start")
async def start_interview(token: str, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.token == token).first()
    if not interview:
        raise HTTPException(404)
    if interview.status not in ("waiting", "in_progress"):
        raise HTTPException(400, "この面接は既に終了しています")

    interview.status = "in_progress"
    interview.started_at = datetime.utcnow()
    db.commit()

    # Generate initial greeting
    job = interview.job
    greeting = (job.ai_greeting or "面接を開始します。よろしくお願いします。").replace(
        "{duration}", str(job.ai_interview_duration)
    ).replace("{name}", interview.applicant.name)

    # Add greeting as first assistant message
    if not interview.messages:
        msg = models.InterviewMessage(
            interview_id=interview.id, role="assistant", content=greeting
        )
        db.add(msg)
        db.commit()

    return JSONResponse({"status": "started", "greeting": greeting})


@router.post("/interview/{token}/message")
async def send_message(token: str, request: Request, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.token == token).first()
    if not interview or interview.status != "in_progress":
        raise HTTPException(400, "面接が開始されていません")

    body = await request.json()
    user_message = body.get("message", "").strip()
    if not user_message:
        raise HTTPException(400, "メッセージが空です")

    # Save user message
    db.add(models.InterviewMessage(
        interview_id=interview.id, role="user", content=user_message
    ))
    db.commit()

    # Build message history for Claude
    job = interview.job
    system_prompt = build_system_prompt(job, interview.applicant)

    history = []
    for m in interview.messages:
        history.append({"role": m.role, "content": m.content})

    # Check turn limit
    user_turns = sum(1 for m in interview.messages if m.role == "user")
    if user_turns >= job.ai_max_turns:
        closing = f"ご回答いただきありがとうございました。これで面接を終了いたします。{interview.applicant.name}様のご活躍をお祈りしております。[INTERVIEW_COMPLETE]"
        db.add(models.InterviewMessage(
            interview_id=interview.id, role="assistant", content=closing
        ))
        await _complete_interview(interview, db)
        return JSONResponse({"reply": closing, "completed": True})

    # Call Claude API
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1000,
            system=system_prompt,
            messages=history,
        )
        reply = response.content[0].text
    except Exception as e:
        reply = "申し訳ございません。システムエラーが発生しました。少し待ってから再度お試しください。"
        print(f"Claude API error: {e}")

    # Save assistant message
    db.add(models.InterviewMessage(
        interview_id=interview.id, role="assistant", content=reply
    ))
    db.commit()

    completed = "[INTERVIEW_COMPLETE]" in reply
    if completed:
        await _complete_interview(interview, db)

    return JSONResponse({"reply": reply, "completed": completed})


async def _complete_interview(interview: models.Interview, db: Session):
    interview.status = "completed"
    interview.completed_at = datetime.utcnow()
    db.commit()

    # Run AI evaluation
    try:
        eval_prompt = build_evaluation_prompt(interview.job, interview.messages)
        eval_response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": eval_prompt}],
        )
        eval_text = eval_response.content[0].text.strip()
        # Clean JSON
        if eval_text.startswith("```"):
            eval_text = eval_text.split("```")[1]
            if eval_text.startswith("json"):
                eval_text = eval_text[4:]
        eval_data = json.loads(eval_text)
        interview.total_score = eval_data.get("total_score", 0)
        interview.evaluation_summary = eval_data.get("summary", "")
        interview.evaluation_details = eval_data
        interview.ai_recommendation = eval_data.get("recommendation", "review")
        # Update applicant status
        if interview.ai_recommendation == "pass":
            interview.applicant.status = "interviewed"
        db.commit()
    except Exception as e:
        print(f"Evaluation error: {e}")
        interview.evaluation_summary = "評価処理中にエラーが発生しました"
        db.commit()


@router.get("/interview/{token}/messages")
async def get_messages(token: str, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.token == token).first()
    if not interview:
        raise HTTPException(404)
    messages = [
        {"role": m.role, "content": m.content, "time": m.created_at.isoformat()}
        for m in interview.messages
    ]
    return JSONResponse({"messages": messages, "status": interview.status})
