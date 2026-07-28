"""Deterministic recruitment tools with explicit contracts and safe errors."""

from __future__ import annotations

import json
import io
import logging
import re
from pathlib import Path
from typing import Any, Callable


PASS_THRESHOLD = 80
REVIEW_THRESHOLD = 60
AVAILABLE_SLOTS = {
    "available": ["2026-07-30 09:00", "2026-07-30 14:00"],
    "unavailable": [],
}
SCHEDULED_INTERVIEWS: dict[str, str] = {}


def _decode_object(value: str | dict[str, Any], label: str) -> tuple[dict[str, Any] | None, str | None]:
    if value == "" or value is None:
        return None, f"{label} is empty."
    if isinstance(value, dict):
        return value, None
    if not isinstance(value, str):
        return None, f"{label} must be a JSON object."
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None, f"{label} must be valid JSON."
    if not isinstance(decoded, dict):
        return None, f"{label} must be a JSON object."
    return decoded, None


def _experience_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:years?|năm)?\s*", value, re.I)
        return float(match.group(1)) if match else None
    return None


def _normalized_items(values: Any) -> dict[str, str]:
    if not isinstance(values, list):
        return {}
    result: dict[str, str] = {}
    for item in values:
        if isinstance(item, dict):
            item = item.get("name") or item.get("degree") or item.get("language") or ""
        label = str(item).strip()
        if label:
            result[label.casefold()] = label
    return result


def _education_rank(value: str) -> int:
    text = value.casefold()
    if "phd" in text or "doctor" in text or "tiến sĩ" in text:
        return 4
    if "master" in text or "thạc sĩ" in text:
        return 3
    if "bachelor" in text or "cử nhân" in text or "engineer" in text:
        return 2
    if "associate" in text or "college" in text or "cao đẳng" in text:
        return 1
    return 0


def _candidate_degree(cv: dict[str, Any]) -> str:
    education = cv.get("education", [])
    if isinstance(education, str):
        return education
    if isinstance(education, list):
        degrees = [str(item.get("degree", "")) for item in education if isinstance(item, dict)]
        return max(degrees, key=_education_rank, default="")
    return ""


def _language_satisfied(requirement: str, candidate_languages: list[str]) -> bool:
    required_text = requirement.casefold()
    required_name = required_text.split()[0] if required_text.split() else required_text
    level_rank = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6, "native": 7}
    required_level = max((rank for level, rank in level_rank.items() if level in required_text), default=0)
    for candidate in candidate_languages:
        candidate_text = candidate.casefold()
        if required_name and required_name not in candidate_text:
            continue
        candidate_level = max((rank for level, rank in level_rank.items() if level in candidate_text), default=0)
        if candidate_level >= required_level:
            return True
    return False


def screen_candidate(
    job_description: str | dict[str, Any], candidate_cv: str | dict[str, Any]
) -> str:
    """Score one CV against one JD using only job-related evidence.

    The evidence model supports required/preferred skills, experience,
    education, languages, and certifications. Personally identifying and
    sensitive fields never contribute to the score. Missing mandatory criteria
    apply transparent caps so a high optional score cannot hide a hard gap.
    """
    cv, cv_error = _decode_object(candidate_cv, "CV")
    if cv_error:
        return json.dumps({"status": "ERROR", "message": cv_error}, ensure_ascii=False)

    raw_experience = cv.get("total_experience_years", cv.get("experience"))
    candidate_experience = _experience_number(raw_experience) if raw_experience is not None else None
    if raw_experience is not None and (candidate_experience is None or candidate_experience > 60):
        return json.dumps(
            {"status": "FLAGGED", "reason": "Inconsistent candidate information"},
            ensure_ascii=False,
        )

    jd, jd_error = _decode_object(job_description, "Job Description")
    if jd_error:
        return json.dumps({"status": "ERROR", "message": jd_error}, ensure_ascii=False)

    required = jd.get("required_skills", [])
    preferred = jd.get("preferred_skills", [])
    candidate_skills = cv.get("skills", [])
    if not isinstance(required, list) or not isinstance(preferred, list) or not isinstance(candidate_skills, list):
        return json.dumps(
            {"status": "ERROR", "message": "Skills must be arrays."}, ensure_ascii=False
        )

    required_map = _normalized_items(required)
    preferred_map = _normalized_items(preferred)
    owned_map = _normalized_items(candidate_skills)
    owned = set(owned_map)
    missing = [original for normalized, original in required_map.items() if normalized not in owned]
    skill_score = 100.0 if not required_map else 100.0 * (len(required_map) - len(missing)) / len(required_map)
    missing_preferred = [original for normalized, original in preferred_map.items() if normalized not in owned]
    preferred_score = 100.0 if not preferred_map else 100.0 * (len(preferred_map) - len(missing_preferred)) / len(preferred_map)

    has_experience_criterion = jd.get("experience") not in (None, "")
    required_experience = _experience_number(jd.get("experience")) if has_experience_criterion else None
    if has_experience_criterion and (required_experience is None or required_experience < 0):
        return json.dumps(
            {"status": "ERROR", "message": "Job experience requirement is invalid."},
            ensure_ascii=False,
        )
    experience_score = 100.0
    if required_experience and required_experience > 0:
        experience_score = min(100.0, 100.0 * (candidate_experience or 0) / required_experience)

    minimum_education = str(jd.get("minimum_education", "")).strip()
    candidate_degree = _candidate_degree(cv)
    education_score = 100.0 if not minimum_education else (
        100.0 if _education_rank(candidate_degree) >= _education_rank(minimum_education) else 0.0
    )

    required_languages = [str(item) for item in jd.get("required_languages", [])]
    candidate_languages = [str(item) for item in cv.get("languages", [])]
    matched_languages = [item for item in required_languages if _language_satisfied(item, candidate_languages)]
    language_score = 100.0 if not required_languages else 100.0 * len(matched_languages) / len(required_languages)

    required_certifications = _normalized_items(jd.get("required_certifications", []))
    candidate_certifications = _normalized_items(cv.get("certifications", []))
    missing_certifications = [
        original for normalized, original in required_certifications.items()
        if normalized not in candidate_certifications
    ]
    certification_score = 100.0 if not required_certifications else (
        100.0 * (len(required_certifications) - len(missing_certifications)) / len(required_certifications)
    )

    components: list[tuple[str, float, float]] = []
    if required_map:
        components.append(("required_skills", 50.0, skill_score))
    if has_experience_criterion:
        components.append(("experience", 25.0, experience_score))
    if minimum_education:
        components.append(("education", 10.0, education_score))
    if preferred_map:
        components.append(("preferred_skills", 5.0, preferred_score))
    if required_languages:
        components.append(("languages", 5.0, language_score))
    if required_certifications:
        components.append(("certifications", 5.0, certification_score))
    if not components:
        return json.dumps(
            {"status": "ERROR", "message": "Job Description has no screening criteria."},
            ensure_ascii=False,
        )

    available_weight = sum(weight for _, weight, _ in components)
    score = sum(weight * component_score / 100 for _, weight, component_score in components)
    score = 100.0 * score / available_weight

    # Mandatory gates are explicit and deterministic.
    if required_map and len(missing) == len(required_map):
        score = min(score, 30.0)
    elif missing:
        score = min(score, 79.0)
    experience_ratio = 1.0
    if required_experience and required_experience > 0:
        experience_ratio = (candidate_experience or 0) / required_experience
        if experience_ratio < 0.6:
            score = min(score, 59.0)
    if education_score == 0 or language_score < 100 or missing_certifications:
        score = min(score, 79.0)

    rounded = round(score, 1)
    status = "PASS" if rounded >= PASS_THRESHOLD else "REVIEW" if rounded >= REVIEW_THRESHOLD else "REJECT"
    result = {
        "status": status,
        "score": rounded,
        "candidate_id": cv.get("candidate_id"),
        "position": jd.get("position"),
        "matched_skills": [original for normalized, original in required_map.items() if normalized in owned],
        "missing_skills": missing,
        "matched_preferred_skills": [original for normalized, original in preferred_map.items() if normalized in owned],
        "missing_preferred_skills": missing_preferred,
        "experience": {
            "candidate_years": candidate_experience,
            "required_years": required_experience,
            "criterion_used": has_experience_criterion,
            "score": round(experience_score, 1) if has_experience_criterion else None,
        },
        "education": {"candidate_degree": candidate_degree, "minimum": minimum_education, "meets": education_score == 100},
        "languages": {"matched": matched_languages, "required": required_languages},
        "missing_certifications": missing_certifications,
        "score_breakdown": {name: round(component_score, 1) for name, _, component_score in components},
        "ignored_for_scoring": ["name", "email", "phone", "address", "age", "gender", "marital_status"],
        "schedule_interview": status == "PASS",
    }
    return json.dumps(result, ensure_ascii=False)


def check_interviewer_calendar(scenario: str) -> str:
    """Read deterministic interviewer availability for ``available``/``unavailable``."""
    key = scenario.strip().lower() if isinstance(scenario, str) else ""
    if key not in AVAILABLE_SLOTS:
        return json.dumps({"status": "ERROR", "message": "Unknown calendar scenario."})
    slots = AVAILABLE_SLOTS[key]
    return json.dumps(
        {"calendar_checked": True, "available_slots": slots, "has_slot": bool(slots)},
        ensure_ascii=False,
    )


def book_interview(candidate_name: str, slot: str, confirmation: str) -> str:
    """Book a slot only with exact ``CONFIRMED`` approval; idempotent by candidate."""
    name = candidate_name.strip() if isinstance(candidate_name, str) else ""
    chosen = slot.strip() if isinstance(slot, str) else ""
    if confirmation != "CONFIRMED":
        return json.dumps({"status": "ERROR", "message": "HR confirmation required."})
    if not name or chosen not in AVAILABLE_SLOTS["available"]:
        return json.dumps({"status": "ERROR", "message": "Candidate or slot is invalid."})
    existing = SCHEDULED_INTERVIEWS.get(name)
    if existing:
        chosen = existing
    else:
        SCHEDULED_INTERVIEWS[name] = chosen
    return json.dumps(
        {"status": "BOOKED", "interview_booked": True, "candidate": name, "slot": chosen, "booking_id": "IV-TC004"},
        ensure_ascii=False,
    )


def generate_invitation_email(candidate_name: str, position: str, slot: str) -> str:
    """Generate, but do not send, a privacy-safe interview invitation draft."""
    if not all(isinstance(item, str) and item.strip() for item in (candidate_name, position, slot)):
        return json.dumps({"status": "ERROR", "message": "Email fields are incomplete."})
    body = (
        f"Kính gửi {candidate_name}, trân trọng mời bạn phỏng vấn vị trí {position} "
        f"vào {slot}. Vui lòng phản hồi để xác nhận."
    )
    return json.dumps({"email_generated": True, "sent": False, "draft": body}, ensure_ascii=False)


def suggest_new_slots() -> str:
    """Suggest follow-up windows without claiming calendar availability."""
    return json.dumps(
        {"suggest_new_slots": True, "suggestion": "Yêu cầu interviewer cung cấp thêm khung giờ trong 3 ngày làm việc tới."},
        ensure_ascii=False,
    )


AVAILABLE_TOOLS: dict[str, Callable[..., str]] = {
    "screen_candidate": screen_candidate,
    "check_interviewer_calendar": check_interviewer_calendar,
    "book_interview": book_interview,
    "generate_invitation_email": generate_invitation_email,
    "suggest_new_slots": suggest_new_slots,
}

TOOL_SCHEMAS = {
    "screen_candidate": {"parameters": ["job_description_json", "candidate_cv_json"], "side_effect": False},
    "check_interviewer_calendar": {"parameters": ["scenario"], "side_effect": False},
    "book_interview": {"parameters": ["candidate_name", "slot", "confirmation"], "side_effect": True, "requires_confirmation": True},
    "generate_invitation_email": {"parameters": ["candidate_name", "position", "slot"], "side_effect": False},
    "suggest_new_slots": {"parameters": [], "side_effect": False},
}


# ---------------------------------------------------------------------------
# PDF -> JSON preprocessing tools (kept here to match the required skeleton)
# ---------------------------------------------------------------------------

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 20


class PdfExtractionError(ValueError):
    """Safe user-facing error raised for unsupported PDF inputs."""


def _pdf_text(data: bytes) -> tuple[list[str], str]:
    if not data or len(data) > MAX_PDF_BYTES:
        raise PdfExtractionError("PDF rỗng hoặc vượt giới hạn 10 MB.")
    if not data.startswith(b"%PDF"):
        raise PdfExtractionError("File tải lên không phải PDF hợp lệ.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfExtractionError("Thiếu pypdf. Chạy: python -m pip install pypdf") from exc
    try:
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PdfExtractionError("PDF có mật khẩu; hãy bỏ mật khẩu trước khi tải lên.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise PdfExtractionError("PDF vượt giới hạn 20 trang.")
        pages = [(page.extract_text() or "") for page in reader.pages]
    except PdfExtractionError:
        raise
    except Exception as exc:
        raise PdfExtractionError(f"Không đọc được PDF: {exc}") from exc
    text = "\n".join(pages).strip()
    if len(text) < 80:
        raise PdfExtractionError("PDF scan không có lớp text; hãy OCR trước khi tải lên.")
    return pages, text


def _pdf_lines(text: str) -> list[str]:
    joined: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if joined and joined[-1].endswith("-") and line and line[0].islower():
            joined[-1] = joined[-1][:-1] + line
        elif line:
            joined.append(line)
    return [re.sub(r"\s+", " ", line).strip(" •●▪◦-") for line in joined if line.strip(" •●▪◦-")]


def _pdf_sections(lines: list[str], aliases: dict[str, set[str]]) -> tuple[list[str], dict[str, list[str]]]:
    header: list[str] = []
    sections = {name: [] for name in aliases}
    current: str | None = None
    for line in lines:
        normalized = re.sub(r"[^\wÀ-ỹ ]", "", line.casefold()).strip()
        detected = next((name for name, values in aliases.items() if normalized in values), None)
        if detected:
            current = detected
        elif current:
            sections[current].append(line)
        else:
            header.append(line)
    return header, sections


def _pdf_list(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        for item in re.split(r"\s*[,;|/]\s*", line):
            value = item.strip(" .-")
            if value and value.casefold() not in {entry.casefold() for entry in result}:
                result.append(value)
    return result


def _pdf_experience(text: str) -> float | None:
    explicit = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|năm)\b", text, re.I)]
    plausible = [value for value in explicit if value <= 60]
    if plausible:
        return max(plausible)
    months = {name: i for i, name in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
    ranges = re.findall(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\s*[-–]\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})", text, re.I)
    total = sum(max(0, (int(ey) - int(sy)) * 12 + months[em[:3].lower()] - months[sm[:3].lower()] + 1) for sm, sy, em, ey in ranges)
    return round(total / 12, 1) if total else None


def _pdf_degree(text: str) -> str:
    lowered = text.casefold()
    for degree, words in (("PhD", ("phd", "tiến sĩ")), ("Master", ("master", "thạc sĩ")), ("Bachelor", ("bachelor", "engineer", "cử nhân", "kỹ sư")), ("Associate", ("associate", "cao đẳng"))):
        if any(word in lowered for word in words):
            return degree
    return ""


def pdf_to_cv_json(data: bytes, filename: str = "candidate_cv.pdf") -> dict[str, Any]:
    """Convert a text-based CV PDF to editable JSON; never invent missing data."""
    pages, text = _pdf_text(data)
    aliases = {
        "summary": {"summary", "professional summary", "profile", "objective", "career objective", "mục tiêu nghề nghiệp"},
        "skills": {"skills", "technical skills", "kỹ năng"},
        "experience": {"experience", "work experience", "professional experience", "kinh nghiệm làm việc"},
        "education": {"education", "education background", "academic background", "học vấn"},
        "projects": {"projects", "technical projects", "selected projects", "dự án"},
        "certifications": {"certifications", "certificates", "chứng chỉ"},
        "languages": {"languages", "language", "ngoại ngữ"},
    }
    header, sections = _pdf_sections(_pdf_lines(text), aliases)
    email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    phone = re.search(r"(?:\+?84|0)[\d .()-]{8,14}\d", text)
    name = next((line for line in header[:6] if 2 <= len(line.split()) <= 7 and "@" not in line and not re.search(r"\d{5,}", line)), "")
    groups = {"technical": [], "hardware": [], "languages": [], "soft": []}
    current = "technical"
    for line in sections["skills"]:
        match = re.match(r"^(Technical Skills|Hardware & Tools|Languages|Soft Skills)\s*:\s*(.*)$", line, re.I)
        if match:
            label = match.group(1).casefold()
            current = "hardware" if "hardware" in label else "languages" if "language" in label else "soft" if "soft" in label else "technical"
            line = match.group(2)
        if line:
            groups[current].append(line)
    skills = _pdf_list(groups["technical"] + groups["hardware"])
    catalog = ["C++", "C", "Python", "SQL", "Docker", "Embedded", "IoT", "RTOS", "CAN", "UART", "SPI", "I2C", "ADC", "PWM", "STM32", "ESP32"]
    for item in catalog:
        if re.search(rf"(?<![A-Za-z0-9+]){re.escape(item)}(?![A-Za-z0-9+])", text, re.I) and item.casefold() not in {skill.casefold() for skill in skills}:
            skills.append(item)
    years = _pdf_experience("\n".join(sections["experience"]))
    warnings = [] if skills else ["Không nhận diện được skills; hãy bổ sung thủ công."]
    if years is None:
        warnings.append("Không nhận diện được tổng số năm kinh nghiệm.")
    return {
        "candidate_id": "PDF-" + re.sub(r"[^A-Za-z0-9]+", "-", Path(filename).stem).strip("-").upper()[:40],
        "personal_information": {"name": name, "email": email.group(0) if email else "", "phone": phone.group(0).strip() if phone else ""},
        "professional_summary": "\n".join(sections["summary"]), "skills": skills,
        "total_experience_years": years,
        "work_experience": [{"raw_text": "\n".join(sections["experience"])}] if sections["experience"] else [],
        "education": [{"degree": _pdf_degree("\n".join(sections["education"])), "raw_text": "\n".join(sections["education"])}] if sections["education"] else [],
        "projects": [{"raw_text": "\n".join(sections["projects"])}] if sections["projects"] else [],
        "certifications": _pdf_list(sections["certifications"]),
        "languages": _pdf_list(sections["languages"] or groups["languages"]),
        "extraction_metadata": {"source_filename": Path(filename).name, "page_count": len(pages), "requires_human_review": True},
        "extraction_warnings": warnings,
    }


def pdf_to_jd_json(data: bytes, filename: str = "job_description.pdf") -> dict[str, Any]:
    """Convert a text-based JD PDF to editable JSON; omit absent criteria."""
    pages, text = _pdf_text(data)
    aliases = {
        "summary": {"summary", "job summary", "job overview", "giới thiệu chung", "thông tin tuyển dụng"},
        "responsibilities": {"responsibilities", "key responsibilities", "duties", "mô tả công việc", "nhiệm vụ"},
        "required": {"required skills", "must have", "kỹ năng bắt buộc"},
        "preferred": {"preferred skills", "nice to have", "kỹ năng ưu tiên"},
        "qualifications": {"requirements", "qualifications", "yêu cầu", "yêu cầu công việc", "yêu cầu ứng viên"},
        "benefits": {"benefits", "what we offer", "quyền lợi"},
    }
    header, sections = _pdf_sections(_pdf_lines(text), aliases)
    position_match = re.search(r"(?:position|job title|vị trí)\s*[:\-]\s*(.{2,100}?)(?=\s+số lượng|\s+thời gian|\s+địa điểm|\n)", text, re.I)
    position = position_match.group(1).strip() if position_match else (header[0] if header else "")
    blob_match = re.search(r"(?:là sinh viên năm cuối|candidate requirements|requirements)(.*?)(?:được nhận trợ cấp|what we offer|ứng viên vui lòng)", text, re.I | re.S)
    qualification_blob = blob_match.group(0) if blob_match else "\n".join(sections["qualifications"])
    required = _pdf_list(sections["required"])
    catalog = ["C++", "C", "Python", "SQL", "Docker", "Embedded", "IoT", "RTOS", "CAN", "UART", "SPI", "I2C", "ADC", "PWM"]
    found = [item for item in catalog if re.search(rf"(?<![A-Za-z0-9+]){re.escape(item)}(?![A-Za-z0-9+])", qualification_blob, re.I)]
    if not required:
        required = [item for item in found if item in {"C", "C++", "Python", "SQL", "Docker"}]
    preferred = _pdf_list(sections["preferred"]) or [item for item in found if item not in required]
    years = _pdf_experience(text)
    languages = ["English B2"] if re.search(r"TOEIC\s*750|IELTS\s*6", qualification_blob, re.I) else []
    warnings = [] if required else ["Không nhận diện được required_skills; hãy bổ sung thủ công."]
    if years is None:
        warnings.append("JD không nêu số năm kinh nghiệm; tiêu chí này được bỏ qua." if "fresher" in position.casefold() else "Không nhận diện được kinh nghiệm tối thiểu.")
    result = {
        "job_id": "PDF-" + re.sub(r"[^A-Za-z0-9]+", "-", Path(filename).stem).strip("-").upper()[:40],
        "position": position, "summary": "\n".join(sections["summary"]),
        "responsibilities": sections["responsibilities"], "required_skills": required,
        "preferred_skills": preferred, "minimum_education": _pdf_degree(qualification_blob),
        "required_languages": languages, "required_certifications": [], "benefits": sections["benefits"],
        "raw_qualifications": sections["qualifications"],
        "extraction_metadata": {"source_filename": Path(filename).name, "page_count": len(pages), "requires_human_review": True},
        "extraction_warnings": warnings,
    }
    if years is not None:
        result["experience"] = years
    return result
