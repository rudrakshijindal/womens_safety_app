import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian 10-digit mobile


def validate_phone(phone, required=False):
    phone = (phone or "").strip()
    if not phone:
        return "Phone number is required." if required else None
    if not PHONE_RE.match(phone):
        return "Enter a valid 10-digit Indian mobile number (starts with 6-9)."
    return None


def validate_account_form(form, phone_required=False):
    """Validate name / email / password / phone. Returns a list of error strings."""
    errors = []
    name = (form.get("name") or "").strip()
    email = (form.get("email") or "").strip()
    password = form.get("password") or ""
    confirm = form.get("confirm_password") or ""

    if len(name) < 2:
        errors.append("Please enter your full name (at least 2 characters).")
    if not EMAIL_RE.match(email):
        errors.append("Enter a valid email address, e.g. name@example.com.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    elif password != confirm:
        errors.append("Password and confirmation do not match.")
    phone_error = validate_phone(form.get("phone"), required=phone_required)
    if phone_error:
        errors.append(phone_error)
    return errors
