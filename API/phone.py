import re


def normalize_ph_number(raw):
    """Convert common Philippine mobile formats to 63XXXXXXXXXX."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("639"):
        return digits
    if len(digits) == 11 and digits.startswith("09"):
        return "63" + digits[1:]
    if len(digits) == 10 and digits.startswith("9"):
        return "63" + digits
    raise ValueError("Invalid Philippine mobile number.")
