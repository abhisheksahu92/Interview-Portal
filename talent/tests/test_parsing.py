import pytest

from talent.parsing import (
    find_email,
    find_experience_years,
    find_name,
    find_phone,
    name_from_filename,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("5 years of experience", 5.0),
        ("5 years experience", 5.0),
        ("5 yrs exp", 5.0),
        ("1 year of experience", 1.0),
        ("2.5 years of experience", 2.5),
        ("10+ years of experience", 10.0),
        ("12+ yrs exp", 12.0),
        ("10 years in experience", 10.0),
        ("I have 4.5 yrs of exp in Python.", 4.5),
        ("Experience: 8 years", 8.0),
        ("15 YRS EXPERIENCE", 15.0),
        ("20+ years", 20.0),
    ],
)
def test_find_experience_years_formats(text, expected):
    assert find_experience_years(text) == expected


def test_find_experience_years_max_value():
    text = "Started with 2 years of experience in Java, now have 8 years of experience in Python."
    assert find_experience_years(text) == 8.0


@pytest.mark.parametrize(
    "text",
    [
        "100 years of experience",
        "0 years of experience",
        "61 years of experience",
        "70 yrs exp",
        "No experience",
        "12345",
        "",
        None,
    ],
)
def test_find_experience_years_invalid_or_missing(text):
    assert find_experience_years(text) is None


def test_find_phone_basic():
    assert find_phone("+1 (555) 123-4567") == "+15551234567"
    assert find_phone("+91 98765 43210") == "+919876543210"
    assert find_phone("555-123-4567") == "5551234567"
    assert find_phone("555.123.4567") == "5551234567"
    assert find_phone("My number is +44 20 7123 1234.") == "+442071231234"


def test_find_phone_edge_cases():
    assert find_phone("") == ""
    assert find_phone(None) == ""
    assert find_phone("Call me maybe") == ""


def test_find_phone_length_limits():
    assert find_phone("123-45") == ""
    assert find_phone("555-0100") == "5550100"
    assert find_phone("1234567890123456") == ""
    assert find_phone("+123456789012345") == "+123456789012345"


def test_find_phone_multiple():
    assert find_phone("Office: 555-0100, Mobile: +1 (555) 123-4567") == "5550100"
    assert find_phone("Fax: 123, Phone: +1 (555) 123-4567") == "+15551234567"


def test_find_phone_regex_boundaries():
    assert find_phone("john@1234567.com") == ""
    assert find_phone("v123.456.7890") == "1234567890"
    assert find_phone("ID: 12345678901234567890") == ""


def test_find_email_success():
    assert find_email("test@example.com") == "test@example.com"
    assert find_email("Contact me at test@example.com") == "test@example.com"
    assert find_email("TEST@example.com") == "test@example.com"
    assert find_email("tEsT@eXaMpLe.CoM") == "test@example.com"
    assert find_email("test@mail.example.co.uk") == "test@mail.example.co.uk"
    assert find_email("my.name+tag@domain.co.uk") == "my.name+tag@domain.co.uk"
    assert find_email("user-name@domain-name.com") == "user-name@domain-name.com"


def test_find_email_not_found():
    assert find_email("No email here") == ""
    assert find_email("user@domain") == ""
    assert find_email("user.domain.com") == ""
    assert find_email("") == ""
    assert find_email(None) == ""


def test_find_email_multiple():
    assert find_email("First first@example.com and second@example.com") == "first@example.com"


def test_find_name_basic_extraction():
    text = "John Doe\nSoftware Engineer\nExperience: 5 years"
    assert find_name(text) == "John Doe"


def test_find_name_capitalization():
    text = "JANE SMITH\nData Scientist\n"
    assert find_name(text) == "Jane Smith"

    text = "Alan Turing\nComputer Scientist"
    assert find_name(text) == "Alan Turing"


def test_find_name_stopwords():
    text = "Resume\nCurriculum Vitae\nAlice Wonderland"
    assert find_name(text) == "Alice Wonderland"

    text = "Profile Summary\nBob Builder"
    assert find_name(text) == "Bob Builder"


def test_find_name_email_filtering():
    text = "john.doe@example.com\nJohn Doe"
    assert find_name(text) == "John Doe"


def test_find_name_number_filtering():
    text = "123 Main St\n+1 555-1234\nCharlie Brown"
    assert find_name(text) == "Charlie Brown"


def test_find_name_fallback_to_filename():
    text = "Resume\nSkills: Python, Java\nExperience\nEducation"
    assert find_name(text, filename="asha_rao_resume.pdf") == "Asha Rao"

    text = "Resume\nSkills: Python, Java\nExperience\nEducation"
    assert find_name(text, filename="asha_rao_resume_updated_copy_123.pdf") == "Asha Rao"

    text = ""
    assert find_name(text, filename="John_Doe_CV.pdf") == "John Doe"


def test_name_from_filename():
    assert name_from_filename("asha_rao_resume.pdf") == "Asha Rao"
    assert name_from_filename("asha_rao_resume_updated_copy_123.pdf") == "Asha Rao"
    assert name_from_filename("John_Doe_CV.pdf") == "John Doe"
    assert name_from_filename("ALICE_WONDERLAND_FINAL.docx") == "Alice Wonderland"
    assert name_from_filename("bob-builder-profile.pdf") == "Bob Builder"


def test_find_name_empty_or_none():
    assert find_name(None) == ""
    assert find_name("") == ""
    assert find_name(None, filename="test_file.pdf") == "Test File"
