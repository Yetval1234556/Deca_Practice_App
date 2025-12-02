# DECA Practice Lab

Local Flask app that reads DECA test PDFs from `tests/`, extracts up to 100 numbered questions (kept in top-to-bottom order) plus answers and explanations, and serves a browser UI for one-at-a-time practice with instant feedback.

## Quick start
1. From the project root, install dependencies (Python 3.9+):
   ```bash
   python3 -m pip install -r requirements.txt
   ```
2. Run the server:
   ```bash
   python3 app.py
   ```
3. Open http://localhost:5000 and pick a test. Answers are never sent to the page source until you click **Show correct answer**.

## Adding DECA PDFs
1. Place PDF files inside `tests/` (e.g., `tests/marketing_exam.pdf`).
2. Each PDF should have:
   - Numbered questions (1–100) with multiple-choice options labeled A–D/E.
   - An answer section near the end mapping numbers to answers and (optionally) explanations directly under each answer. The parser is tolerant of spacing/punctuation like `1. A`, `1)A`, or `1 - A`.
3. Click **Reload** in the UI or refresh the page to pick up newly added PDFs. No restart needed.

## How it works
- The backend reads every PDF in `tests/`, extracts lines, finds the answer section (line containing “answer” or the final third of the file), parses the answer key with regex, and pairs it to numbered questions, options, answers, and explanations.
- Questions without matching answers or options are skipped to avoid broken practice items.
- `/api/tests` lists available tests.
- `/api/tests/<id>/questions?count=N` returns `N` questions (or all) in numeric order without answers.
- `/api/tests/<id>/check/<question_id>` returns only whether a selected option index is correct.
- `/api/tests/<id>/answer/<question_id>` returns the correct option and explanation when you choose to reveal or when the summary loads missed questions.

## Frontend features
- Test selection sidebar with question-count picker (10, 25, 50, 100, or all), numeric order, and progress bar.
- One-question-at-a-time flow with immediate correct/incorrect feedback.
- Timer tracking total session time (and per-question time shown in summary).
- Dedicated **Show correct answer** button that fetches the answer and explanation on demand.
- Results summary with score, missed questions, and explanations from the answer key; optional “Show explanations for all.”
- Restart current test or pick another without restarting the server.

## Deploying/serving
- Local: `python3 app.py` (honors `HOST`/`PORT` env vars).
- Production-style: `gunicorn app:app` (add `--bind 0.0.0.0:5000` as needed).

## Tips for reliable parsing
- Keep question numbers at the start of a line like `12) Question text` or `12. Question text`.
- Label options with leading letters: `A)`, `B.`, `C -`, etc. Multi-line option text is appended to the previous option.
- Ensure the answer key uses clear number-to-letter pairs; any spacing or punctuation is fine (`1 A`, `1. A`, `1-A`). Explanations placed directly after the answer line are captured until the next answer entry.
- If a PDF cannot be parsed, check the server logs for “Skipping …” messages that describe why a file or question was skipped.
