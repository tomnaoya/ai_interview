from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
)
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    name_kana = Column(String(200))
    industry = Column(String(100))
    size = Column(String(50))
    address = Column(Text)
    phone = Column(String(20))
    website = Column(String(300))
    logo_path = Column(String(500))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    accounts = relationship("CompanyAccount", back_populates="company")
    jobs = relationship("Job", back_populates="company")
    applicants = relationship("Applicant", back_populates="company")


class CompanyAccount(Base):
    __tablename__ = "company_accounts"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(500), nullable=False)
    name = Column(String(100))
    role = Column(String(20), default="user")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="accounts")


class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(500), nullable=False)
    name = Column(String(100))
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    title = Column(String(200), nullable=False)
    contact_email = Column(String(200))
    expires_at = Column(DateTime)
    interview_language = Column(String(10), default="ja")
    interview_type = Column(String(20), default="avatar")
    avatar_gender = Column(String(10), default="female")
    show_evaluation = Column(Boolean, default=True)
    share_result = Column(Boolean, default=False)
    retry_count = Column(Integer, default=0)
    score_answer = Column(Integer, default=70)
    score_speaking = Column(Integer, default=20)
    score_posture = Column(Integer, default=10)
    keywords = Column(JSON)
    grade_criteria = Column(JSON)
    ai_role = Column(Text)
    ai_evaluation_prompt = Column(Text)
    interview_title_ja = Column(String(300), default="面接")
    interview_title_en = Column(String(300), default="Interview")
    interview_title_vi = Column(String(300), default="Phong van")
    complete_title_ja = Column(String(300), default="面接データを送信しました。")
    complete_body_ja = Column(Text, default="結果は担当者からご連絡いたします。")
    complete_title_en = Column(String(300), default="Interview data has been submitted.")
    complete_body_en = Column(Text, default="The results will be communicated by the person in charge.")
    complete_title_vi = Column(String(300), default="Du lieu phong van da duoc gui.")
    complete_body_vi = Column(Text, default="Ket qua se duoc thong bao boi nguoi phu trach.")
    ai_questions = Column(JSON)
    ai_persona = Column(Text)
    ai_greeting = Column(Text)
    ai_evaluation_criteria = Column(JSON)
    ai_max_turns = Column(Integer, default=10)
    ai_interview_duration = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="jobs")
    interviews = relationship("Interview", back_populates="job")


class Applicant(Base):
    __tablename__ = "applicants"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    name = Column(String(100), nullable=False)
    name_kana = Column(String(100))
    email = Column(String(200), nullable=False)
    phone = Column(String(20))
    birth_date = Column(String(10))
    address = Column(Text)
    education = Column(Text)
    work_experience = Column(Text)
    resume_path = Column(String(500))
    notes = Column(Text)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="applicants")
    interviews = relationship("Interview", back_populates="applicant")


class Interview(Base):
    __tablename__ = "interviews"
    id = Column(Integer, primary_key=True, index=True)
    applicant_id = Column(Integer, ForeignKey("applicants.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    token = Column(String(100), unique=True, index=True)
    status = Column(String(30), default="waiting")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    total_score = Column(Float)
    evaluation_summary = Column(Text)
    evaluation_details = Column(JSON)
    ai_recommendation = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)

    applicant = relationship("Applicant", back_populates="interviews")
    job = relationship("Job", back_populates="interviews")
    messages = relationship("InterviewMessage", back_populates="interview", order_by="InterviewMessage.id")


class InterviewMessage(Base):
    __tablename__ = "interview_messages"
    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    interview = relationship("Interview", back_populates="messages")


class PrivacyPolicy(Base):
    __tablename__ = "privacy_policies"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    version = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
