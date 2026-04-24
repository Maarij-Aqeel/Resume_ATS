from app.utils.date_parser import months_between, normalize_date


def test_normalize_standard_formats():
    assert normalize_date("Jan 2021") == ("2021-01", False)
    assert normalize_date("January 2021") == ("2021-01", False)
    assert normalize_date("01/2021") == ("2021-01", False)
    assert normalize_date("2021-01") == ("2021-01", False)
    assert normalize_date("2021") == ("2021-01", False)


def test_present_tokens():
    for token in ("Present", "Current", "Now", "Ongoing", "Till date"):
        result, is_current = normalize_date(token)
        assert result is None
        assert is_current is True


def test_quarter():
    assert normalize_date("Q1 2021") == ("2021-01", False)
    assert normalize_date("Q4 2021") == ("2021-10", False)


def test_season():
    assert normalize_date("Spring 2021") == ("2021-03", False)
    assert normalize_date("Fall 2021") == ("2021-09", False)


def test_months_between():
    assert months_between("2020-01", "2021-01") == 12
    assert months_between("2020-01", "2020-06") == 5
    assert months_between(None, "2021-01") == 0
