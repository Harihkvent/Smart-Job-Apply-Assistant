import json
import os
import time

import requests


def tailor_resume(job, profile, config):
    """Tailor resume and cover text for a specific job using Krutrim LLM."""
    messages = _build_prompt(job, profile)
    tailor_result = _call_llm(messages, config)
    resume_path = _generate_resume_pdf(profile, tailor_result, config, job=job)
    tailor_result["resume_pdf_path"] = resume_path
    return tailor_result


def _build_prompt(job, profile):
    """Build system and user messages for the LLM."""
    system_msg = (
        "You are an assistant that tailors a candidate's resume bullets "
        "and a short cover blurb for a job application. Be concise and "
        "prefer measurable results. Do not fabricate facts. Output only "
        "valid JSON."
    )

    jd_section = job.get("jd_text")
    if not jd_section:
        role = job.get("role", "")
        company = job.get("company", "")
        jd_section = f"Role: {role}, Company: {company}"

    user_msg = (
        f"Job Description:\n{jd_section}\n\n"
        f"Candidate Profile:\n{json.dumps(profile, default=str)}\n\n"
        "Return a JSON object with exactly these keys:\n"
        "{\n"
        '  "cover_text": "150-word persuasive paragraph focusing on fit and achievements",\n'
        '  "resume_bullets": ["bullet1", "bullet2", "bullet3"],\n'
        '  "skills_to_highlight": ["python", "docker"]\n'
        "}"
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _call_llm(messages, config):
    """Make HTTP POST request to the Krutrim API and return parsed JSON."""
    default = {"cover_text": "", "resume_bullets": [], "skills_to_highlight": []}

    endpoint = config.get("llm_endpoint", "https://cloud.olakrutrim.com/v1")
    model = config.get("llm_model", "Krutrim-spectre-v2")
    api_key = config.get("llm_api_key", "")

    url = f"{endpoint}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
    except requests.RequestException:
        return dict(default)

    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return dict(default)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        return dict(default)

    for key in default:
        if key not in result:
            result[key] = default[key]

    return result


def _generate_resume_pdf(profile, tailor_result, config, job=None):
    """Generate a plain-text tailored resume and return its file path."""
    temp_dir = os.path.abspath(config.get("tailor_temp_dir", "/tmp/tailor_resumes"))
    os.makedirs(temp_dir, exist_ok=True)

    company = (job or {}).get("company") or profile.get("company", "unknown")
    timestamp = int(time.time())
    filename = f"resume_{company}_{timestamp}.txt"
    filepath = os.path.join(temp_dir, filename)

    lines = []
    lines.append(profile.get("name", ""))
    contact_parts = [
        profile.get("email", ""),
        profile.get("phone", ""),
        profile.get("location", ""),
        profile.get("linkedin", ""),
    ]
    lines.append(" | ".join(p for p in contact_parts if p))
    lines.append("")

    skills = tailor_result.get("skills_to_highlight", [])
    if skills:
        lines.append("Skills: " + ", ".join(skills))
        lines.append("")

    bullets = tailor_result.get("resume_bullets", [])
    if bullets:
        lines.append("Tailored Highlights:")
        for bullet in bullets:
            lines.append(f"  - {bullet}")
        lines.append("")

    for exp in profile.get("experience", []):
        if isinstance(exp, dict):
            lines.append(f"{exp.get('title', '')} at {exp.get('company', '')}")
            for b in exp.get("bullets", []):
                lines.append(f"  - {b}")
            lines.append("")
        else:
            lines.append(str(exp))

    education_parts = [
        profile.get("degree", ""),
        profile.get("cgpa", ""),
        profile.get("graduation_date", ""),
    ]
    edu_line = " | ".join(str(p) for p in education_parts if p)
    if edu_line:
        lines.append("Education:")
        lines.append(f"  {edu_line}")
        lines.append("")

    cover = tailor_result.get("cover_text", "")
    if cover:
        lines.append("Cover Text:")
        lines.append(cover)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return filepath
