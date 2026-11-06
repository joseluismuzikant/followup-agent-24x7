"""Phone numbers: stored as E.164, shown the Argentine way. Argentine mobiles are kept with
the 9 everywhere inside (leads, wa_ids, threads); only the Cloud API's `to` drops it."""

import phonenumbers

DEFAULT_REGION = "AR"


def to_e164(number: str, region: str = DEFAULT_REGION) -> str | None:
    """ "+5491155550188" from any common format; None when it is not a valid number.

    Argentine mobiles: the international form needs the 9 after +54 and drops the 15 of the
    local form ("011 15 5555-0188", "11 5555 0188" and "+54 9 11 5555 0188" are the same).
    """
    text = number.strip()
    if not text:
        return None
    digits = "".join(char for char in text if char.isdigit())
    # wa_ids arrive without "+": "5491155550188".
    if not text.startswith("+") and digits.startswith("54") and len(digits) >= 12:
        text = "+" + digits
    # "15 5555-0188" without an area code is a Buenos Aires mobile.
    elif region == "AR" and not text.startswith("+") and len(digits) == 10 and digits[:2] == "15":
        text = "11" + digits[2:]
    try:
        parsed = phonenumbers.parse(text, region)
    except phonenumbers.NumberParseException:
        return None
    if parsed.country_code == 54:
        parsed = _argentine_mobile(parsed)
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def canonical_wa_id(wa_id: str) -> str:
    """An inbound wa_id in our form: "541151060793" (an Argentine mobile without the 9, as
    Meta may send it) becomes "5491151060793", so both reach the same thread and lead. Every
    other wa_id is kept as Meta sent it."""
    if len(wa_id) == 12 and wa_id.startswith("54") and not wa_id.startswith("549"):
        e164 = to_e164(wa_id)
        if e164 is not None and e164.startswith("+549"):
            return e164[1:]
    return wa_id


def to_cloud_api_recipient(e164: str) -> str:
    """The Cloud API's `to` (digits only). Argentine mobiles go without the 9: Meta answers
    "+549" + 10 digits with error 131030 (not in the allowed list) and expects "54" + the 10
    digits. Every other number is unchanged."""
    digits = e164.lstrip("+")
    if digits.startswith("549") and len(digits) == 13 and digits.isdigit():
        return "54" + digits[3:]
    return digits


def _argentine_mobile(parsed: phonenumbers.PhoneNumber) -> phonenumbers.PhoneNumber:
    national = str(parsed.national_number)
    if national.startswith("9") and len(national) == 11:
        return parsed  # already +54 9 ...
    if len(national) == 10:
        # An area code + subscriber without the 9: mobiles are written with it.
        candidate = phonenumbers.PhoneNumber(country_code=54, national_number=int("9" + national))
        if phonenumbers.number_type(candidate) == phonenumbers.PhoneNumberType.MOBILE:
            return candidate
    return parsed


def display(e164: str) -> str:
    """ "+54 9 11 5555-0188" for Buenos Aires mobiles; the international format otherwise."""
    if e164.startswith("+54911") and len(e164) == 14:
        local = e164[6:]
        return f"+54 9 11 {local[:4]}-{local[4:]}"
    try:
        parsed = phonenumbers.parse(e164, None)
    except phonenumbers.NumberParseException:
        return e164
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
