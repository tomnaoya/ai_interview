import os
import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from database import get_db
import models
import anthropic

router = APIRouter()
templates = Jinja2Templates(directory="templates")
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# 正しいモデル名
# モデルIDの優先順位リスト（上から順に試みる）
MODELS = [
    "claude-sonnet-4-5-20250514",   # Claude Sonnet 4.5 (stable)
    "claude-3-5-sonnet-20241022",   # Claude 3.5 Sonnet (fallback)
    "claude-haiku-4-5-20251001",    # Claude Haiku 4.5 (lightweight fallback)
]
MODEL = MODELS[0]


def build_system_prompt(job: models.Job, applicant: models.Applicant) -> str:
    """新旧両方のJobフォーマットに対応したシステムプロンプト生成"""
    lang = job.interview_language or "ja"

    # 質問リスト（新形式: question_ja / 旧形式: question）
    questions_text = ""
    if job.ai_questions:
        lines = []
        for i, q in enumerate(job.ai_questions, 1):
            if lang == "en":
                text = q.get("question_en") or q.get("question_ja") or q.get("question", "")
            elif lang == "vi":
                text = q.get("question_vi") or q.get("question_ja") or q.get("question", "")
            else:
                text = q.get("question_ja") or q.get("question", "")
            if text:
                lines.append(f"{i}. {text}")
        questions_text = "\n".join(lines)

    # 評価基準（新形式: grade_criteria＋ai_evaluation_prompt / 旧形式: ai_evaluation_criteria）
    criteria_text = ""
    if job.ai_evaluation_prompt:
        criteria_text = job.ai_evaluation_prompt
    elif job.ai_evaluation_criteria:
        criteria_text = "\n".join([
            f"- {c.get('name','')}: {c.get('weight',0)}%"
            for c in job.ai_evaluation_criteria
        ])

    # キーワード
    keywords_text = ""
    if job.keywords:
        keywords_text = "評価時に加点するキーワード: " + "、".join(job.keywords)

    # ペルソナ（新形式: ai_role / 旧形式: ai_persona）
    if job.ai_role and job.ai_role.strip():
        persona = f"あなたは{job.ai_role}です。"
    elif job.ai_persona:
        persona = job.ai_persona
    else:
        persona = f"あなたは{job.company.name}のプロフェッショナルな採用面接官です。"

    return f"""{persona}

## 採用情報
- 企業名: {job.company.name}
- 求人タイトル: {job.title}

## 応募者情報
- 氏名: {applicant.name}
- 学歴: {applicant.education or '未記載'}
- 職務経歴: {applicant.work_experience or '未記載'}

## 面接質問リスト（この順番で必ず聞いてください。一度に一問ずつ）
{questions_text or '自由に適切な質問を行ってください。'}

## 評価方針
{criteria_text}
{keywords_text}

## 厳守ルール
1. 質問は必ず一度に一つだけ行う
2. 一回の発言は**3文以内**に収める（簡潔に）
3. 共感・承認は一言で済ませ、すぐ次の質問へ進む
4. すべての質問が完了したら「本日はありがとうございました。以上で面接を終了いたします。[INTERVIEW_COMPLETE]」と伝える
5. 回答が短い・不明瞭な場合は一度だけフォローアップ質問をする
6. 日本語で面接を行う（interview_language: {lang}）
7. **マークダウン記号（*、**、#、-、「」など装飾的な記号）は一切使わない**
8. 音声で読み上げることを前提とした自然な話し言葉で書く
"""


def build_evaluation_prompt(job: models.Job, messages: list) -> str:
    conversation = "\n".join([
        f"{'面接官' if m.role == 'assistant' else '応募者'}: {m.content}"
        for m in messages
    ])

    criteria_text = ""
    if job.ai_evaluation_criteria:
        criteria_text = "\n".join([
            f"- {c.get('name','')}: {c.get('weight',0)}%"
            for c in job.ai_evaluation_criteria
        ])
    elif job.grade_criteria:
        criteria_text = "S(100点〜)/A(80点〜)/B(60点〜)/C(40点〜)/D(0点〜)"

    return f"""以下の面接の会話記録を分析し、応募者を評価してください。

## 求人情報
- タイトル: {job.title}
- 企業: {job.company.name}

## 評価基準
{criteria_text or '総合的に評価してください'}

## 加点キーワード
{', '.join(job.keywords or [])}

## 面接会話記録
{conversation}

## 出力形式（JSONのみ・マークダウン不要）
{{"total_score":75,"recommendation":"pass","summary":"総合評価200字程度","details":[{{"criterion":"評価項目","score":80,"comment":"コメント","weight":20}}],"strengths":["強み1"],"concerns":["懸念1"]}}

recommendationは "pass"/"review"/"fail" のいずれか。total_scoreは0-100。JSONのみで回答。"""


# ── Interview Pages ──────────────────────────────────────────────────────────

@router.get("/interview/{token}", response_class=HTMLResponse)
async def interview_start(token: str, request: Request, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).options(
        joinedload(models.Interview.applicant).joinedload(models.Applicant.company),
        joinedload(models.Interview.job).joinedload(models.Job.company),
    ).filter(models.Interview.token == token).first()

    if not interview:
        return HTMLResponse("<h1 style='font-family:sans-serif;padding:40px'>無効なリンクです</h1>", status_code=404)
    if interview.status == "completed":
        return templates.TemplateResponse("interview/completed.html", {"request": request, "interview": interview})
    if interview.status == "expired":
        return HTMLResponse("<h1 style='font-family:sans-serif;padding:40px'>このリンクは有効期限が切れています</h1>", status_code=410)

    policy = db.query(models.PrivacyPolicy).filter(
        models.PrivacyPolicy.company_id == interview.applicant.company_id,
        models.PrivacyPolicy.is_active == True,
    ).first() or db.query(models.PrivacyPolicy).filter(
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

    job = interview.job
    lang = job.interview_language or "ja"

    # 言語別の挨拶
    if lang == "en":
        greeting = f"Thank you for joining the interview for {job.company.name}. I'm your AI interviewer today. We have about {job.ai_interview_duration} minutes. Please feel free to speak naturally. When you're ready, please say 'I'm ready'."
    elif lang == "vi":
        greeting = f"Cảm ơn bạn đã tham gia phỏng vấn tại {job.company.name}. Tôi là người phỏng vấn AI hôm nay. Khi bạn sẵn sàng, hãy nói 'Tôi đã sẵn sàng'."
    else:
        greeting = (job.ai_greeting or "本日はご応募いただきありがとうございます。これよりAI面接を開始いたします。約{duration}分程度を予定しております。準備ができましたら「はい、準備できました」とお答えください。").replace("{duration}", str(job.ai_interview_duration or 30)).replace("{name}", interview.applicant.name)

    if not interview.messages:
        db.add(models.InterviewMessage(
            interview_id=interview.id, role="assistant", content=greeting
        ))
        db.commit()

    return JSONResponse({"status": "started", "greeting": greeting})


@router.post("/interview/{token}/message")
async def send_message(token: str, request: Request, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).options(
        joinedload(models.Interview.applicant),
        joinedload(models.Interview.job).joinedload(models.Job.company),
        joinedload(models.Interview.messages),
    ).filter(models.Interview.token == token).first()

    if not interview or interview.status != "in_progress":
        raise HTTPException(400, "面接が開始されていません")

    body = await request.json()
    user_message = body.get("message", "").strip()
    if not user_message:
        raise HTTPException(400, "メッセージが空です")

    db.add(models.InterviewMessage(
        interview_id=interview.id, role="user", content=user_message
    ))
    db.commit()
    db.refresh(interview)

    job = interview.job
    system_prompt = build_system_prompt(job, interview.applicant)

    # Anthropic API requires history to start with "user" and alternate roles.
    # The initial greeting (first assistant message) goes in the system prompt,
    # so we skip leading assistant messages and merge consecutive same-role messages.
    raw = [{"role": m.role, "content": m.content} for m in interview.messages]

    # Drop leading assistant messages (greeting is already in system prompt context)
    while raw and raw[0]["role"] == "assistant":
        raw.pop(0)

    # Merge consecutive same-role messages (API requires strict alternation)
    history = []
    for msg in raw:
        if history and history[-1]["role"] == msg["role"]:
            history[-1]["content"] += "\n" + msg["content"]
        else:
            history.append({"role": msg["role"], "content": msg["content"]})

    # Must start with user
    if not history:
        history = [{"role": "user", "content": user_message}]

    # ターン数チェック
    user_turns = sum(1 for m in interview.messages if m.role == "user")
    total_questions = len(job.ai_questions) if job.ai_questions else (job.ai_max_turns or 10)

    if user_turns >= total_questions + 2:
        closing = "本日は面接にご参加いただきありがとうございました。以上で面接を終了いたします。[INTERVIEW_COMPLETE]"
        db.add(models.InterviewMessage(interview_id=interview.id, role="assistant", content=closing))
        await _complete_interview(interview, db)
        return JSONResponse({"reply": closing, "completed": True})

    # Claude API呼び出し（モデルフォールバック付き）
    reply = None
    last_error = None
    for model_id in MODELS:
        try:
            response = client.messages.create(
                model=model_id,
                max_tokens=1000,
                system=system_prompt,
                messages=history,
            )
            reply = response.content[0].text
            print(f"[OK] Used model: {model_id}")
            break
        except anthropic.APIConnectionError as e:
            print(f"[ERROR] Connection error: {e}")
            raise HTTPException(503, "AIサービスに接続できません")
        except anthropic.AuthenticationError as e:
            print(f"[ERROR] Auth error: {e}")
            raise HTTPException(500, "APIキーが無効です")
        except anthropic.BadRequestError as e:
            print(f"[WARN] BadRequestError with model {model_id}: {e}")
            last_error = e
            continue  # 次のモデルを試す
        except Exception as e:
            print(f"[ERROR] Claude API {model_id}: {type(e).__name__}: {e}")
            last_error = e
            continue

    if reply is None:
        detail = str(last_error) if last_error else "全モデルで失敗"
        print(f"[ERROR] All models failed. Last: {detail}")
        raise HTTPException(500, f"AI処理失敗: {detail}")

    db.add(models.InterviewMessage(interview_id=interview.id, role="assistant", content=reply))
    db.commit()

    completed = "[INTERVIEW_COMPLETE]" in reply
    if completed:
        await _complete_interview(interview, db)

    return JSONResponse({"reply": reply, "completed": completed})


async def _complete_interview(interview: models.Interview, db: Session):
    interview.status = "completed"
    interview.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(interview)

    try:
        eval_prompt = build_evaluation_prompt(interview.job, interview.messages)
        eval_response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": eval_prompt}],
        )
        eval_text = eval_response.content[0].text.strip()
        if "```" in eval_text:
            eval_text = eval_text.split("```")[1]
            if eval_text.startswith("json"):
                eval_text = eval_text[4:]
        eval_data = json.loads(eval_text)
        interview.total_score = eval_data.get("total_score", 0)
        interview.evaluation_summary = eval_data.get("summary", "")
        interview.evaluation_details = eval_data
        interview.ai_recommendation = eval_data.get("recommendation", "review")
        interview.applicant.status = "interviewed"
        db.commit()
    except Exception as e:
        print(f"[ERROR] Evaluation error: {type(e).__name__}: {e}")
        interview.evaluation_summary = "評価処理中にエラーが発生しました"
        db.commit()


@router.get("/interview/{token}/messages")
async def get_messages(token: str, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.token == token).first()
    if not interview:
        raise HTTPException(404)
    return JSONResponse({
        "messages": [{"role": m.role, "content": m.content} for m in interview.messages],
        "status": interview.status,
        "total_questions": len(interview.job.ai_questions) if interview.job.ai_questions else 10,
    })


@router.get("/interview/{token}/debug")
async def debug_interview(token: str, db: Session = Depends(get_db)):
    """デバッグ用：面接状態確認"""
    interview = db.query(models.Interview).filter(models.Interview.token == token).first()
    if not interview:
        return JSONResponse({"error": "token not found"})
    return JSONResponse({
        "interview_id": interview.id,
        "status": interview.status,
        "job_title": interview.job.title if interview.job else None,
        "company": interview.job.company.name if interview.job and interview.job.company else None,
        "questions_count": len(interview.job.ai_questions) if interview.job and interview.job.ai_questions else 0,
        "messages_count": len(interview.messages),
        "model": MODEL,
        "api_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
    })
