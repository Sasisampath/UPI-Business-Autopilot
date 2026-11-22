# Gemini bill reading

## Status
- **Built and unit-tested; not yet run against Google.** No `GEMINI_API_KEY` was available where
  this was built, and that sandbox could not reach `generativelanguage.googleapis.com`. No real
  bill has been read by Gemini yet, so there are **no accuracy results**.
- What was verified without a key: the request is built with the installed `google-genai` SDK
  (image/PDF part, typed schema, timeout); amounts are converted in code; every failure type is
  reported as a failure; the simulated sample is used only when asked for or when no key exists.
  With a deliberately invalid key the real SDK call was made end to end and the app showed
  "The bill was not read" with no draft.

## Turn it on
```bash
cd services/api
pip install -r requirements-integrations.txt
export GEMINI_API_KEY=...            # server-side only; never sent to the browser
export GEMINI_MODEL=gemini-2.5-flash # confirm this model id is current for your key
```
The key is read from the server environment only. It is never returned by any API, written to
logs by this code, or exposed to the web app.

## How a read works
1. The uploaded file's own bytes (JPEG, PNG, WebP or PDF, up to 10 MB) go to Gemini with a prompt
   for handwritten/printed Indian bills in English and Tamil.
2. Gemini returns a transcription: buyer, items (description, quantity, rate, amount), subtotal,
   tax, total, the paths it found unclear, languages, and an optional note. Amounts come back as
   **text exactly as written**.
3. Code converts amounts to integer paise. Anything that is not plainly an amount (e.g. `2oo`) is
   emptied and flagged, never guessed. Missing year in a date, missing tax, smudged values: flagged.
4. Code re-adds every line and the total. Differences from what the bill says are shown as
   "Fix" items. The merchant edits, ticks the acknowledgement and approves. Only then is there an invoice.

## When a read fails
The draft is left empty, marked "The bill was not read", with a plain reason (key rejected, limit
reached, timeout, model not found, not a bill, nothing readable, Gemini unavailable). Options on
screen: **Try reading again**, **Use the simulated sample instead** (explicit, labelled), or type
the bill in. Timeouts and provider outages are retried once automatically. A failed read is never
replaced by sample data on its own.

`GEMINI_DAILY_LIMIT` (default 200 per merchant per day) caps real reads so a shared demo cannot
drain the quota.

## Measure accuracy on real bills
```bash
cd services/api
GEMINI_API_KEY=... python -m scripts.eval_extraction                       # six bundled bills
GEMINI_API_KEY=... python -m scripts.eval_extraction /path/to/your/bills   # your photos + expected.json
```
It prints, per bill, what was read, what was flagged, what the backend arithmetic caught, a score
against ground truth, and calls out any value that is **wrong and not flagged** (the dangerous
case). Without a key it prints "NOT RUN" and exits; it never invents results.

The bundled bills in `fixtures/bills/` are **synthetic** (rendered pages, not photos of real
handwriting): English handwriting-style with a deliberate arithmetic error, Tamil-only, a printed
GST invoice PDF, a tilted/blurred/dim mixed Tamil-English bill, a smudged bill with the total cut
off, and a non-bill poster. They test the pipeline. For a true accuracy figure, add at least five
photos of real bills with an `expected.json` (format: `fixtures/bills/expected.json`).
