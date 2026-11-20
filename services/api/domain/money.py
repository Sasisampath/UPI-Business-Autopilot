"""Integer-paise money helpers. No floats anywhere near a balance."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def line_total_paise(quantity: str, unit_price_paise: int) -> int:
    """quantity (decimal string) x unit price, rounded half-up to the paisa."""
    qty = parse_quantity(quantity)
    return int((qty * Decimal(unit_price_paise)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_quantity(quantity) -> Decimal:
    try:
        qty = Decimal(str(quantity).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"invalid quantity: {quantity!r}") from exc
    if not qty.is_finite() or qty <= 0:
        raise ValueError(f"quantity must be positive: {quantity!r}")
    return qty


def format_inr(paise: int) -> str:
    """Indian digit grouping: 2000000 paise -> '₹20,000', 12345678 paise -> '₹1,23,456.78'."""
    sign = "-" if paise < 0 else ""
    rupees, rem = divmod(abs(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{sign}₹{digits}" + (f".{rem:02d}" if rem else "")
