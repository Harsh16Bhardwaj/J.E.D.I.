from datetime import date
from io import BytesIO

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter

from backend.schemas.learning import QuestionBank
from backend.services.learning import compare_skills, load_banks
from backend.services.resume import (
    ResumeError,
    extract_resume,
    parse_resume_text,
    work_months,
)

RESUME = """Ada Developer
ada@example.com
Location: Bengaluru, India
Summary
Frontend engineer building accessible products.
Skills
React, TypeScript, CSS
Work Experience
Engineer, Example Ltd
Jan 2022 - Dec 2023
Built React interfaces and deployed container images with Docker.
Projects
Portfolio — Built a Next.js portfolio with reusable components.
Education
BSc Computer Science, Example University, 2021
"""


def test_resume_separates_explicit_and_inferred_evidence():
    result = parse_resume_text(RESUME)
    assert "React" in result.explicit_skills
    assert "Docker" in result.explicit_skills
    assert "JavaScript" not in result.explicit_skills
    assert any(s.skill == "JavaScript" and s.evidence for s in result.inferred_skills)
    assert result.current_location == "Bengaluru, India"
    assert result.experience_years == 2
    assert result.projects and result.education and result.work_history
    assert "Frontend engineer" in result.summary


def test_non_resume_is_rejected_even_with_technology_keywords():
    with pytest.raises(ResumeError, match="resume"):
        parse_resume_text(
            "Docker React Python guide\n" + "How to build a container. " * 30
        )


def test_work_intervals_merge_and_ignore_education():
    assert (
        work_months("Jan 2020 - Dec 2021\nJul 2021 - Jun 2022", date(2026, 11, 1)) == 30
    )
    assert work_months("2020 - 2022", date(2026, 11, 1)) is None


def test_pdf_errors_are_distinct():
    for data, code in [
        (b"not a pdf", "INVALID_PDF"),
        (b"%PDF-1.7\nbroken", "INVALID_PDF"),
    ]:
        with pytest.raises(ResumeError) as error:
            extract_resume(data)
        assert error.value.code == code
    writer = PdfWriter()
    writer.add_blank_page(600, 800)
    output = BytesIO()
    writer.write(output)
    with pytest.raises(ResumeError) as error:
        extract_resume(output.getvalue())
    assert error.value.code == "UNREADABLE_RESUME"
    writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    with pytest.raises(ResumeError) as error:
        extract_resume(output.getvalue())
    assert error.value.code == "ENCRYPTED_PDF"


def test_skill_gap_aliases_negation_and_optional_requirements():
    evidence = parse_resume_text(RESUME)
    gap = compare_skills(
        "Must have React.js and Kubernetes. Docker is not required.\nPython is a plus.",
        ["React", "Docker"],
        evidence,
    )
    assert [x["skill"] for x in gap["matched"]] == ["React"]
    assert [x["skill"] for x in gap["missing"]] == ["Kubernetes", "Python"]
    assert gap["missing"][1]["requirement"] == "preferred"
    assert gap["missing"][0]["topicIds"] == []


def test_supplied_question_bank_and_invalid_counts():
    bank = load_banks()["react-rendering"]
    assert bank.question_count == 3
    assert bank.questions[0].answer.correct_option_id == "b"
    data = bank.model_dump(by_alias=True)
    data["questionCount"] = 2
    with pytest.raises(ValidationError):
        QuestionBank.model_validate(data)
    data["questionCount"] = 3
    data["questions"][0]["answer"]["correctOptionId"] = "unknown"
    with pytest.raises(ValidationError):
        QuestionBank.model_validate(data)


def test_mixed_job_clauses_do_not_erase_required_skills():
    gap = compare_skills(
        "React is required, but Docker is not required. "
        "No Kubernetes experience required.",
        ["Docker", "Kubernetes"],
        None,
    )
    assert [(x["skill"], x["requirement"]) for x in gap["missing"]] == [
        ("React", "required")
    ]


def test_distinct_skills_do_not_match_language_suffixes():
    from backend.services.resume import skill_names

    assert skill_names("React.js Next.js Node.js") == ["React", "Next.js", "Node.js"]


def make_resume_pdf(text=RESUME):
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(600, 800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    lines = [line.replace("—", "-") for line in text.splitlines()]
    commands = ["BT /F1 10 Tf 20 770 Td 14 TL"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({escaped}) Tj T*")
    commands.append("ET")
    stream.set_data("\n".join(commands).encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pdf_valid_resume_round_trip():
    result = extract_resume(make_resume_pdf())
    assert "React" in result.explicit_skills
    assert result.experience_years == 2


def test_question_bank_rejects_duplicate_options_and_distribution():
    data = load_banks()["react-rendering"].model_dump(by_alias=True)
    data["questions"][0]["options"][1]["id"] = "a"
    with pytest.raises(ValidationError):
        QuestionBank.model_validate(data)
    data = load_banks()["react-rendering"].model_dump(by_alias=True)
    data["difficultyDistribution"]["hard"] = 2
    with pytest.raises(ValidationError):
        QuestionBank.model_validate(data)


def test_isolated_pdf_worker_preserves_validation_errors():
    from backend.services.resume import extract_resume_isolated

    with pytest.raises(ResumeError) as error:
        extract_resume_isolated(b"%PDF-1.7\nbroken")
    assert error.value.code == "INVALID_PDF"


def test_requirements_keep_per_skill_levels_and_common_negation():
    gap = compare_skills("Python is required, React is optional.", [], None)
    assert [(x["skill"], x["requirement"]) for x in gap["missing"]] == [
        ("Python", "required"),
        ("React", "preferred"),
    ]
    for text in ["React is not essential.", "No experience with React is required."]:
        assert compare_skills(text, ["React"], None)["missing"] == []


def test_partial_work_history_is_unknown_instead_of_undercounted():
    assert work_months("Jan 2020 - Dec 2020\n2015 - 2019") is None
    result = parse_resume_text(
        RESUME.replace("Jan 2022 - Dec 2023", "Jan 2020 - Dec 2020\n2015 - 2019")
    )
    assert result.experience_years is None
    assert any("could not be calculated" in note for note in result.limitations)


def test_negated_resume_skill_does_not_suppress_a_learning_gap():
    result = parse_resume_text(
        RESUME.replace("React", "Vue").replace(
            "TypeScript, CSS", "TypeScript, CSS\nNo React experience"
        )
    )
    assert "React" not in result.explicit_skills
    assert not any(s.skill == "JavaScript" for s in result.inferred_skills)
    gap = compare_skills("React is required.", [], result)
    assert gap["missing"][0]["topicIds"] == ["react-rendering"]


def test_phone_only_resume_contact_is_supported():
    result = parse_resume_text(RESUME.replace("ada@example.com", "+91 98765 43210"))
    assert "+91 98765 43210" in result.contact
    assert not any("2022" in contact for contact in result.contact)


def test_bank_rejects_whitespace_only_question_text():
    data = load_banks()["react-rendering"].model_dump(by_alias=True)
    data["questions"][0]["question"] = "   "
    with pytest.raises(ValidationError):
        QuestionBank.model_validate(data)
