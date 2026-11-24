"""Run real bills through the real Gemini reader and score them against ground truth.

    cd services/api
    GEMINI_API_KEY=... python -m scripts.eval_extraction                 # the bundled synthetic bills
    GEMINI_API_KEY=... python -m scripts.eval_extraction path/to/folder  # your own bills + expected.json
    ... --json report.json                                               # also save the raw results

Without a key it exits with code 2 and says so; it never fabricates a result. A folder needs the
bill files plus an `expected.json` in the format of fixtures/bills/expected.json (amounts in rupees
as written). Files without an entry are still read and printed, just not scored.
"""
import json
import mimetypes
import sys
import time
from pathlib import Path

from adapters.extraction import ExtractionError, GeminiExtractionAdapter, clean_quantity, rupees_to_paise
from app import clock
from app.config import get_settings
from domain.money import format_inr, line_total_paise

DEFAULT = Path(__file__).resolve().parents[3] / "fixtures" / "bills"
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".pdf": "application/pdf"}


def score(name: str, draft: dict, want: dict) -> tuple[int, int, list[str]]:
    """Returns (correct, total, problems). A value the reader left empty AND flagged counts as a
    safe miss; a wrong value that is not flagged is the dangerous case and is called out."""
    ok = total = 0
    problems: list[str] = []
    flagged = set(draft["uncertain_fields"])

    def check(label: str, got, expected, path: str):
        nonlocal ok, total
        total += 1
        if got == expected:
            ok += 1
        elif got is None and any(f == path or f.startswith(path) or path.startswith(f) for f in flagged):
            problems.append(f"{label}: left empty and flagged (expected {expected!r}) - safe, needs typing")
        else:
            danger = "" if any(f == path or path.startswith(f) for f in flagged) else "  <-- WRONG AND NOT FLAGGED"
            problems.append(f"{label}: read {got!r}, expected {expected!r}{danger}")

    names = [n.lower() for n in (want.get("customer_name"), want.get("customer_name_en")) if n]
    total += 1
    if names and any(n in (draft["customer_name"] or "").lower() for n in names):
        ok += 1
    else:
        problems.append(f"customer: read {draft['customer_name']!r}, expected one of {names}")
    check("date", draft["invoice_date"], want.get("invoice_date"), "invoice_date")
    check("total", draft["total_paise"], rupees_to_paise(want.get("total")), "total_paise")
    if "tax" in want:
        check("tax", draft["tax_paise"], rupees_to_paise(want["tax"]), "tax_paise")
    items = draft["items"]
    if len(items) != len(want["items"]):
        problems.append(f"item count: read {len(items)}, expected {len(want['items'])}")
    for i, (_, qty, rate, amount) in enumerate(want["items"]):
        got = items[i] if i < len(items) else {"quantity": None, "unit_price_paise": None, "line_total_paise": None}
        check(f"line {i + 1} qty", got["quantity"], clean_quantity(qty), f"items[{i}].quantity")
        check(f"line {i + 1} rate", got["unit_price_paise"], rupees_to_paise(rate), f"items[{i}].unit_price_paise")
        check(f"line {i + 1} amount", got["line_total_paise"], rupees_to_paise(amount), f"items[{i}].line_total_paise")
    for path in want.get("must_flag", []):
        total += 1
        if any(f == path or f.startswith(path) or path.startswith(f) for f in flagged):
            ok += 1
        else:
            problems.append(f"should have flagged {path} as unclear but did not")
    return ok, total, problems


def backend_checks(draft: dict) -> list[str]:
    out = []
    for i, it in enumerate(draft["items"]):
        try:
            calc = line_total_paise(it["quantity"], it["unit_price_paise"]) if it["unit_price_paise"] is not None else None
        except ValueError:
            calc = None
        if calc is not None and it["line_total_paise"] is not None and calc != it["line_total_paise"]:
            out.append(f"backend caught: line {i + 1} says {format_inr(it['line_total_paise'])} but qty x rate = {format_inr(calc)}")
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folder = Path(args[0]) if args else DEFAULT
    settings = get_settings()
    if not settings.gemini_api_key:
        print("NOT RUN: GEMINI_API_KEY is not set. No bills were read and there are no results to report.")
        return 2
    expected = json.loads((folder / "expected.json").read_text()) if (folder / "expected.json").exists() else {}
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in TYPES)
    adapter = GeminiExtractionAdapter(settings)
    results, good, total = [], 0, 0
    print(f"Model: {settings.gemini_model}   Bills: {len(files)}   Folder: {folder}\n")
    for path in files:
        want = expected.get(path.name, {})
        started = time.time()
        entry: dict = {"file": path.name, "kind": want.get("kind")}
        try:
            draft = adapter.extract(path.read_bytes(), TYPES[path.suffix.lower()], clock.today_ist().isoformat())
            entry.update(outcome="read", draft=draft)
        except ExtractionError as exc:
            entry.update(outcome="failed", error_code=exc.code, error=exc.message)
        entry["seconds"] = round(time.time() - started, 1)
        print(f"== {path.name}  ({want.get('kind', 'no ground truth')})  {entry['seconds']}s")
        if entry["outcome"] == "failed":
            expected_error = want.get("expect_error")
            verdict = "as expected" if expected_error == entry["error_code"] else ("UNEXPECTED FAILURE" if not expected_error else f"expected {expected_error}")
            print(f"   not read: {entry['error_code']} ({verdict}) - {entry['error']}")
            if expected_error:
                total += 1
                good += expected_error == entry["error_code"]
        else:
            d = entry["draft"]
            print(f"   customer: {d['customer_name']} | date: {d['invoice_date']} | total: {format_inr(d['total_paise']) if d['total_paise'] is not None else None} | languages: {d['source_language']}")
            for i, it in enumerate(d["items"]):
                print(f"   {i + 1}. {it['description']} | qty {it['quantity']} | rate {it['unit_price_paise']} | amount {it['line_total_paise']}  (paise)")
            print(f"   flagged unclear: {d['uncertain_fields']}")
            if d.get("reader_notes"):
                print(f"   reader note: {d['reader_notes']}")
            for line in backend_checks(d):
                print("   " + line)
            if want.get("expect_error"):
                total += 1
                print(f"   PROBLEM: expected this file to be rejected ({want['expect_error']}) but it was read")
            elif want.get("items"):
                ok, n, problems = score(path.name, d, want)
                good, total = good + ok, total + n
                entry.update(correct=ok, checked=n, problems=problems)
                print(f"   score: {ok}/{n} values correct")
                for p in problems:
                    print("   - " + p)
        results.append(entry)
        print()
    if total:
        print(f"OVERALL: {good}/{total} checked values correct ({round(100 * good / total)}%) across {len(files)} files")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
