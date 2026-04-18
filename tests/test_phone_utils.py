# ============================================================
# Tests for phone_utils.py — universal phone normalization
# Run: python -m pytest tests/test_phone_utils.py -v
# ============================================================
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fazle-system", "shared"))

from phone_utils import normalize_phone, phones_match


class TestNormalizePhone:
    """Test BD phone normalization per spec."""

    def test_full_international(self):
        assert normalize_phone("+8801958122300") == "01958122300"

    def test_international_no_plus(self):
        assert normalize_phone("8801958122300") == "01958122300"

    def test_local_format(self):
        assert normalize_phone("01958122300") == "01958122300"

    def test_ten_digit_without_zero(self):
        assert normalize_phone("1958122300") == "01958122300"

    def test_with_dashes(self):
        assert normalize_phone("01958-122-300") == "01958122300"

    def test_with_spaces(self):
        assert normalize_phone("01958 122 300") == "01958122300"

    def test_880_with_spaces(self):
        assert normalize_phone("880 1958 122300") == "01958122300"

    def test_plus_880_with_spaces(self):
        assert normalize_phone("+880 1958 122300") == "01958122300"

    def test_owner_phone(self):
        assert normalize_phone("+8801880446111") == "01880446111"

    def test_access_phone_1(self):
        assert normalize_phone("+8801848144841") == "01848144841"

    def test_access_phone_2(self):
        assert normalize_phone("+8801772274173") == "01772274173"

    def test_none_input(self):
        assert normalize_phone(None) is None

    def test_empty_string(self):
        assert normalize_phone("") is None

    def test_non_bd_number(self):
        assert normalize_phone("447878758751") is None

    def test_short_number(self):
        assert normalize_phone("12345") is None

    def test_numeric_input(self):
        assert normalize_phone(8801958122300) == "01958122300"

    def test_double_880(self):
        # Handle edge case of double country code
        assert normalize_phone("88088001958122300") == "01958122300"


class TestPhonesMatch:
    def test_same_number_different_format(self):
        assert phones_match("+8801958122300", "01958122300") is True

    def test_different_numbers(self):
        assert phones_match("+8801958122300", "+8801880446111") is False

    def test_non_bd_vs_bd(self):
        assert phones_match("+447878758751", "+8801958122300") is False
