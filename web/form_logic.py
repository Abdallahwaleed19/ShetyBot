"""Pure form calculations shared by the API and unit tests."""

from datetime import date


def inclusive_duration(admission: date, discharge: date) -> int:
    """Return the inclusive number of calendar days, rejecting reversed dates."""
    if discharge < admission:
        raise ValueError("discharge date precedes admission date")
    return (discharge - admission).days + 1
