"""
bot/states.py — ConversationHandler state constants.
"""

# ── Page 1: Leave & Report Details ───────────────────────────────────────────
REPORT_TYPE       = 0
ADMISSION_DATE    = 1
DISCHARGE_DATE    = 2
ISSUE_DATE        = 3
ISSUE_TIME        = 4

# ── Page 2: Patient Information ───────────────────────────────────────────────
NATIONAL_ID       = 5
PATIENT_NAME_AR   = 6
PATIENT_NAME_EN   = 7
NATIONALITY       = 8
EMPLOYER          = 9

# ── Page 3: Practitioner & Hospital ──────────────────────────────────────────
PRACT_NAME_AR     = 10
PRACT_NAME_EN     = 11
PRACT_POS_AR      = 12
PRACT_POS_EN      = 13
HOSPITAL_NAME_AR  = 14
HOSPITAL_NAME_EN  = 15
HOSPITAL_TYPE     = 16
HOSPITAL_LOGO     = 17

# Confirmation / done
CONFIRM           = 18
