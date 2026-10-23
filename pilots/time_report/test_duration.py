from duration import format_duration


def test_zero():
    assert format_duration(0) == "0:00"
