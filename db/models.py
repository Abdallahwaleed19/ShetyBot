"""
db/models.py — SQLAlchemy ORM model يطابق جدول sick_leave_reports بالظبط.

الجدول موجود في قاعدة بيانات seha_db التابعة لموقع Laravel،
البوت يحفظ فيه مباشرة عشان الموقع يقدر يعرض البيانات.
"""
import enum
from sqlalchemy import (
    BigInteger, Column, Date, Enum, Index,
    SmallInteger, String, Text, Time, TIMESTAMP, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class HospitalType(str, enum.Enum):
    government = "government"
    private    = "private"


class SickLeaveReport(Base):
    """
    يطابق جدول `sick_leave_reports` في seha_db بالظبط —
    نفس أسماء الأعمدة وأنواع البيانات والـ constraints.
    """
    __tablename__ = "sick_leave_reports"

    # Primary Key — AUTO_INCREMENT زي ما Laravel بيعمل
    id                  = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── بيانات التقرير ──────────────────────────────────────────────────────
    service_code        = Column(String(50),  nullable=False, unique=True)   # رمز الإجازة  GSL...
    report_type         = Column(String(100), nullable=False)
    admission_date      = Column(Date,        nullable=False)                # DATE
    discharge_date      = Column(Date,        nullable=False)                # DATE
    leave_duration_days = Column(SmallInteger, nullable=False)
    issue_date          = Column(Date,        nullable=False)                # DATE
    report_time         = Column(Time,        nullable=True)                 # TIME  e.g. 18:32:00

    # ── بيانات المريض ──────────────────────────────────────────────────────
    national_id         = Column(String(14),  nullable=False, index=True)
    patient_name_ar     = Column(String(200), nullable=False)
    patient_name_en     = Column(String(200), nullable=True)
    nationality         = Column(String(100), nullable=True)
    nationality_en      = Column(String(100), nullable=True)
    employer            = Column(String(200), nullable=True)
    employer_en         = Column(String(200), nullable=True)

    # ── بيانات الممارس ─────────────────────────────────────────────────────
    practitioner_name_ar = Column(String(200), nullable=True)
    practitioner_name_en = Column(String(200), nullable=True)
    job_title_ar         = Column(String(200), nullable=True)   # المسمى الوظيفي عربي
    job_title_en         = Column(String(200), nullable=True)   # المسمى الوظيفي إنجليزي

    # ── بيانات المستشفى ────────────────────────────────────────────────────
    hospital_name_ar    = Column(String(200), nullable=True)
    hospital_name_en    = Column(String(200), nullable=True)
    hospital_type       = Column(Enum(HospitalType), nullable=True)
    hospital_logo_path  = Column(String(255), nullable=True)

    # ── حقول إضافية (موجودة في الجدول) ──────────────────────────────────
    companion_name      = Column(String(255), nullable=True)
    relationship        = Column(String(100), nullable=True)

    # ── Timestamps (Laravel convention) ───────────────────────────────────
    created_at          = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at          = Column(TIMESTAMP, server_default=func.now(),
                                 onupdate=func.now(), nullable=True)

    # ── Constraints (نفس الـ SQL) ─────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint("national_id", "service_code",
                         name="sick_leave_reports_national_id_service_code_unique"),
    )
