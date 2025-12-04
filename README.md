# DECA Practice Lab

**Built for DECA practice.** Drop any DECA exam PDF into `tests/` and get an instant, fully local drill UI—questions stay in order, answers and explanations stay hidden until you ask. No manual entry, no cloud calls, just your DECA tests plus fast feedback.

## Highlights
- **DECA-ready parser:** Handles 1–100 numbered questions with A–E options and dense answer keys.
- **Instant scoring:** One-question flow with correct/incorrect feedback and optional timed mode.
- **Jump anywhere:** Tap numbered boxes (1–100) to answer questions in any order.
- **Light/dark themes:** Flip the appearance instantly from the Settings page; preference is remembered.
- **Full summaries:** Score, accuracy, per-question timing, and explanations from the answer key.
- **Missed-only review:** Replay only what you got wrong to lock in weak spots.
- **All local:** PDFs never leave your machine; answers are only fetched when you click **Show correct answer**.

## Quick start
1. From the project root, install dependencies (Python 3.9+):
   ```bash
   python3 -m pip install -r requirements.txt
   ```
2. Run the server:
   ```bash
   python3 app.py
   ```
3. Open http://localhost:8080 and pick a test. Answers are never sent to the page source until you click **Show correct answer** (API fetch).

## Adding DECA PDFs
1. Place PDF files inside `tests/` (e.g., `tests/marketing_exam.pdf`).
2. Each PDF should have:
   - Numbered questions (1–100) with multiple-choice options labeled A–D/E.
   - An answer section near the end mapping numbers to answers and (optionally) explanations directly under each answer. The parser is tolerant of spacing/punctuation like `1. A`, `1)A`, or `1 - A`.
3. Click **Reload** in the UI or refresh the page to pick up newly added PDFs. No restart needed.

## How it works
- The backend reads every PDF in `tests/`, extracts lines, finds the answer section (line containing “answer” or the final third of the file), parses the answer key with regex, and pairs it to numbered questions, options, answers, and explanations. Dense answer lines such as `97.B 98.C 99.D` are split and explanations are captured until the next answer entry for stability near the end of PDFs.
- Questions without matching answers or options are skipped to avoid broken practice items. Only questions numbered 1–100 are kept and sorted to preserve DECA order.
- `/api/tests` lists available tests.
- `/api/tests/<id>/start_quiz` begins a session (accepts `count`, `mode` of `regular` or `review_incorrect`, and optional `time_limit_seconds`); `/api/tests/<id>/questions?count=N` remains for simple retrieval without mode metadata.
- `/api/tests/<id>/results` stores missed questions for the last session; `/api/tests/<id>/review_missed` serves just the incorrect set.
- `/api/tests/<id>/check/<question_id>` returns only whether a selected option index is correct.
- `/api/tests/<id>/answer/<question_id>` returns the correct option and explanation when you choose to reveal or when the summary loads missed questions.

## Frontend features
- Test selection sidebar with question-count picker (10, 25, 50, 100, or all), numeric order, and progress bar.
- One-question-at-a-time flow with immediate correct/incorrect feedback.
- Timed practice mode: set a countdown before starting; the timer auto-submits/grades when it hits zero.
- Timer tracking total session time (and per-question time shown in summary) with a toggle to hide/show the clock without pausing or resetting progress.
- Dedicated **Show correct answer** button that fetches the answer and explanation on demand.
- Results summary with score, missed questions, and explanations from the answer key; optional “Show explanations for all.”
- “Review incorrect only” mode to replay just the questions you missed in the previous session.
- Restart current test or pick another without restarting the server.

## Deploying/serving
- Local: `python3 app.py` (honors `HOST`/`PORT` env vars; default 0.0.0.0:8080).
- Production-style: `gunicorn app:app` (add `--bind 0.0.0.0:8080` as needed).
- Health check: `GET /health` returns `{"status":"ok"}` for container readiness.
- Environment toggles:
  - `DEFAULT_RANDOM_ORDER` (`true`/`false`): shuffle questions by default unless the user overrides in Settings.
  - `MAX_QUESTIONS_PER_RUN` (int, default 100): clamp how many questions can be requested.
  - `MAX_TIME_LIMIT_MINUTES` (int, default 180): maximum allowed time limit for a session.

## Docker
Build and run with Docker:
1. Build the image:
   ```bash
   docker build -t deca-practice .
   ```
2. Run it (maps port 8080):
   ```bash
   docker run --rm -p 8080:8080 deca-practice
   ```
   Use `-v "$(pwd)/tests:/app/tests"` to mount your PDFs without rebuilding.

## Tests
Install test dependencies and run pytest:
```bash
python3 -m pip install -r requirements-dev.txt
pytest
```

## Tips for reliable parsing
- Keep question numbers at the start of a line like `12) Question text` or `12. Question text`.
- Label options with leading letters: `A)`, `B.`, `C -`, etc. Multi-line option text is appended to the previous option.
- Ensure the answer key uses clear number-to-letter pairs; any spacing or punctuation is fine (`1 A`, `1. A`, `1-A`). Explanations placed directly after the answer line are captured until the next answer entry.
- If a PDF cannot be parsed, check the server logs for “Skipping …” messages that describe why a file or question was skipped.

## Key backend functions (app.py)
- `_lines_from_pdf(path)`: extracts trimmed lines from each page, normalizing double-spaces to keep tokens in order.
- `_find_answer_section_start(lines)`: locates the likely start of the answer key (explicit “answer” line or final third of the PDF).
- `_explode_answer_lines(lines)`: splits dense answer key lines like `97.B 98.C` into separate chunks for stable parsing.
- `_parse_answer_key(lines, start, raw_text)`: builds answer/explanation map with fallbacks (expanded lines and full-text scan) while bounding to questions 1–100.
- `_parse_questions(lines, stop=None)` and `_parse_question_blocks(text)`: recover numbered questions and options (inline or multi-line), preferring content before the answer section.
- `_attach_answers(test_id, questions, answers)`: pairs questions to answers by letter/index, pruning items with missing options or mismatched keys.
- `_parse_pdf_to_test(path)`: orchestrates parsing a PDF into a test payload, normalizing ids/names and enforcing order 1–100.
- `load_all_tests()`: caches parsed tests from `tests/` and reloads on file mtime change.
- Routes: `/api/tests`, `/api/tests/<id>/questions`, `/api/tests/<id>/check/<qid>`, `/api/tests/<id>/answer/<qid>` power the UI.
