import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian 10-digit mobile
LONG_NUMBER_RE = re.compile(r"\d{8,}")  # looks like a full ID number


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


def validate_guardian_form(form):
    """Account fields (phone required) plus the guardian application fields."""
    errors = validate_account_form(form, phone_required=True)
    organisation = (form.get("organisation") or "").strip()
    proof = (form.get("id_proof_note") or "").strip()
    reason = (form.get("reason") or "").strip()

    if len(organisation) < 2:
        errors.append("Enter your organisation, college or NGO name.")
    elif len(organisation) > 150:
        errors.append("Organisation name is too long (150 characters maximum).")

    if len(proof) < 4:
        errors.append("Describe your ID proof, for example: Aadhaar, last 4 digits 1234.")
    elif LONG_NUMBER_RE.search(proof):
        errors.append("Please do not enter a full ID number. Type the ID name and the last 4 digits only.")
    elif len(proof) > 255:
        errors.append("ID proof note is too long (255 characters maximum).")

    if len(reason) > 500:
        errors.append("Reason is too long (500 characters maximum).")
    if not form.get("agree"):
        errors.append("Please tick the box to confirm you understand this is a reviewed prototype.")
    return errors
