from app.models.schemas import Experience, PersonalInfo, ResumeSchema


def test_email_normalization():
    p = PersonalInfo(email="  Foo@BAR.com  ")
    assert p.email == "foo@bar.com"


def test_invalid_email_nulled():
    p = PersonalInfo(email="not-an-email")
    assert p.email is None


def test_phone_e164():
    p = PersonalInfo(phone="(415) 555-1234")
    assert p.phone == "+14155551234"


def test_url_validation():
    p = PersonalInfo(linkedin_url="linkedin.com/in/foo")
    assert p.linkedin_url == "https://linkedin.com/in/foo"


def test_date_validation():
    e = Experience(start_date="2020-01", end_date="2021-06")
    assert e.start_date == "2020-01"
    assert e.end_date == "2021-06"


def test_bad_date_nulled():
    e = Experience(start_date="Jan 2020")  # not YYYY-MM
    assert e.start_date is None


def test_date_order_swap():
    e = Experience(start_date="2021-01", end_date="2020-01")
    # out-of-order dates get swapped
    assert e.start_date == "2020-01"
    assert e.end_date == "2021-01"


def test_empty_resume_valid():
    r = ResumeSchema()
    assert r.experience == []
    assert r.skills.technical == []
