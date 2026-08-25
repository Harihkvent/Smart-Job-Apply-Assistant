"""Tests for src.tailor module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

from src.tailor import _build_prompt, _call_llm, _generate_resume_pdf, tailor_resume

SAMPLE_JOB = {
    "company": "TestCorp",
    "role": "Backend Developer",
    "jd_text": "We need a Python developer with Flask experience.",
}

SAMPLE_PROFILE = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "555-1234",
    "location": "Remote",
    "linkedin": "https://linkedin.com/in/janedoe",
    "experience": [
        {
            "title": "Software Engineer",
            "company": "PrevCo",
            "bullets": ["Built REST APIs", "Improved CI/CD pipeline"],
        }
    ],
    "degree": "B.S. Computer Science",
    "cgpa": "3.8",
    "graduation_date": "2020",
}

SAMPLE_CONFIG = {
    "llm_endpoint": "https://cloud.olakrutrim.com/v1",
    "llm_model": "Krutrim-spectre-v2",
    "llm_api_key": "test-key",
    "tailor_temp_dir": "/tmp/test_tailor",
}

LLM_RESPONSE_CONTENT = json.dumps({
    "cover_text": "test cover",
    "resume_bullets": ["bullet1"],
    "skills_to_highlight": ["python"],
})

MOCK_API_RESPONSE = {
    "choices": [{"message": {"content": LLM_RESPONSE_CONTENT}}]
}


def test_build_prompt():
    """Verify prompt structure contains JD and profile info."""
    messages = _build_prompt(SAMPLE_JOB, SAMPLE_PROFILE)

    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    user_content = messages[1]["content"]
    assert "Python developer" in user_content
    assert "Jane Doe" in user_content
    assert "Backend Developer" not in messages[0]["content"]


def test_build_prompt_no_jd():
    """When jd_text is missing, uses role and company instead."""
    job = {"company": "Acme", "role": "Dev"}
    messages = _build_prompt(job, SAMPLE_PROFILE)

    user_content = messages[1]["content"]
    assert "Acme" in user_content
    assert "Dev" in user_content


@patch("src.tailor.requests.post")
def test_call_llm_success(mock_post):
    """Mock requests.post to return valid JSON, verify parsing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = MOCK_API_RESPONSE
    mock_post.return_value = mock_resp

    messages = [{"role": "user", "content": "test"}]
    result = _call_llm(messages, SAMPLE_CONFIG)

    assert result["cover_text"] == "test cover"
    assert result["resume_bullets"] == ["bullet1"]
    assert result["skills_to_highlight"] == ["python"]

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "chat/completions" in call_kwargs[0][0] or "chat/completions" in call_kwargs.kwargs.get("url", call_kwargs[0][0])


@patch("src.tailor.requests.post")
def test_call_llm_failure(mock_post):
    """Mock requests.post to raise exception, verify fallback defaults."""
    mock_post.side_effect = requests_lib.RequestException("connection error")

    messages = [{"role": "user", "content": "test"}]
    result = _call_llm(messages, SAMPLE_CONFIG)

    assert result["cover_text"] == ""
    assert result["resume_bullets"] == []
    assert result["skills_to_highlight"] == []


@patch("src.tailor._call_llm")
def test_tailor_resume_integration(mock_call_llm, tmp_path):
    """Mock _call_llm, verify full pipeline returns expected keys."""
    mock_call_llm.return_value = {
        "cover_text": "tailored cover",
        "resume_bullets": ["b1", "b2"],
        "skills_to_highlight": ["python", "flask"],
    }

    config = {**SAMPLE_CONFIG, "tailor_temp_dir": str(tmp_path / "resumes")}
    result = tailor_resume(SAMPLE_JOB, SAMPLE_PROFILE, config)

    assert "cover_text" in result
    assert "resume_bullets" in result
    assert "skills_to_highlight" in result
    assert "resume_pdf_path" in result
    assert os.path.exists(result["resume_pdf_path"])


def test_generate_resume_pdf(tmp_path):
    """Verify file is created in temp dir."""
    tailor_result = {
        "cover_text": "great cover letter",
        "resume_bullets": ["did X", "achieved Y"],
        "skills_to_highlight": ["python", "docker"],
    }
    config = {"tailor_temp_dir": str(tmp_path / "resumes")}

    path = _generate_resume_pdf(SAMPLE_PROFILE, tailor_result, config, job=SAMPLE_JOB)

    assert os.path.exists(path)
    assert path.endswith(".txt")

    content = open(path, "r").read()
    assert "Jane Doe" in content
    assert "python" in content
    assert "great cover letter" in content
