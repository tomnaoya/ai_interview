import os
import json
import secrets
from datetime import datetime
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import models
from database import engine, get_db, DATA_DIR
from auth import (
    get_current_admin, verify_password, get_password_hash,
    create_access_token, get_current_admin_optional
)
from routers import companies, accounts, jobs, applicants, interviews, privacy, interview_session

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI面接システム")

UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory="templates")

app.include_router(companies.router, prefix="/admin")
app.include_router(accounts.router, prefix="/admin")
app.include_router(jobs.router, prefix="/admin")
app.include_router(applicants.router, prefix="/admin")
app.include_router(interviews.router, prefix="/admin")
app.include_router(privacy.router, prefix="/admin")
app.include_router(interview_session.router)

SEED_QUESTIONS = [
    {"id": 1,  "question_ja": "簡潔に自己紹介をお願いします。",                                                                   "question_en": "Please briefly introduce yourself.",                                         "question_vi": "Vui lòng giới thiệu bản thân một cách ngắn gọn.", "time_limit": 120},
    {"id": 2,  "question_ja": "採用HPや採用動画を見たうえで率直な当法人の印象や感想を教えてください。",                           "question_en": "What is your honest impression of our organization after viewing our recruitment site and videos?", "question_vi": "Ấn tượng của bạn về tổ chức chúng tôi sau khi xem trang tuyển dụng?", "time_limit": 180},
    {"id": 3,  "question_ja": "ご自身の長所と短所を教えてください。",                                                              "question_en": "Please tell us your strengths and weaknesses.",                               "question_vi": "Hãy cho chúng tôi biết điểm mạnh và điểm yếu của bạn.", "time_limit": 180},
    {"id": 4,  "question_ja": "当法人を志望した理由を教えてください。",                                                            "question_en": "Why did you apply to our organization?",                                     "question_vi": "Lý do bạn ứng tuyển vào tổ chức chúng tôi là gì?", "time_limit": 180},
    {"id": 5,  "question_ja": "転職活動で大事にしている転職活動の軸、ゴールを教えてください。",                                   "question_en": "What are the key criteria and goals of your job search?",                    "question_vi": "Tiêu chí và mục tiêu quan trọng trong việc tìm kiếm việc làm của bạn là gì?", "time_limit": 180},
    {"id": 6,  "question_ja": "現在他社選考の状況や進捗があれば教えてください。",                                                  "question_en": "Please share your current status with other companies' selection processes.",  "question_vi": "Vui lòng chia sẻ tình trạng ứng tuyển tại các công ty khác.", "time_limit": 120},
    {"id": 7,  "question_ja": "複数の内定が出た際に何を基準として就業先を決めますか？",                                           "question_en": "If you receive multiple job offers, what criteria will you use to decide?",   "question_vi": "Nếu nhận được nhiều lời mời làm việc, bạn sẽ dựa vào tiêu chí nào để quyết định?", "time_limit": 150},
    {"id": 8,  "question_ja": "ご家族の方、友人の方、職場の方にどのような人といわれることが多いですか。",                         "question_en": "How do your family, friends, and colleagues typically describe you?",          "question_vi": "Gia đình, bạn bè và đồng nghiệp thường mô tả bạn như thế nào?", "time_limit": 150},
    {"id": 9,  "question_ja": "今までのお仕事の経験での失敗談を教えてください。",                                                  "question_en": "Please share a failure experience from your work history.",                   "question_vi": "Hãy chia sẻ một kinh nghiệm thất bại trong lịch sử làm việc của bạn.", "time_limit": 180},
    {"id": 10, "question_ja": "仲間と議論して意見が相違しているとき、貴方はどう考えて動きますか。",                               "question_en": "When you disagree with colleagues during discussions, how do you handle it?",  "question_vi": "Khi bất đồng ý kiến với đồng nghiệp, bạn xử lý như thế nào?", "time_limit": 180},
    {"id": 11, "question_ja": "今までを振り返って運がいい方と思いますか悪い方と思いますか。",                                     "question_en": "Looking back on your life, do you consider yourself lucky or unlucky?",        "question_vi": "Nhìn lại cuộc sống, bạn coi mình là người may mắn hay không?", "time_limit": 120},
    {"id": 12, "question_ja": "当法人に入職したときに叶えたいことやチャレンジしたいことを教えてください。",                       "question_en": "What do you hope to achieve or challenge yourself with when joining our organization?", "question_vi": "Bạn hy vọng đạt được điều gì khi gia nhập tổ chức chúng tôi?", "time_limit": 180},
]

SEED_GRADE_CRITERIA = [
    {"grade": "S", "min": 100},
    {"grade": "A", "min": 80},
    {"grade": "B", "min": 60},
    {"grade": "C", "min": 40},
    {"grade": "D", "min": 0},
]

SEED_KEYWORDS = ["協調性", "AI", "自己責任", "協力", "積極的に", "挑戦", "成長", "IT"]
SEED_PENALTY_TRAITS = ["他人のせいにする", "他責", "他者の悪口を言う"]


@app.on_event("startup")
async def startup_event():
    # ★ 起動時にDB場所をログ出力
    print(f"★ DATA_DIR = {DATA_DIR}")
    print(f"★ DATABASE_URL = {os.getenv('DATABASE_URL', f'sqlite:///{DATA_DIR}/ai_interview.db')}")
    import sqlalchemy
    print(f"★ Engine URL = {engine.url}")
    db = next(get_db())

    # Admin
    if not db.query(models.AdminAccount).first():
        db.add(models.AdminAccount(
            email=os.getenv("ADMIN_EMAIL", "admin@example.com"),
            password_hash=get_password_hash(os.getenv("ADMIN_PASSWORD", "Admin1234!")),
            name="システム管理者", is_active=True,
        ))
        db.commit()
        print("✅ Admin created")

    # Company seed
    company = db.query(models.Company).filter(
        models.Company.name == "医療法人社団モルゲンロート"
    ).first()
    if not company:
        company = models.Company(
            name="医療法人社団モルゲンロート",
            name_kana="イリョウホウジンシャダンモルゲンロート",
            industry="医療・福祉",
            size="51〜100名",
            address="東京都",
            is_active=True,
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        print(f"✅ Company created: {company.name}")

    # Job seed
    job = db.query(models.Job).filter(
        models.Job.title == "テスト",
        models.Job.company_id == company.id,
    ).first()
    if not job:
        job = models.Job(
            company_id=company.id,
            title="テスト",
            contact_email=os.getenv("ADMIN_EMAIL", "admin@example.com"),
            interview_language="ja",
            interview_type="avatar",
            avatar_gender="female",
            show_evaluation=True,
            share_result=False,
            retry_count=0,
            score_answer=70,
            score_speaking=20,
            score_posture=10,
            keywords=SEED_KEYWORDS,
            grade_criteria=SEED_GRADE_CRITERIA,
            ai_role="あなたは医療法人社団モルゲンロートの採用面接官です。",
            ai_evaluation_prompt="医療・福祉現場で求められる協調性・思いやり・責任感を重点的に評価してください。",
            interview_title_ja="面接",
            interview_title_en="Interview",
            interview_title_vi="Phong van",
            complete_title_ja="面接データを送信しました。",
            complete_body_ja="結果は担当者からご連絡いたします。\n少々お時間を頂戴いたします。\nご対応いただきましてありがとうございました。",
            complete_title_en="Interview data has been submitted.",
            complete_body_en="The results will be communicated by the person in charge.\nThank you for your cooperation.",
            complete_title_vi="Du lieu phong van da duoc gui.",
            complete_body_vi="Ket qua se duoc thong bao boi nguoi phu trach.\nCam on ban da hop tac.",
            ai_questions=SEED_QUESTIONS,
            ai_max_turns=len(SEED_QUESTIONS),
            ai_interview_duration=30,
            is_active=True,
        )
        db.add(job)
        db.commit()
        print(f"✅ Job created: {job.title}")
    else:
        # 既存ジョブのデータが消えていた場合は復元する
        updated = False
        if not job.ai_questions:
            job.ai_questions = SEED_QUESTIONS
            job.ai_max_turns = len(SEED_QUESTIONS)
            updated = True
        if not job.keywords:
            job.keywords = SEED_KEYWORDS
            updated = True
        if not job.penalty_traits:
            job.penalty_traits = SEED_PENALTY_TRAITS
            updated = True
        if updated:
            db.commit()
            print(f"✅ Job restored: {job.title}")

    db.close()


@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    admin = get_current_admin_optional(request, next(get_db()))
    if admin:
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/admin/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = db.query(models.AdminAccount).filter(
        models.AdminAccount.email == email,
        models.AdminAccount.is_active == True
    ).first()
    if not admin or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "メールアドレスまたはパスワードが正しくありません"
        })
    admin.last_login = datetime.utcnow()
    db.commit()
    token = create_access_token({"sub": admin.email, "role": "admin"})
    response = RedirectResponse("/admin", status_code=302)
    response.set_cookie("admin_token", token, httponly=True, max_age=3600 * 8)
    return response


@app.get("/admin/logout")
async def logout():
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie("admin_token")
    return response


@app.get("/admin", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    stats = {
        "companies": db.query(models.Company).filter(models.Company.is_active == True).count(),
        "jobs": db.query(models.Job).filter(models.Job.is_active == True).count(),
        "applicants": db.query(models.Applicant).count(),
        "interviews_today": db.query(models.Interview).filter(
            models.Interview.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
        ).count(),
        "interviews_completed": db.query(models.Interview).filter(
            models.Interview.status == "completed"
        ).count(),
    }
    recent_interviews = db.query(models.Interview).order_by(
        models.Interview.created_at.desc()
    ).limit(5).all()
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "admin": admin, "stats": stats,
        "recent_interviews": recent_interviews, "active_page": "dashboard",
    })


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/admin/login")


@app.get("/debug-info")
async def debug_info(db: Session = Depends(get_db)):
    """DB・ファイルパスの診断用エンドポイント"""
    import os as _os
    db_path = str(engine.url).replace("sqlite:///", "")
    return JSONResponse({
        "DATA_DIR": DATA_DIR,
        "engine_url": str(engine.url),
        "db_file_exists": _os.path.exists(db_path),
        "db_file_size_bytes": _os.path.getsize(db_path) if _os.path.exists(db_path) else 0,
        "companies": db.query(models.Company).count(),
        "interviews": db.query(models.Interview).count(),
        "applicants": db.query(models.Applicant).count(),
    })
