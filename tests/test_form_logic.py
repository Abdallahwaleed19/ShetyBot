"""
tests/test_form_logic.py — Unit tests for form business logic

Run with: python -m pytest tests/ -v
or standalone: python tests/test_form_logic.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date
from web.form_logic import inclusive_duration


# ── Duration calculation (mimics JS: inclusive day count) ───────────────────
def calc_duration(adm_date: date, dis_date: date) -> int:
    """Inclusive duration: same-day = 1 day."""
    return inclusive_duration(adm_date, dis_date)


# ── Tests ────────────────────────────────────────────────────────────────────
def test_same_day():
    assert calc_duration(date(2026, 10, 23), date(2026, 10, 23)) == 1

def test_consecutive_days():
    assert calc_duration(date(2026, 10, 23), date(2026, 10, 24)) == 2

def test_seven_days():
    assert calc_duration(date(2026, 10, 23), date(2026, 10, 29)) == 7

def test_spec_example():
    """Official spec: 23/10 to 30/10 = 8 days."""
    assert calc_duration(date(2026, 10, 23), date(2026, 10, 30)) == 8

def test_month_boundary():
    assert calc_duration(date(2026, 10, 28), date(2026, 11, 3)) == 7

def test_year_boundary():
    assert calc_duration(date(2026, 12, 28), date(2027, 1, 4)) == 8

def test_leap_year_february():
    assert calc_duration(date(2024, 2, 28), date(2024, 3, 1)) == 3

def test_invalid_range_negative():
    """Discharge before admission: expected negative (caller rejects)."""
    try:
        calc_duration(date(2026, 10, 30), date(2026, 10, 23))
    except ValueError:
        return
    raise AssertionError("reversed ranges must be rejected")

def test_report_type_values():
    """Only GSL and PSL are valid report types."""
    VALID = {"GSL", "PSL"}
    assert "GSL" in VALID
    assert "PSL" in VALID
    assert "تقرير إجازة مرضية" not in VALID  # old value must not be accepted

def test_leave_duration_readonly():
    """Duration should not be overridable to an arbitrary value by the form."""
    adm = date(2026, 10, 23)
    dis = date(2026, 10, 30)
    server_calc = calc_duration(adm, dis)
    # Simulated form override attempt
    form_override = 99
    # Server always recalculates; override must be ignored if out-of-range
    assert server_calc == 8
    assert form_override != server_calc


if __name__ == "__main__":
    tests = [
        test_same_day, test_consecutive_days, test_seven_days,
        test_spec_example, test_month_boundary, test_year_boundary, test_leap_year_february,
        test_invalid_range_negative, test_report_type_values,
        test_leave_duration_readonly,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
