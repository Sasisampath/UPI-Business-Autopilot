"""Rule-based parser that turns a customer's own words into PROPOSED commitments.
It only reads what is stated (amount + day [+ method]); nothing is saved until the merchant confirms."""
import re
from datetime import date, timedelta

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
             "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6,
             # Tamil (romanised)
             "thingal": 0, "sevvai": 1, "budhan": 2, "viyazhan": 3, "velli": 4, "sani": 5, "nyayiru": 6}
_RELATIVE = {"today": 0, "tomorrow": 1, "inniku": 0, "innaiku": 0, "indru": 0, "naalaiku": 1, "naalaikku": 1, "nalaiku": 1}
_AMOUNT = re.compile(r"(?:₹|rs\.?|inr|rupees?)\s*([\d,]+(?:\.\d{1,2})?)\s*(k\b)?|([\d,]+(?:\.\d{1,2})?)\s*(k\b)?\s*(?:rs\b|rupees?|/-|ரூ)?", re.I)
_DMY = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
_METHODS = (("upi", "upi"), ("gpay", "upi"), ("phonepe", "upi"), ("paytm", "upi"), ("online", "upi"),
            ("cash", "cash"), ("kaasu", "cash"), ("panam", "cash"))


def _amount_paise(text: str) -> int | None:
    for m in _AMOUNT.finditer(text):
        raw, k = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if not raw:
            continue
        value = raw.replace(",", "")
        rupees, _, frac = value.partition(".")
        paise = int(rupees) * 100 + int((frac + "00")[:2])
        if k:
            paise *= 1000
        if paise >= 10000 or m.group(1):  # ignore bare small numbers such as dates
            return paise
    return None


def _day(text: str, today: date) -> date | None:
    low = text.lower()
    for word, offset in _RELATIVE.items():
        if re.search(rf"\b{word}\b", low):
            return today + timedelta(days=offset)
    for word, wd in _WEEKDAYS.items():
        if re.search(rf"\b{word}\b", low):
            return today + timedelta(days=(wd - today.weekday()) % 7)  # same weekday => today; merchant can edit
    m = _DMY.search(low)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        year += 2000 if year < 100 else 0
        try:
            d = date(year, month, day)
            return d.replace(year=year + 1) if not m.group(3) and d < today else d
        except ValueError:
            return None
    return None


def _method(text: str) -> str | None:
    low = text.lower()
    for word, method in _METHODS:
        if re.search(rf"\b{word}\b", low):
            return method
    return None


def parse_commitments(text: str, today: date) -> list[dict]:
    """'₹3,000 on Friday, ₹2,000 on Monday' -> two proposals. Clauses lacking an amount or a day are skipped."""
    default_method = _method(text)
    proposals = []
    # Split on separators, but not on the comma inside a number such as 3,000.
    for clause in re.split(r"(?<!\d),|,(?!\d)|;|\band\b|\bthen\b|\n|\bmattum\b", text, flags=re.I):
        date_free = _DMY.sub(" ", clause)
        amount, day = _amount_paise(date_free), _day(clause, today)
        if amount and day:
            proposals.append({"amount_paise": amount, "promised_date": day.isoformat(),
                              "method": _method(clause) or default_method, "source_text": clause.strip()})
    return proposals
