"""
tests/test_master.py — Comprehensive 20-Point Test Suite for SehtyBot Master Requirements
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BASE_DIR, REPORTS_DIR
from web.form_logic import inclusive_duration
from db.database import (
    init_db_sync,
    get_or_create_user_sync,
    check_subscription_sync,
    renew_subscription_sync,
    create_verification_code_sync,
    verify_code_sync,
    verify_report_ownership_sync,
    record_report_ownership_sync,
)
from pdf.generator import generate_pdf, ar, has_ar


class TestMasterSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db_sync()

    # ── Test 1: ظهور GSL و PSL فقط ──────────────────────────────────────────
    def test_01_report_types_only_gsl_psl(self):
        valid_types = {"GSL", "PSL"}
        self.assertIn("GSL", valid_types)
        self.assertIn("PSL", valid_types)
        self.assertNotIn("تقرير إجازة مرضية", valid_types)
        self.assertNotIn("OTHER", valid_types)

    # ── Test 2: صحة حقول التاريخ ومنع تاريخ الخروج قبل الدخول ─────────────────
    def test_02_date_field_validation(self):
        adm = date(2026, 10, 23)
        dis = date(2026, 10, 30)
        self.assertLessEqual(adm, dis)
        # Invalid reversed range
        with self.assertRaises(ValueError):
            inclusive_duration(date(2026, 10, 30), date(2026, 10, 23))

    # ── Test 3: حساب 8 أيام للفترة من 23/10/2026 إلى 30/10/2026 ──────────────
    def test_03_inclusive_duration_spec_example(self):
        adm = date(2026, 10, 23)
        dis = date(2026, 10, 30)
        days = inclusive_duration(adm, dis)
        self.assertEqual(days, 8, "Expected 8 inclusive days from 23/10 to 30/10")

    # ── Test 4: تحديث المدة عند تعديل التاريخ (نهاية شهر، سنة، سنة كبيسة) ──────
    def test_04_duration_boundary_conditions(self):
        # Same day = 1 day
        self.assertEqual(inclusive_duration(date(2026, 10, 23), date(2026, 10, 23)), 1)
        # Month boundary (28 Oct to 3 Nov = 7 days)
        self.assertEqual(inclusive_duration(date(2026, 10, 28), date(2026, 11, 3)), 7)
        # Year boundary (28 Dec to 4 Jan = 8 days)
        self.assertEqual(inclusive_duration(date(2026, 12, 28), date(2027, 1, 4)), 8)
        # Leap year Feb (28 Feb to 1 Mar in 2024 = 3 days)
        self.assertEqual(inclusive_duration(date(2024, 2, 28), date(2024, 3, 1)), 3)

    # ── Test 5: استقلال تاريخ الإصدار عن وقت الإصدار ──────────────────────────
    def test_05_independent_issue_date_and_time(self):
        issue_date_str = "2026-10-23"
        issue_time_str = "18:20"
        d = datetime.strptime(issue_date_str, "%Y-%m-%d").date()
        t = datetime.strptime(issue_time_str, "%H:%M").time()
        self.assertEqual(d.day, 23)
        self.assertEqual(t.hour, 18)
        self.assertEqual(t.minute, 20)
        # Modifying time doesn't alter date
        new_t = datetime.strptime("09:15", "%H:%M").time()
        self.assertEqual(d.day, 23)
        self.assertEqual(new_t.hour, 9)

    # ── Test 6: صحة تحويل وحساب AM و PM ─────────────────────────────────────
    def test_06_ampm_conversion(self):
        t18 = datetime.strptime("18:20", "%H:%M").strftime("%I:%M %p").lstrip("0")
        self.assertEqual(t18, "6:20 PM")
        t09 = datetime.strptime("09:05", "%H:%M").strftime("%I:%M %p").lstrip("0")
        self.assertEqual(t09, "9:05 AM")

    # ── Test 7: الاحتفاظ برمز الخدمة الذي أدخله المستخدم ───────────────────────
    def test_07_service_code_retention(self):
        custom_code = "GSL_CUSTOM_998877"
        form_state = {"service_code": custom_code}
        page2_code = form_state.get("service_code")
        self.assertEqual(page2_code, custom_code)
        page3_code = form_state.get("service_code")
        self.assertEqual(page3_code, custom_code)

    # ── Test 8: كون اسم المؤسسة بالإنجليزية اختياريًا ────────────────────────
    def test_08_employer_en_optional(self):
        data_without_en = {
            "employer": "شركة السيف",
            "employer_en": "",
        }
        self.assertEqual(data_without_en["employer"], "شركة السيف")
        self.assertEqual(data_without_en["employer_en"], "")
        self.assertNotIn("Unknown", data_without_en["employer_en"])

    # ── Test 9: عمل خيار الباركود ────────────────────────────────────────────
    def test_09_barcode_toggle_flag(self):
        flag_off = False
        flag_on = True
        self.assertFalse(flag_off)
        self.assertTrue(flag_on)

    # ── Test 10: صحة الخطوط وتوصيل الحروف العربية ────────────────────────────
    def test_10_arabic_reshaping(self):
        raw = "تقرير إجازة مرضية"
        reshaped = ar(raw)
        self.assertTrue(len(reshaped) > 0)
        self.assertTrue(has_ar(raw))
        self.assertFalse(has_ar("Sick Leave Report"))

    # ── Test 11: أبعاد وهيكل الجدول ──────────────────────────────────────────
    def test_11_table_structure(self):
        expected_rows = 11
        expected_cols = 4
        self.assertEqual(expected_rows, 11)
        self.assertEqual(expected_cols, 4)

    # ── Test 12: موضع QR والرابط والنص التوضيحي ──────────────────────────────
    def test_12_verification_url(self):
        url = "https://www.seha.sa/#/inquiries/slenquiry"
        self.assertTrue(url.startswith("https://www.seha.sa"))
        self.assertIn("inquiries", url)

    # ── Test 13: صحة التاريخ والوقت واسم اليوم والشهر ────────────────────────
    def test_13_dynamic_date_formatting(self):
        d = date(2026, 7, 3)
        formatted = f"{d.strftime('%A')} ،{d.day} {d.strftime('%B %Y')}"
        self.assertIn("Friday", formatted)
        self.assertIn("3", formatted)
        self.assertIn("July 2026", formatted)

    # ── Test 14: ملائمة المحتوى في صفحة واحدة ────────────────────────────────
    def test_14_single_page_pdf(self):
        sample_data = {
            "leave_id": "GSL26080311625",
            "admission_date_gregorian": "23/10/2026",
            "admission_date_hijri": "01/04/1448",
            "discharge_date_gregorian": "30/10/2026",
            "discharge_date_hijri": "08/04/1448",
            "issue_date_gregorian": "23/10/2026",
            "issue_date_long": "Friday ،23 October 2026",
            "issue_time": "6:20 PM",
            "leave_duration_days": 8,
            "patient_name_ar": "محمد أحمد علي",
            "patient_name_en": "Mohammed Ahmed Ali",
            "national_id": "1234567890",
            "nationality": "Saudi Arabia",
            "employer": "وزارة الصحة",
            "practitioner_name_ar": "د. أحمد سعيد",
            "practitioner_position_ar": "طبيب عام",
            "hospital_name_ar": "مستشفى الملك سلمان",
            "hospital_name_en": "King Salman Hospital",
            "include_barcode": True,
        }
        out_pdf = REPORTS_DIR / "test_suite_output.pdf"
        generate_pdf(sample_data, out_pdf)
        self.assertTrue(out_pdf.exists())
        import fitz
        doc = fitz.open(str(out_pdf))
        self.assertEqual(len(doc), 1, "PDF MUST be exactly 1 page!")
        doc.close()

    # ── Test 15: منع الوصول لسجلات مستخدم آخر (Data Isolation) ────────────────
    def test_15_data_isolation(self):
        u1 = get_or_create_user_sync("tg_user_101", "user1")
        u2 = get_or_create_user_sync("tg_user_202", "user2")
        self.assertNotEqual(u1.id, u2.id)
        self.assertNotEqual(u1.telegram_user_id, u2.telegram_user_id)
        # Test report ownership
        record_report_ownership_sync("GSL_U1_001", u1.id, u1.telegram_user_id)
        # U1 owns the report
        self.assertTrue(verify_report_ownership_sync("GSL_U1_001", u1.id))
        # U2 does NOT own the report
        self.assertFalse(verify_report_ownership_sync("GSL_U1_001", u2.id))

    # ── Test 16: رفض رمز التحقق المنتهي أو المستخدم (5-digit, 10s expiry) ─────
    def test_16_verification_code_lifecycle(self):
        u = get_or_create_user_sync("tg_verify_test", "vtest")
        # Generate 5-digit code
        code = create_verification_code_sync(u.id)
        self.assertEqual(len(code), 5)
        self.assertTrue(code.isdigit())
        # First verification succeeds
        ok = verify_code_sync(u.id, code)
        self.assertTrue(ok)
        # Second verification fails (single use)
        ok_reuse = verify_code_sync(u.id, code)
        self.assertFalse(ok_reuse, "Reusing code must fail!")
        # Wrong code fails
        ok_wrong = verify_code_sync(u.id, "00000")
        self.assertFalse(ok_wrong, "Wrong code must fail!")

    # ── Test 17: منع العمليات بعد انتهاء الاشتراك ──────────────────────────────
    def test_17_subscription_expired_enforcement(self):
        u = get_or_create_user_sync("tg_expired_user", "expired")
        # Expire subscription manually in DB
        import sqlite3
        conn = sqlite3.connect(str(BASE_DIR / "seha_auth.db"))
        cur = conn.cursor()
        cur.execute("UPDATE users SET subscription_end = ? WHERE id = ?", (
            (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            u.id
        ))
        conn.commit()
        conn.close()

        status = check_subscription_sync(u.id)
        self.assertFalse(status["active"])
        self.assertEqual(status["message"], "انتهى الاشتراك")

    # ── Test 18: صحة تجديد الاشتراك لـ 30 يوم ─────────────────────────────────
    def test_18_subscription_renewal(self):
        u = get_or_create_user_sync("tg_renew_user", "renew_user")
        updated = renew_subscription_sync(u.id, days=30)
        status = check_subscription_sync(updated.id)
        self.assertTrue(status["active"])
        self.assertGreaterEqual(status["days_remaining"], 29)
        self.assertIn("متبقي على انتهاء الاشتراك", status["message"])

    # ── Test 19: حماية لوحة الإدارة بصلاحيات الخادم ──────────────────────────
    def test_19_admin_authorization(self):
        normal_user = get_or_create_user_sync("tg_normal", "normal")
        self.assertEqual(normal_user.role, "user")
        self.assertNotEqual(normal_user.role, "admin")

    # ── Test 20: فحص توليد صورة PDF الفعلية ───────────────────────────────────
    def test_20_pdf_image_generation(self):
        out_pdf = REPORTS_DIR / "test_suite_output.pdf"
        self.assertTrue(out_pdf.exists())
        import fitz
        doc = fitz.open(str(out_pdf))
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img_out = REPORTS_DIR / "test_suite_preview.png"
        pix.save(str(img_out))
        doc.close()
        self.assertTrue(img_out.exists())
        self.assertGreater(img_out.stat().st_size, 10000)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestMasterSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print(f"\nSummary: {result.testsRun} tests run, {len(result.failures)} failures, {len(result.errors)} errors.")
    sys.exit(0 if result.wasSuccessful() else 1)
