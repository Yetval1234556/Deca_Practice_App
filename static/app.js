const SESSION_KEY = "deca-active-session-v1";
const DEFAULT_TIME_LIMIT_MINUTES = 90;
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
  timerHidden: false,
  timeLimitMs: 0,
  timeRemainingMs: 0,
  mode: "regular",
  sessionComplete: false,
  endedByTimer: false,
  resultsPersisted: false,
  lastResults: [],
  lastRequestedCount: 0,
  lastTimeLimitMinutes: DEFAULT_TIME_LIMIT_MINUTES,
  questionGridCollapsed: true,
  randomOrderEnabled: false,
};

const RANDOM_KEY = "deca-random-order";

function parseDefaultRandom() {
  if (typeof window !== "undefined" && typeof window.DEFAULT_RANDOM_ORDER !== "undefined") {
    return String(window.DEFAULT_RANDOM_ORDER).toLowerCase() === "true";
  }
  return false;
}

const testListEl = document.getElementById("test-list");
const reloadBtn = document.getElementById("reload-tests");
const questionArea = document.getElementById("question-area");
const summaryArea = document.getElementById("summary-area");
const progressFill = document.getElementById("progress-fill");
const activeTestName = document.getElementById("active-test-name");
const scoreDisplay = document.getElementById("score-display");
const questionGridShell = document.getElementById("question-grid-shell");
const questionGrid = document.getElementById("question-grid");
const questionGridWrapper = document.getElementById("question-grid-wrapper");
const questionGridToggle = document.getElementById("toggle-grid");
const restartBtn = document.getElementById("restart-test");
const backToTestsBtn = document.getElementById("back-to-tests");
const showAllExplanationsBtn = document.getElementById("show-all-explanations");
const timerDisplay = document.getElementById("timer-display");
const toggleTimerBtn = document.getElementById("toggle-timer");
const reviewIncorrectBtn = document.getElementById("review-incorrect");
const summaryNote = document.getElementById("summary-note");
const sessionFooter = document.getElementById("session-footer");

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, (tag) => {
    const chars = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return chars[tag] || tag;
  });
}

function isRandomOrderEnabled() {
  const fallback = parseDefaultRandom();
  try {
    const stored = localStorage.getItem(RANDOM_KEY);
    if (stored === null) return fallback;
    return stored === "true";
  } catch (err) {
    return fallback;
  }
}

function shuffleQuestions(list) {
  const arr = [...list];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function persistSession() {
  if (typeof localStorage === "undefined") return;
  if (!state.activeTest || !state.questions.length) {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch (err) {
      // ignore storage errors
    }
    return;
  }
  const payload = {
    activeTest: state.activeTest,
    questions: state.questions,
    currentIndex: state.currentIndex,
    score: state.score,
    answers: state.answers,
    selectedCount: state.selectedCount,
    totalAvailable: state.totalAvailable,
    showAllExplanations: state.showAllExplanations,
    sessionStart: state.sessionStart,
    questionStart: state.questionStart,
    totalElapsedMs: state.totalElapsedMs,
    perQuestionMs: state.perQuestionMs,
    timerHidden: state.timerHidden,
    timeLimitMs: state.timeLimitMs,
    timeRemainingMs: state.timeRemainingMs,
    mode: state.mode,
    sessionComplete: state.sessionComplete,
    endedByTimer: state.endedByTimer,
    resultsPersisted: state.resultsPersisted,
    lastResults: state.lastResults,
    lastRequestedCount: state.lastRequestedCount,
    lastTimeLimitMinutes: state.lastTimeLimitMinutes,
    questionGridCollapsed: state.questionGridCollapsed,
    randomOrderEnabled: state.randomOrderEnabled,
  };
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(payload));
  } catch (err) {
    // ignore storage errors
  }
}

function clearPersistedSession() {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch (err) {
    // ignore
  }
}

function recomputeScoreFromAnswers() {
  state.score = state.questions.reduce((acc, q) => {
    const status = state.answers[q.id];
    if (status && status.correct === true) {
      return acc + 1;
    }
    return acc;
  }, 0);
}

function updateScore() {
  const total = state.selectedCount || state.questions.length || 0;
  scoreDisplay.textContent = `${state.score} / ${total}`;
}

function updateProgress() {
  const total = state.questions.length;
  if (!total) {
    progressFill.style.width = "0%";
    updateSessionMeta();
    return;
  }
  const answered = state.questions.reduce((acc, q) => (questionDone(q.id) ? acc + 1 : acc), 0);
  const percent = Math.min(100, (answered / total) * 100);
  progressFill.style.width = `${percent}%`;
  updateSessionMeta();
}

function updateSessionMeta() {
  if (!sessionFooter) return;
  if (!state.activeTest || !state.questions.length) {
    sessionFooter.classList.add("hidden");
    sessionFooter.innerHTML = `<span class="muted">No test in progress.</span>`;
    return;
  }
  const answered = state.questions.reduce((acc, q) => (questionDone(q.id) ? acc + 1 : acc), 0);
  const modeLabel = state.mode === "review_incorrect" ? "Review missed" : "Practice";
  const orderLabel = state.randomOrderEnabled ? "Random order" : "In order";
  const limitLabel = `${Math.round(state.timeLimitMs / 60000)}m limit`;
  const countLabel = `${state.selectedCount || state.questions.length}/${state.totalAvailable || state.questions.length}`;
  const statusLabel = state.endedByTimer ? "Timed out" : state.sessionComplete ? "Finished" : "In progress";
  sessionFooter.classList.remove("hidden");
  sessionFooter.innerHTML = `
    <div class="session-footer__title">${escapeHtml(state.activeTest.name)}</div>
    <div class="session-footer__meta">${countLabel} • ${modeLabel} • ${orderLabel} • ${limitLabel} • ${statusLabel}</div>
    <div class="session-footer__progress">Answered ${answered}/${state.questions.length}</div>
  `;
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
  if (toggleTimerBtn) {
    toggleTimerBtn.textContent = state.timerHidden ? "Show timer" : "Hide timer";
  }
  if (state.timerHidden) {
    timerDisplay.textContent = "— —";
    return;
  }
  if (!state.sessionStart) {
    if (state.sessionComplete && state.totalElapsedMs) {
      timerDisplay.textContent = formatMs(state.totalElapsedMs);
      return;
    }
    const base = formatMs(state.timeLimitMs || DEFAULT_TIME_LIMIT_MINUTES * 60 * 1000);
    timerDisplay.textContent = `${base} left`;
    return;
  }
  const elapsed = Math.max(0, Date.now() - state.sessionStart);
  state.totalElapsedMs = elapsed;
  if (state.timeLimitMs) {
    const remaining = Math.max(state.timeLimitMs - elapsed, 0);
    state.timeRemainingMs = remaining;
    timerDisplay.textContent = `${formatMs(remaining)} left`;
  } else {
    timerDisplay.textContent = formatMs(elapsed);
  }
}

function startSessionTimer(startedAt) {
  clearInterval(state.timerInterval);
  if (!state.timeLimitMs || state.timeLimitMs <= 0) {
    state.timeLimitMs = DEFAULT_TIME_LIMIT_MINUTES * 60 * 1000;
    state.timeRemainingMs = state.timeLimitMs;
  }
  const startStamp = startedAt || Date.now();
  state.sessionStart = startStamp;
  const elapsed = Math.max(0, Date.now() - startStamp);
  state.totalElapsedMs = elapsed;
  state.timeRemainingMs = state.timeLimitMs ? Math.max(state.timeLimitMs - elapsed, 0) : 0;
  updateTimerDisplay();
  if (state.timeLimitMs && state.timeRemainingMs <= 0) {
    handleTimeExpiry().catch((err) => console.error(err));
    persistSession();
    return;
  }
  state.timerInterval = setInterval(tickSessionTimer, 500);
  persistSession();
}

function stopSessionTimer() {
  if (state.sessionStart) {
    state.totalElapsedMs = Date.now() - state.sessionStart;
  }
  clearInterval(state.timerInterval);
  state.timerInterval = null;
  state.sessionStart = null;
  state.questionStart = null;
  persistSession();
}

function toggleTimer() {
  state.timerHidden = !state.timerHidden;
  toggleTimerBtn.textContent = state.timerHidden ? "Show timer" : "Hide timer";
  updateTimerDisplay();
  persistSession();
}

function tickSessionTimer() {
  if (!state.sessionStart) return;
  if (state.sessionComplete) {
    stopSessionTimer();
    return;
  }
  const elapsed = Date.now() - state.sessionStart;
  state.totalElapsedMs = elapsed;
  if (state.timeLimitMs) {
    state.timeRemainingMs = Math.max(state.timeLimitMs - elapsed, 0);
    if (state.timeRemainingMs <= 0 && !state.endedByTimer) {
      handleTimeExpiry().catch((err) => console.error(err));
      return;
    }
  }
  updateTimerDisplay();
}

async function handleTimeExpiry() {
  if (state.sessionComplete) return;
  state.endedByTimer = true;
  recordCurrentQuestionTime();
  state.timeRemainingMs = 0;
  updateTimerDisplay();
  await showSummary(state.showAllExplanations);
  updateSessionMeta();
  persistSession();
}

function startQuestionTimer() {
  if (!state.questionStart) {
    state.questionStart = Date.now();
    persistSession();
  }
}

function recordCurrentQuestionTime() {
  if (!state.questionStart || !state.questions[state.currentIndex]) return;
  const qid = state.questions[state.currentIndex].id;
  const elapsed = Date.now() - state.questionStart;
  state.perQuestionMs[qid] = (state.perQuestionMs[qid] || 0) + elapsed;
  state.questionStart = null;
  persistSession();
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

function restoreSessionFromStorage() {
  let raw;
  try {
    raw = localStorage.getItem(SESSION_KEY);
  } catch (err) {
    return false;
  }
  if (!raw) return false;
  let data = null;
  try {
    data = JSON.parse(raw);
  } catch (err) {
    return false;
  }
  if (!data || !data.activeTest || !Array.isArray(data.questions) || !data.questions.length) {
    return false;
  }
  state.activeTest = data.activeTest;
  state.questions = data.questions;
  state.currentIndex = Number.isFinite(data.currentIndex) ? data.currentIndex : 0;
  if (state.currentIndex < 0 || state.currentIndex >= state.questions.length) {
    state.currentIndex = 0;
  }
  state.answers = data.answers || {};
  state.selectedCount = data.selectedCount || data.questions.length;
  state.totalAvailable = data.totalAvailable || data.questions.length;
  state.showAllExplanations = Boolean(data.showAllExplanations);
  state.sessionStart = data.sessionStart || null;
  state.questionStart = data.questionStart || null;
  state.totalElapsedMs = data.totalElapsedMs || 0;
  state.perQuestionMs = data.perQuestionMs || {};
  state.timerHidden = Boolean(data.timerHidden);
  state.timeLimitMs = typeof data.timeLimitMs === "number" ? data.timeLimitMs : 0;
  state.timeRemainingMs = typeof data.timeRemainingMs === "number" ? data.timeRemainingMs : 0;
  state.mode = data.mode || "regular";
  state.sessionComplete = Boolean(data.sessionComplete);
  state.endedByTimer = Boolean(data.endedByTimer);
  state.resultsPersisted = Boolean(data.resultsPersisted);
  state.lastResults = data.lastResults || [];
  state.lastRequestedCount = typeof data.lastRequestedCount === "number" ? data.lastRequestedCount : 0;
  state.lastTimeLimitMinutes =
    typeof data.lastTimeLimitMinutes === "number" ? data.lastTimeLimitMinutes : DEFAULT_TIME_LIMIT_MINUTES;
  if (!state.timeLimitMs || state.timeLimitMs <= 0) {
    state.timeLimitMs = DEFAULT_TIME_LIMIT_MINUTES * 60 * 1000;
    state.timeRemainingMs = state.timeLimitMs;
  }
  if (!state.lastTimeLimitMinutes || state.lastTimeLimitMinutes <= 0) {
    state.lastTimeLimitMinutes = DEFAULT_TIME_LIMIT_MINUTES;
  }
  state.questionGridCollapsed = data.questionGridCollapsed !== undefined ? data.questionGridCollapsed : true;
  state.randomOrderEnabled =
    data.randomOrderEnabled !== undefined ? data.randomOrderEnabled : isRandomOrderEnabled();
  recomputeScoreFromAnswers();
  activeTestName.textContent = state.activeTest.name || "Active test";

  const elapsedNow = state.sessionStart ? Math.max(0, Date.now() - state.sessionStart) : 0;
  if (state.timeLimitMs && state.sessionStart) {
    state.timeRemainingMs = Math.max(state.timeLimitMs - elapsedNow, 0);
  }

  if (state.sessionComplete || state.endedByTimer) {
    showSummary(state.showAllExplanations).catch((err) => console.error(err));
  } else {
    questionArea.classList.remove("hidden");
    summaryArea.classList.add("hidden");
    startSessionTimer(state.sessionStart || Date.now());
    renderQuestionCard();
  }
  updateScore();
  updateProgress();
  renderQuestionGrid();
  updateSessionMeta();
  updateTimerDisplay();
  return true;
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

function normalizeTimeLimitInput(value) {
  const raw = (value || "").toString().trim();
  if (!raw) return { minutes: DEFAULT_TIME_LIMIT_MINUTES, display: `${DEFAULT_TIME_LIMIT_MINUTES}` };
  const parsed = parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return { minutes: DEFAULT_TIME_LIMIT_MINUTES, display: `${DEFAULT_TIME_LIMIT_MINUTES}` };
  }
  return { minutes: parsed, display: `${parsed}` };
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
        <label>
          <span class="muted small-label">Time limit (minutes)</span>
          <div class="time-input-row">
            <input
              class="time-select"
              data-test-id="${test.id}"
              type="text"
              inputmode="text"
              value="${DEFAULT_TIME_LIMIT_MINUTES}"
              spellcheck="false"
            >
          </div>
          <span class="muted microcopy">Default is 90 minutes. Leave blank to use the default.</span>
        </label>
        <button class="primary" data-test-id="${test.id}">Start</button>
      </div>
    `;
    const startBtn = card.querySelector("button");
    const selectEl = card.querySelector(".count-select");
    const timeSelect = card.querySelector(".time-select");
    const preferredMinutes =
      state.activeTest && state.activeTest.id === test.id
        ? state.lastTimeLimitMinutes
        : DEFAULT_TIME_LIMIT_MINUTES;
    if (timeSelect) {
      timeSelect.value = preferredMinutes > 0 ? preferredMinutes : DEFAULT_TIME_LIMIT_MINUTES;
    }
    startBtn.addEventListener("click", () => {
      const count = Number(selectEl.value);
      const parsed = normalizeTimeLimitInput(timeSelect.value);
      startTest(test.id, count, "regular", parsed.minutes);
    });
    testListEl.appendChild(card);
  });
}

async function startTest(testId, count = 0, mode = "regular", timeLimitMinutes = 0) {
  if (!testId) return;
  state.lastRequestedCount = count;
  const normalizedMinutes =
    typeof timeLimitMinutes === "number" && timeLimitMinutes >= 0
      ? timeLimitMinutes
      : DEFAULT_TIME_LIMIT_MINUTES;
  const enforcedMinutes = normalizedMinutes > 0 ? normalizedMinutes : DEFAULT_TIME_LIMIT_MINUTES;
  state.lastTimeLimitMinutes = enforcedMinutes;
  state.mode = mode;
  try {
    const payload = {
      count: count > 0 ? count : undefined,
      mode,
      time_limit_seconds: enforcedMinutes * 60,
    };
    const res = await fetch(`/api/tests/${encodeURIComponent(testId)}/start_quiz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const bodyText = await res.text();
    let data = null;
    try {
      data = bodyText ? JSON.parse(bodyText) : null;
    } catch (err) {
      data = null;
    }
    if (!res.ok || !data) {
      const fallbackMessage =
        mode === "review_incorrect"
          ? "No missed questions recorded for this test yet."
          : "Unable to load test";
      const msg =
        (data && (data.description || data.error || data.message)) ||
        bodyText ||
        fallbackMessage;
      throw new Error(typeof msg === "string" ? msg : fallbackMessage);
    }
    state.activeTest = data.test;
    state.mode = data.mode || mode || "regular";
    state.randomOrderEnabled = isRandomOrderEnabled();
    state.questions = state.randomOrderEnabled ? shuffleQuestions(data.questions || []) : data.questions || [];
    if (!state.questions.length) throw new Error("No questions returned for this session.");
    state.currentIndex = 0;
    state.score = 0;
    state.answers = {};
    state.selectedCount = data.selected_count || state.questions.length;
    state.totalAvailable = data.test?.total || state.questions.length;
    state.showAllExplanations = false;
    state.perQuestionMs = {};
    const resolvedLimitSeconds = data.time_limit_seconds || enforcedMinutes * 60;
    const safeLimitMs = Math.max(1000, resolvedLimitSeconds * 1000);
    state.timeLimitMs = safeLimitMs;
    state.timeRemainingMs = state.timeLimitMs;
    state.totalElapsedMs = 0;
    state.questionStart = null;
    state.sessionComplete = false;
    state.endedByTimer = false;
    state.resultsPersisted = false;
    state.lastResults = [];
    state.questionGridCollapsed = true;
    state.timerHidden = state.timerHidden || false;
    startSessionTimer();
    activeTestName.textContent = state.activeTest.name;
    questionArea.classList.remove("hidden");
    summaryArea.classList.add("hidden");
    renderQuestionCard();
    updateScore();
    updateProgress();
    updateSessionMeta();
  } catch (err) {
    questionArea.innerHTML = `<div class="placeholder"><p class="muted">${escapeHtml(err.message || "Unable to load test")}</p></div>`;
  }
}

function questionDone(questionId) {
  const status = state.answers[questionId];
  return Boolean(status && (status.correct !== undefined || status.revealed || status.choice !== undefined));
}

function goToQuestion(idx) {
  if (state.sessionComplete || state.endedByTimer) return;
  if (!state.questions[idx]) return;
  recordCurrentQuestionTime();
  state.currentIndex = idx;
  renderQuestionCard();
}

function renderQuestionGrid() {
  if (!questionGrid || !questionGridShell || !questionGridWrapper) return;
  const hasQuestions = Boolean(state.questions.length) && !state.sessionComplete;
  if (!hasQuestions) {
    questionGridWrapper.classList.add("hidden");
    questionGridShell.classList.add("hidden");
    questionGrid.classList.add("hidden");
    questionGrid.innerHTML = "";
    if (questionGridToggle) {
      questionGridToggle.textContent = "Show boxes";
      questionGridToggle.setAttribute("aria-expanded", "false");
      questionGridToggle.disabled = true;
    }
    return;
  }

  questionGridWrapper.classList.remove("hidden");
  if (questionGridToggle) {
    questionGridToggle.disabled = false;
    questionGridToggle.textContent = state.questionGridCollapsed ? "Show boxes" : "Hide boxes";
    questionGridToggle.setAttribute("aria-expanded", (!state.questionGridCollapsed).toString());
  }

  questionGridShell.classList.toggle("hidden", state.questionGridCollapsed);
  questionGrid.classList.toggle("hidden", state.questionGridCollapsed);
  questionGrid.innerHTML = "";
  const idToIndex = new Map(state.questions.map((q, i) => [q.id, i]));
  const sortedByNumber = [...state.questions].sort((a, b) => {
    const aNum = Number.isFinite(a.number) ? a.number : idToIndex.get(a.id) + 1;
    const bNum = Number.isFinite(b.number) ? b.number : idToIndex.get(b.id) + 1;
    return aNum - bNum;
  });
  const activeId = state.questions[state.currentIndex]?.id;

  sortedByNumber.forEach((q) => {
    const idx = idToIndex.get(q.id);
    const status = state.answers[q.id] || {};
    const btn = document.createElement("button");
    btn.className = "qdot";
    const label = Number.isFinite(q.number) ? q.number : idx + 1;
    btn.textContent = label;
    btn.title = `Question ${label}`;
    if (q.id === activeId) btn.classList.add("active");
    if (status.correct === true) {
      btn.classList.add("correct");
    } else if (status.correct === false) {
      btn.classList.add("incorrect");
    } else if (status.choice !== undefined || status.revealed) {
      btn.classList.add("answered");
    }
    if (state.endedByTimer) {
      btn.disabled = true;
    } else {
      btn.addEventListener("click", () => goToQuestion(idx));
    }
    questionGrid.appendChild(btn);
  });

  if (!state.questionGridCollapsed) {
    scrollActiveQuestionIntoView();
  }
}

function scrollActiveQuestionIntoView() {
  if (!questionGridShell || !questionGrid) return;
  const activeBtn = questionGrid.querySelector(".qdot.active");
  if (!activeBtn || typeof activeBtn.scrollIntoView !== "function") return;
  const shellRect = questionGridShell.getBoundingClientRect();
  const btnRect = activeBtn.getBoundingClientRect();
  if (btnRect.top < shellRect.top || btnRect.bottom > shellRect.bottom) {
    activeBtn.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }
}

function toggleQuestionGrid() {
  state.questionGridCollapsed = !state.questionGridCollapsed;
  renderQuestionGrid();
  persistSession();
}

function renderQuestionCard() {
  if (!state.activeTest || !state.questions.length) {
    questionArea.innerHTML = `<div class="placeholder"><p class="muted">Select a test to begin.</p></div>`;
    renderQuestionGrid();
    return;
  }

  if (state.sessionComplete) return;
  startQuestionTimer();
  const question = state.questions[state.currentIndex];
  const status = state.answers[question.id];
  const disableOptions = state.sessionComplete || state.endedByTimer;
  const controlsDisabled = state.sessionComplete || state.endedByTimer;
  const feedbackText = status
    ? status.correct
      ? "Correct! Change your answer anytime to re-check."
      : status.correct === false
        ? "Incorrect — adjust your pick to try again."
        : "Answer revealed"
    : "Pick or change an answer to get instant feedback.";

  const isLast = state.currentIndex === state.questions.length - 1;
  questionArea.innerHTML = `
    <div class="question-head">
      <div>
        <p class="eyebrow">Question ${state.currentIndex + 1} of ${state.questions.length}${question.number ? ` • #${question.number}` : ""}</p>
        <div class="question-text">${escapeHtml(question.question)}</div>
      </div>
    </div>
    <div class="options">
      ${question.options
        .map(
          (option, idx) =>
            `<button class="option-btn" data-idx="${idx}" ${disableOptions ? "disabled" : ""}>
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
      <button id="prev-question" class="ghost" ${controlsDisabled ? "disabled" : ""}>Previous question</button>
      <button id="next-question" class="primary" ${controlsDisabled ? "disabled" : ""}>${isLast ? "Finish" : "Next question"}</button>
      <button id="show-answer" class="secondary" ${controlsDisabled ? "disabled" : ""}>Show correct answer</button>
      <button id="submit-quiz" class="ghost" ${controlsDisabled ? "disabled" : ""}>Submit & score</button>
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
  const submitBtn = document.getElementById("submit-quiz");
  submitBtn.addEventListener("click", () => {
    if (state.sessionComplete || state.endedByTimer) return;
    showSummary(false);
  });
  const nextBtn = document.getElementById("next-question");
  nextBtn.addEventListener("click", nextQuestion);
  nextBtn.disabled = controlsDisabled;
  const prevBtn = document.getElementById("prev-question");
  prevBtn.addEventListener("click", prevQuestion);
  prevBtn.disabled = controlsDisabled;
  updateScore();
  updateProgress();
  renderQuestionGrid();
  persistSession();
}

async function handleAnswer(question, choiceIndex) {
  if (state.sessionComplete || state.endedByTimer) return;
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
    const existing = state.answers[question.id] || {};
    state.answers[question.id] = { ...existing, choice: choiceIndex, correct: data.correct };
    recomputeScoreFromAnswers();
    renderQuestionCard();
    persistSession();
  } catch (err) {
    const feedbackEl = document.getElementById("feedback");
    if (feedbackEl) {
      feedbackEl.textContent = err.message;
      feedbackEl.classList.remove("correct", "incorrect");
    }
    startQuestionTimer();
    persistSession();
  }
}

async function revealAnswer(question) {
  if (state.sessionComplete || state.endedByTimer) return;
  try {
    const details = await ensureAnswerDetails(question);
    state.answers[question.id] = { ...(state.answers[question.id] || {}), ...details, revealed: true };
    renderQuestionCard();
    document.getElementById("next-question").disabled = false;
    persistSession();
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
  if (state.sessionComplete || state.endedByTimer) return;
  recordCurrentQuestionTime();
  const currentQuestion = state.questions[state.currentIndex];
  const total = state.questions.length;
  const answeredCount = state.questions.reduce((acc, q) => (questionDone(q.id) ? acc + 1 : acc), 0);
  if (answeredCount >= total) {
    await showSummary(state.showAllExplanations);
    progressFill.style.width = "100%";
    return;
  }
  for (let step = 1; step <= total; step += 1) {
    const idx = (state.currentIndex + step) % total;
    if (!questionDone(state.questions[idx].id)) {
      state.currentIndex = idx;
      renderQuestionCard();
      return;
    }
  }
  state.currentIndex = (state.currentIndex + 1) % total;
  renderQuestionCard();
}

function prevQuestion() {
  if (state.sessionComplete || state.endedByTimer) return;
  recordCurrentQuestionTime();
  const total = state.questions.length;
  state.currentIndex = (state.currentIndex - 1 + total) % total;
  renderQuestionCard();
}

async function persistResults() {
  if (!state.activeTest || state.resultsPersisted) return;
  const results = state.questions.map((q) => {
    const status = state.answers[q.id];
    return { question_id: q.id, correct: Boolean(status && status.correct === true) };
  });
  state.lastResults = results;
  try {
    const res = await fetch(
      `/api/tests/${encodeURIComponent(state.activeTest.id)}/results`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ results }),
      }
    );
    if (!res.ok) throw new Error("Failed to store session results");
    state.resultsPersisted = true;
  } catch (err) {
    console.warn("Could not store missed questions", err);
  }
}

async function showSummary(showAll = false) {
  if (!state.sessionComplete) {
    state.sessionComplete = true;
    recordCurrentQuestionTime();
    stopSessionTimer();
  }
  questionArea.classList.add("hidden");
  summaryArea.classList.remove("hidden");
  if (questionGrid) {
    questionGrid.classList.add("hidden");
  }
  if (questionGridShell) {
    questionGridShell.classList.add("hidden");
  }
  if (questionGridWrapper) {
    questionGridWrapper.classList.add("hidden");
  }
  if (questionGridToggle) {
    questionGridToggle.setAttribute("aria-expanded", "false");
    questionGridToggle.textContent = "Show boxes";
    questionGridToggle.disabled = true;
  }
  const summaryScore = document.getElementById("summary-score");
  const summaryAccuracy = document.getElementById("summary-accuracy");
  const summaryList = document.getElementById("summary-list");
  const summaryTime = document.getElementById("summary-time");
  const noteMessages = [];
  if (state.endedByTimer) {
    noteMessages.push("Session ended because the timer ran out.");
  }
  if (state.mode === "review_incorrect") {
    noteMessages.push("Reviewing missed questions only.");
  }
  summaryNote.textContent = noteMessages.join(" ");
  summaryNote.classList.toggle("hidden", !noteMessages.length);
  const total = state.questions.length;
  const displayTotal = total || state.selectedCount || 0;
  scoreDisplay.textContent = `${state.score} / ${displayTotal}`;
  const accuracy = total ? Math.round((state.score / total) * 100) : 0;
  summaryScore.textContent = `You answered ${state.score} out of ${total} correctly.`;
  summaryAccuracy.textContent = `Accuracy: ${accuracy}%`;
  summaryTime.textContent = `Total time: ${formatMs(state.totalElapsedMs || 0)}${
    state.timeLimitMs ? ` (limit ${formatMs(state.timeLimitMs)})` : ""
  }`;
  summaryList.innerHTML = "";
  const targets = state.questions.filter((q) => {
    const status = state.answers[q.id];
    if (showAll) return true;
    return status && status.correct === false;
  });
  try {
    await Promise.all(targets.map((q) => ensureAnswerDetails(q)));
  } catch (err) {
    console.warn("Could not load explanations", err);
  }
  state.showAllExplanations = showAll;

  state.questions.forEach((q, idx) => {
    const status = state.answers[q.id] || {};
    let label = "Not answered";
    let tone = "";
    if (status.correct === true) {
      label = "Correct";
      tone = "correct";
    } else if (status.correct === false) {
      label = "Incorrect";
      tone = "incorrect";
    } else if (status.revealed) {
      label = "Revealed";
    } else if (state.endedByTimer) {
      label = "Not answered (timed out)";
    }
    const item = document.createElement("div");
    item.className = "summary-item";
    const shouldShowExplanation = showAll || status.correct === false;
    const timeTaken = state.perQuestionMs[q.id] || 0;
    const explanationHtml =
      shouldShowExplanation && status.explanation !== undefined
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
  await persistResults();
  updateSessionMeta();
  updateTimerDisplay();
  persistSession();
}

reloadBtn.addEventListener("click", fetchTests);
restartBtn.addEventListener("click", () => {
  if (state.activeTest) {
    startTest(
      state.activeTest.id,
      state.lastRequestedCount || 0,
      state.mode || "regular",
      state.lastTimeLimitMinutes ?? DEFAULT_TIME_LIMIT_MINUTES
    );
  }
});
showAllExplanationsBtn.addEventListener("click", () => {
  if (!state.activeTest) return;
  showSummary(true);
});
toggleTimerBtn.addEventListener("click", toggleTimer);
if (questionGridToggle) {
  questionGridToggle.addEventListener("click", toggleQuestionGrid);
}
reviewIncorrectBtn.addEventListener("click", () => {
  if (!state.activeTest) return;
  startTest(
    state.activeTest.id,
    0,
    "review_incorrect",
    state.lastTimeLimitMinutes ?? DEFAULT_TIME_LIMIT_MINUTES
  );
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
  state.timeLimitMs = 0;
  state.timeRemainingMs = 0;
  state.mode = "regular";
  state.sessionComplete = false;
  state.endedByTimer = false;
  state.resultsPersisted = false;
  state.lastResults = [];
  state.lastRequestedCount = 0;
  state.lastTimeLimitMinutes = DEFAULT_TIME_LIMIT_MINUTES;
  state.questionGridCollapsed = true;
  state.timerHidden = false;
  state.sessionStart = null;
  state.questionStart = null;
  summaryNote.classList.add("hidden");
  stopSessionTimer();
  updateTimerDisplay();
  activeTestName.textContent = "None selected";
  questionArea.classList.remove("hidden");
  summaryArea.classList.add("hidden");
  if (questionGrid) {
    questionGrid.classList.add("hidden");
    questionGrid.innerHTML = "";
  }
  if (questionGridShell) {
    questionGridShell.classList.add("hidden");
  }
  if (questionGridWrapper) {
    questionGridWrapper.classList.add("hidden");
  }
  if (questionGridToggle) {
    questionGridToggle.textContent = "Show boxes";
    questionGridToggle.setAttribute("aria-expanded", "false");
    questionGridToggle.disabled = true;
  }
  renderQuestionCard();
  updateScore();
  updateProgress();
  clearPersistedSession();
  updateSessionMeta();
  persistSession();
});

window.addEventListener("beforeunload", () => {
  recordCurrentQuestionTime();
  persistSession();
});

window.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    recordCurrentQuestionTime();
    persistSession();
  }
});

// Kick off
restoreSessionFromStorage();
fetchTests();
updateTimerDisplay();
