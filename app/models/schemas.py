"""Pydantic schemas for resume parsing input/output."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

import phonenumbers
from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
YYYY_MM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
URL_RE = re.compile(r"^https?://[^\s]+$")


# ---------- Nested schemas ----------

class Location(BaseModel):
    city: str | None = None
    state: str | None = None
    country: str | None = None
    full_address: str | None = None


class PersonalInfo(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: Location = Field(default_factory=Location)
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    other_urls: list[str] = Field(default_factory=list)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v):
        if v is None or v == "":
            return None
        v = str(v).strip().lower()
        if not EMAIL_RE.match(v):
            return None
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v):
        if v is None or v == "":
            return None
        raw = str(v).strip()
        try:
            # Try parsing with no region first (for E.164 numbers)
            parsed = phonenumbers.parse(raw, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        # Try with US region as fallback
        try:
            parsed = phonenumbers.parse(raw, "US")
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        return raw  # return original if unparseable

    @field_validator("linkedin_url", "github_url", "portfolio_url", mode="before")
    @classmethod
    def validate_url(cls, v):
        if v is None or v == "":
            return None
        v = str(v).strip()
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        if not URL_RE.match(v):
            return None
        return v


class Skills(BaseModel):
    technical: list[str] = Field(default_factory=list)
    soft: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    certifications_mentioned_as_skills: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    company_name: str | None = None
    job_title: str | None = None
    employment_type: Literal["full-time", "part-time", "contract", "internship", "freelance"] | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None
    achievements: list[str] = Field(default_factory=list)
    skills_mentioned: list[str] = Field(default_factory=list)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_date(cls, v):
        if v is None or v == "":
            return None
        v = str(v).strip()
        if not YYYY_MM_RE.match(v):
            return None
        # Must not be in the future
        try:
            year, month = map(int, v.split("-"))
            now = datetime.utcnow()
            if (year, month) > (now.year, now.month):
                return None
        except (ValueError, AttributeError):
            return None
        return v

    @model_validator(mode="after")
    def check_date_order(self):
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                # Swap if obviously reversed
                self.start_date, self.end_date = self.end_date, self.start_date
        return self


class Education(BaseModel):
    institution_name: str | None = None
    degree_type: Literal["Bachelor", "Master", "PhD", "Associate", "Diploma", "Certificate", "High School"] | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    graduation_date: str | None = None
    is_ongoing: bool = False
    gpa: float | None = None
    gpa_scale: float | None = None
    honors: str | None = None
    activities: list[str] = Field(default_factory=list)

    @field_validator("start_date", "graduation_date", mode="before")
    @classmethod
    def validate_date(cls, v):
        if v is None or v == "":
            return None
        v = str(v).strip()
        if not YYYY_MM_RE.match(v):
            return None
        return v

    @field_validator("gpa")
    @classmethod
    def validate_gpa(cls, v):
        if v is None:
            return None
        if v < 0 or v > 10:
            return None
        return v


class Certification(BaseModel):
    name: str | None = None
    issuing_organization: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None

    @field_validator("issue_date", "expiry_date", mode="before")
    @classmethod
    def validate_date(cls, v):
        if v is None or v == "":
            return None
        v = str(v).strip()
        if not YYYY_MM_RE.match(v):
            return None
        return v


class Project(BaseModel):
    name: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None
    start_date: str | None = None
    end_date: str | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_date(cls, v):
        if v is None or v == "":
            return None
        v = str(v).strip()
        if not YYYY_MM_RE.match(v):
            return None
        return v


class LanguageSpoken(BaseModel):
    language: str
    proficiency: Literal["Native", "Fluent", "Professional", "Conversational", "Basic"] | None = None


class Award(BaseModel):
    title: str | None = None
    issuer: str | None = None
    date: str | None = None
    description: str | None = None


class Publication(BaseModel):
    title: str | None = None
    publisher: str | None = None
    date: str | None = None
    url: str | None = None


class Volunteer(BaseModel):
    organization: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class ParserMetadata(BaseModel):
    total_years_experience: float | None = None
    career_level: Literal["Entry", "Junior", "Mid", "Senior", "Lead", "Manager", "Director", "Executive"] | None = None
    primary_domain: str | None = None
    resume_language: str = "en"


class ResumeSchema(BaseModel):
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    professional_summary: str | None = None
    skills: Skills = Field(default_factory=Skills)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    languages_spoken: list[LanguageSpoken] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    volunteer_experience: list[Volunteer] = Field(default_factory=list)
    parser_metadata: ParserMetadata = Field(default_factory=ParserMetadata)


# ---------- Job description + matching ----------

class JobDescriptionIn(BaseModel):
    title: str
    company: str | None = None
    description: str
    required_skills: list[str] | None = None
    required_years: int | None = None


class MatchScore(BaseModel):
    total: float
    breakdown: dict[str, float]
    matching_skills: list[str]
    missing_skills: list[str]


# ---------- API envelopes ----------

class ResumeStatus(BaseModel):
    resume_id: str
    status: str
    confidence_score: float | None = None
    parse_time_ms: int | None = None
    error_message: str | None = None


class ResumeFull(BaseModel):
    resume_id: str
    status: str
    confidence_score: float | None = None
    parsed_data: ResumeSchema | None = None
    original_filename: str
    file_type: str
    extractor_used: str | None = None
    ocr_used: bool = False
