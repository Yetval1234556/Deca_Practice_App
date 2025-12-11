# DECA Practice Lab

Built for DECA practice. Drop any DECA exam PDF into `tests/` and get an instant, fully local drill UI: questions stay in order, answers and explanations stay hidden until you ask. No manual entry, no cloud calls, just your DECA tests plus fast feedback.

## Highlights

Highlights include a DECA-ready parser (1–100 numbered questions with A–E options, dense answer keys tolerated), instant scoring with timed mode, jump-anywhere navigation, light and dark themes with remembered preference, full summaries with explanations, missed-only review, and an all-local flow where answers are only fetched when you ask for them.

## Quick start

Install dependencies with Python 3.9+:
```bash
python3 -m pip install -r requirements.txt
```
Run the server:
```bash
python3 app.py
```
Open http://localhost:8080 and pick a test; answers stay server-side until you click Show correct answer.

## Adding DECA PDFs

Place PDF files inside `tests/` (for example `tests/marketing_exam.pdf`). Each PDF should have numbered questions (1–100) with multiple-choice options labeled A–D/E and an answer section near the end mapping numbers to answers with optional explanations directly under each answer. The parser is tolerant of spacing and punctuation such as `1. A`, `1)A`, or `1 - A`. Click Reload in the UI or refresh the page to pick up new PDFs; no server restart is required.

## How it works

The backend reads every PDF in `tests/`, extracts lines, finds the answer section, parses the answer key with regex, and pairs it to numbered questions, options, answers, and explanations. Dense answer lines such as `97.B 98.C 99.D` are split and explanations are captured until the next answer entry. Questions without matching answers or options are skipped; only items numbered 1–100 are kept and sorted. Core routes: `/api/tests` to list tests, `/api/tests/<id>/start_quiz` to begin a session (accepts `count`, `mode` of `regular` or `review_incorrect`, and optional `time_limit_seconds`), `/api/tests/<id>/check/<qid>` for correctness, and `/api/tests/<id>/answer/<qid>` for the correct option and explanation.

## Frontend features

The UI offers a test selection sidebar with a question-count picker, one-question-at-a-time flow with immediate feedback, timed practice with auto-submit when time expires, a timer that can be hidden without pausing, a dedicated Show correct answer control, a results summary with explanations, a review-incorrect-only mode, and the ability to restart or switch tests without restarting the server.

## Deploying and serving

Local usage: run `python3 app.py` (honors `HOST` and `PORT`, default 0.0.0.0:8080). Production-style usage: run `gunicorn app:app` and bind as needed. Health check: `GET /health` returns `{"status":"ok"}`. Environment toggles include `DEFAULT_RANDOM_ORDER` (true/false), `MAX_QUESTIONS_PER_RUN` (int, default 100), and `MAX_TIME_LIMIT_MINUTES` (int, default 180).

## Docker

Build the image:
```bash
docker build -t deca-practice .
```
Run it (maps port 8080):
```bash
docker run --rm -p 8080:8080 deca-practice
```
Mount your PDFs without rebuilding by adding `-v "$(pwd)/tests:/app/tests"`.

## Tests

Install test dependencies and run pytest:
```bash
python3 -m pip install -r requirements-dev.txt
pytest
```

## Tips for reliable parsing

Keep question numbers at the start of a line (for example `12) Question text` or `12. Question text`). Label options with leading letters (`A)`, `B.`, `C -`). Ensure the answer key uses clear number-to-letter pairs; any spacing or punctuation is fine (`1 A`, `1. A`, `1-A`). Explanations placed directly after the answer line are captured until the next answer entry. If a PDF cannot be parsed, check server logs for Skipping messages that describe why a file or question was skipped.

## Key backend functions (app.py)

`_lines_from_pdf(path)` extracts trimmed lines and normalizes spacing. `_find_answer_section_start(lines)` locates the likely start of the answer key. `_explode_answer_lines(lines)` splits dense keys. `_parse_answer_key(lines, start, raw_text)` builds the answer and explanation map within 1–100 bounds. `_parse_questions(lines, stop=None)` and `_parse_question_blocks(text)` recover numbered questions and options. `_attach_answers(test_id, questions, answers)` pairs questions to answers. `_parse_pdf_to_test(path)` orchestrates parsing into a test payload. `load_all_tests()` caches parsed tests and reloads on file changes.

## Credits

Icons: Phosphor Icons CDN. Fonts: Space Grotesk from Google Fonts. Charts: Chart.js. Confetti: canvas-confetti.
