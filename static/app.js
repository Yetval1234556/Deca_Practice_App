const state = {
  tests: [],
  activeTest: null,
  questions: [],
  currentIndex: 0,
  score: 0,
  answers: {}, // { [questionId]: { choice, correct, revealed, correctIndex, correctLetter, explanation } }
  selectedCount: 0,
  totalAvailable: 0,
  showAllExplanations: false,
  sessionStart: null,
  questionStart: null,
  timerInterval: null,
  totalElapsedMs: 0,
  perQuestionMs: {}, // questionId -> ms
};

const testListEl = document.getElementById("test-list");
const reloadBtn = document.getElementById("reload-tests");
const questionArea = document.getElementById("question-area");
const summaryArea = document.getElementById("summary-area");
const progressFill = document.getElementById("progress-fill");
const activeTestName = document.getElementById("active-test-name");
const scoreDisplay = document.getElementById("score-display");
const restartBtn = document.getElementById("restart-test");
const backToTestsBtn = document.getElementById("back-to-tests");
const showAllExplanationsBtn = document.getElementById("show-all-explanations");
const timerDisplay = document.getElementById("timer-display");

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, (tag) => {
    const chars = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return chars[tag] || tag;
  });
}

function updateScore() {
  const total = state.selectedCount || state.questions.length || 0;
  scoreDisplay.textContent = `${state.score} / ${total}`;
}

function updateProgress() {
  if (!state.questions.length) {
    progressFill.style.width = "0%";
    return;
  }
  const percent = Math.min(100, (state.currentIndex / state.questions.length) * 100);
  progressFill.style.width = `${percent}%`;
}

function formatMs(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function updateTimerDisplay() {
  if (!state.sessionStart) {
    timerDisplay.textContent = "00:00";
    return;
  }
  const elapsed = Date.now() - state.sessionStart;
  state.totalElapsedMs = elapsed;
  timerDisplay.textContent = formatMs(elapsed);
}

function startSessionTimer() {
  clearInterval(state.timerInterval);
  state.sessionStart = Date.now();
  state.totalElapsedMs = 0;
  updateTimerDisplay();
  state.timerInterval = setInterval(updateTimerDisplay, 1000);
}

function stopSessionTimer() {
  if (state.sessionStart) {
    state.totalElapsedMs = Date.now() - state.sessionStart;
  }
  clearInterval(state.timerInterval);
  state.timerInterval = null;
}

function startQuestionTimer() {
  state.questionStart = Date.now();
}

function recordCurrentQuestionTime() {
  if (!state.questionStart || !state.questions[state.currentIndex]) return;
  const qid = state.questions[state.currentIndex].id;
  const elapsed = Date.now() - state.questionStart;
  state.perQuestionMs[qid] = (state.perQuestionMs[qid] || 0) + elapsed;
  state.questionStart = null;
}

async function ensureAnswerDetails(question) {
  const existing = state.answers[question.id] || {};
  if (existing.correctIndex !== undefined && existing.explanation !== undefined) {
    return existing;
  }
  const res = await fetch(
    `/api/tests/${encodeURIComponent(state.activeTest.id)}/answer/${encodeURIComponent(question.id)}`
  );
  if (!res.ok) throw new Error("Unable to load answer details");
  const data = await res.json();
  const merged = {
    ...existing,
    correctIndex: data.correct_index,
    correctLetter: data.correct_letter,
    explanation: data.explanation,
  };
  state.answers[question.id] = merged;
  return merged;
}

async function fetchTests() {
  testListEl.innerHTML = `<p class="muted">Loading tests...</p>`;
  try {
    const res = await fetch("/api/tests");
    if (!res.ok) throw new Error("Failed to load tests");
    const data = await res.json();
    state.tests = data;
    renderTestList();
  } catch (err) {
    testListEl.innerHTML = `<p class="muted">Could not load tests. ${err.message}</p>`;
  }
}

function renderTestList() {
  testListEl.innerHTML = "";
  if (!state.tests.length) {
    testListEl.innerHTML = `<p class="muted">No tests found. Add DECA PDFs to <code>tests/</code> and reload.</p>`;
    return;
  }
  state.tests.forEach((test) => {
    const card = document.createElement("div");
    card.className = "test-card";
    const options = [
      { label: "All", value: 0 },
      { label: "10", value: 10 },
      { label: "25", value: 25 },
      { label: "50", value: 50 },
      { label: "100", value: 100 },
    ].filter((opt) => opt.value === 0 || opt.value <= test.question_count);
    card.innerHTML = `
      <div class="test-meta">
        <h4>${escapeHtml(test.name)}</h4>
        <p>${escapeHtml(test.description || "No description")}</p>
        <p class="muted">${test.question_count} question${test.question_count === 1 ? "" : "s"}</p>
      </div>
      <div class="test-actions">
        <label>
          <span class="muted small-label">Question count</span>
          <select class="count-select" data-test-id="${test.id}">
            ${options
              .map((opt) => `<option value="${opt.value}">${opt.value === 0 ? "All" : opt.label}</option>`)
              .join("")}
          </select>
        </label>
        <button class="primary" data-test-id="${test.id}">Start</button>
      </div>
    `;
    const startBtn = card.querySelector("button");
    const selectEl = card.querySelector(".count-select");
    startBtn.addEventListener("click", () => {
      const count = Number(selectEl.value);
      startTest(test.id, count);
    });
    testListEl.appendChild(card);
  });
}

async function startTest(testId, count = 0) {
  try {
    const query = count && count > 0 ? `?count=${count}` : "";
    const res = await fetch(`/api/tests/${encodeURIComponent(testId)}/questions${query}`);
    if (!res.ok) throw new Error("Unable to load test");
    const data = await res.json();
    state.activeTest = data.test;
    state.questions = data.questions;
    state.currentIndex = 0;
    state.score = 0;
    state.answers = {};
    state.selectedCount = data.selected_count || state.questions.length;
    state.totalAvailable = data.test?.total || state.questions.length;
    state.showAllExplanations = false;
    state.perQuestionMs = {};
    startSessionTimer();
    activeTestName.textContent = state.activeTest.name;
    questionArea.classList.remove("hidden");
    summaryArea.classList.add("hidden");
    renderQuestionCard();
    updateScore();
    updateProgress();
  } catch (err) {
    questionArea.innerHTML = `<div class="placeholder"><p class="muted">${err.message}</p></div>`;
  }
}

function questionDone(questionId) {
  const status = state.answers[questionId];
  return Boolean(status && (status.correct !== undefined || status.revealed));
}

function renderQuestionCard() {
  if (!state.activeTest || !state.questions.length) {
    questionArea.innerHTML = `<div class="placeholder"><p class="muted">Select a test to begin.</p></div>`;
    return;
  }

  startQuestionTimer();
  const question = state.questions[state.currentIndex];
  const status = state.answers[question.id];
  const answered = questionDone(question.id);
  const feedbackText = status
    ? status.correct
      ? "Correct!"
      : status.correct === false
        ? "Incorrect"
        : "Answer revealed"
    : "Pick an answer to get instant feedback.";

  const isLast = state.currentIndex === state.questions.length - 1;
  questionArea.innerHTML = `
    <div class="question-head">
      <div>
        <p class="eyebrow">Question ${state.currentIndex + 1} of ${state.questions.length}${question.number ? ` • #${question.number}` : ""}</p>
        <div class="question-text">${escapeHtml(question.question)}</div>
      </div>
      <div class="pill">
        <span class="dot"></span>
        <span>${escapeHtml(state.activeTest.name)} · ${state.selectedCount || state.questions.length}/${state.totalAvailable || state.questions.length}</span>
      </div>
    </div>
    <div class="options">
      ${question.options
        .map(
          (option, idx) =>
            `<button class="option-btn" data-idx="${idx}" ${status && status.choice !== undefined ? "disabled" : ""}>
              <strong>${String.fromCharCode(65 + idx)}.</strong> ${escapeHtml(option)}
            </button>`
        )
        .join("")}
    </div>
    <div id="feedback" class="feedback ${status ? (status.correct ? "correct" : status.correct === false ? "incorrect" : "") : ""}">
      ${feedbackText}
    </div>
    <div id="explanation" class="explanation ${status && status.revealed ? "" : "hidden"}"></div>
    <div class="actions">
      <button id="show-answer" class="secondary">Show correct answer</button>
      <button id="next-question" class="primary" ${answered ? "" : "disabled"}>${isLast ? "Finish" : "Next question"}</button>
    </div>
  `;

  const optionButtons = questionArea.querySelectorAll(".option-btn");
  optionButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const choice = Number(btn.dataset.idx);
      handleAnswer(question, choice);
    });
  });

  if (status) {
    optionButtons.forEach((btn) => {
      const idx = Number(btn.dataset.idx);
      if (status.choice === idx) {
        btn.classList.add(status.correct ? "correct" : "incorrect");
      }
      if (status.revealed && status.correctIndex === idx) {
        btn.classList.add("revealed", "correct");
      }
    });
    if (status.revealed) {
      renderExplanation(question, status);
    }
  }

  const showAnswerBtn = document.getElementById("show-answer");
  showAnswerBtn.addEventListener("click", () => revealAnswer(question));
  const nextBtn = document.getElementById("next-question");
  nextBtn.addEventListener("click", nextQuestion);
  nextBtn.disabled = !answered;
  updateScore();
  updateProgress();
}

async function handleAnswer(question, choiceIndex) {
  const existing = state.answers[question.id];
  if (existing && existing.choice !== undefined) return;
  recordCurrentQuestionTime();
  try {
    const res = await fetch(
      `/api/tests/${encodeURIComponent(state.activeTest.id)}/check/${encodeURIComponent(question.id)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice: choiceIndex }),
      }
    );
    if (!res.ok) throw new Error("Unable to submit answer");
    const data = await res.json();
    const wasCounted = Boolean(existing && existing.choice !== undefined);
    state.answers[question.id] = { ...(existing || {}), choice: choiceIndex, correct: data.correct };
    if (data.correct && !wasCounted) {
      state.score += 1;
    }
    renderQuestionCard();
  } catch (err) {
    const feedbackEl = document.getElementById("feedback");
    if (feedbackEl) {
      feedbackEl.textContent = err.message;
      feedbackEl.classList.remove("correct", "incorrect");
    }
  }
}

async function revealAnswer(question) {
  try {
    const details = await ensureAnswerDetails(question);
    state.answers[question.id] = { ...(state.answers[question.id] || {}), ...details, revealed: true };
    renderQuestionCard();
    document.getElementById("next-question").disabled = false;
  } catch (err) {
    const feedbackEl = document.getElementById("feedback");
    if (feedbackEl) {
      feedbackEl.textContent = err.message;
      feedbackEl.classList.remove("correct", "incorrect");
    }
  }
}

function renderExplanation(question, status) {
  const explanationEl = document.getElementById("explanation");
  if (!explanationEl) return;
  const correctLetter =
    status.correctIndex !== undefined ? String.fromCharCode(65 + status.correctIndex) : "?";
  const explanationText = status.explanation ? `<p>${escapeHtml(status.explanation)}</p>` : "";
  explanationEl.innerHTML = `
    <strong>Correct answer: ${correctLetter}</strong>
    ${explanationText}
  `;
  explanationEl.classList.remove("hidden");
}

async function nextQuestion() {
  recordCurrentQuestionTime();
  const currentQuestion = state.questions[state.currentIndex];
  if (!questionDone(currentQuestion.id)) return;
  if (state.currentIndex >= state.questions.length - 1) {
    await showSummary(state.showAllExplanations);
    stopSessionTimer();
    progressFill.style.width = "100%";
    return;
  }
  state.currentIndex += 1;
  renderQuestionCard();
}

async function showSummary(showAll = false) {
  recordCurrentQuestionTime();
  stopSessionTimer();
  questionArea.classList.add("hidden");
  summaryArea.classList.remove("hidden");
  const summaryScore = document.getElementById("summary-score");
  const summaryAccuracy = document.getElementById("summary-accuracy");
  const summaryList = document.getElementById("summary-list");
  const summaryTime = document.getElementById("summary-time");
  const total = state.questions.length;
  const accuracy = total ? Math.round((state.score / total) * 100) : 0;
  summaryScore.textContent = `You answered ${state.score} out of ${total} correctly.`;
  summaryAccuracy.textContent = `Accuracy: ${accuracy}%`;
  summaryTime.textContent = `Total time: ${formatMs(state.totalElapsedMs || 0)}`;
  summaryList.innerHTML = "";
  const targets = state.questions.filter((q) => {
    const status = state.answers[q.id];
    if (!status) return false;
    return showAll || status.correct === false;
  });
  try {
    await Promise.all(targets.map((q) => ensureAnswerDetails(q)));
  } catch (err) {
    console.warn("Could not load explanations", err);
  }
  state.showAllExplanations = showAll;

  state.questions.forEach((q, idx) => {
    const status = state.answers[q.id];
    let label = "Not answered";
    let tone = "";
    if (status) {
      if (status.correct === true) {
        label = "Correct";
        tone = "correct";
      } else if (status.correct === false) {
        label = "Incorrect";
        tone = "incorrect";
      } else if (status.revealed) {
        label = "Revealed";
      }
    }
    const item = document.createElement("div");
    item.className = "summary-item";
    const shouldShowExplanation = status && (status.correct === false || showAll);
    const timeTaken = state.perQuestionMs[q.id] || 0;
    const explanationHtml =
      shouldShowExplanation && status && status.explanation !== undefined
        ? `<div class="explanation"><strong>Correct (${status.correctLetter || "?"}):</strong> ${escapeHtml(
            status.explanation || "No explanation provided."
          )}<br><span class="muted">Time: ${formatMs(timeTaken)}</span></div>`
        : `<div class="explanation muted">Time: ${formatMs(timeTaken)}</div>`;
    item.innerHTML = `
      <strong>#${q.number || idx + 1}:</strong> ${escapeHtml(q.question)}<br>
      <span class="${tone}">${label}</span>
      ${explanationHtml}
    `;
    summaryList.appendChild(item);
  });
}

reloadBtn.addEventListener("click", fetchTests);
restartBtn.addEventListener("click", () => {
  if (state.activeTest) {
    startTest(state.activeTest.id);
  }
});
showAllExplanationsBtn.addEventListener("click", () => {
  if (!state.activeTest) return;
  showSummary(true);
});
backToTestsBtn.addEventListener("click", () => {
  state.activeTest = null;
  state.questions = [];
  state.currentIndex = 0;
  state.answers = {};
  state.score = 0;
  state.selectedCount = 0;
  state.totalAvailable = 0;
  state.showAllExplanations = false;
  state.perQuestionMs = {};
  stopSessionTimer();
  updateTimerDisplay();
  activeTestName.textContent = "None selected";
  questionArea.classList.remove("hidden");
  summaryArea.classList.add("hidden");
  renderQuestionCard();
  updateScore();
  updateProgress();
});

// Kick off
fetchTests();
