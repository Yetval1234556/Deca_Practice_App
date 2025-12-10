const SESSION_KEY = "deca-active-session-v1";
const HISTORY_KEY = "deca-history-v1";
const DEFAULT_TIME_LIMIT_MINUTES = 90;

const state = {
  tests: [],
  activeTest: null,
  questions: [],
  currentIndex: 0,
  score: 0,
  answers: {},
  selectedCount: 0,
  totalAvailable: 0,
  showAllExplanations: false,
  sessionStart: null,
  questionStart: null,
  timerInterval: null,
  totalElapsedMs: 0,
  perQuestionMs: {},
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

// Global Elements
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
const summaryChart = document.getElementById("summary-chart");
const chartCanvas = document.getElementById("performance-chart");

let performanceChartInstance = null; // Chart.js instance
let settingsOpenedFromHash = false;

/**
 * --- UTILITIES ---
 */

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

function formatMs(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

/**
 * --- HISTORY & ANALYTICS ---
 */

function saveSessionToHistory() {
  if (!state.activeTest || !state.questions.length) return;

  const historyItem = {
    testId: state.activeTest.id,
    testName: state.activeTest.name,
    date: new Date().toISOString(),
    score: state.score,
    total: state.questions.length,
    elapsedMs: state.totalElapsedMs,
    mode: state.mode
  };

  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const history = raw ? JSON.parse(raw) : [];
    history.push(historyItem);
    // Keep last 50 runs
    if (history.length > 50) history.shift();
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch (e) {
    console.error("Failed to save history", e);
  }
}

function renderPerformanceChart() {
  if (!chartCanvas || !summaryChart) return;

  // Destroy old instance if exists
  if (performanceChartInstance) {
    performanceChartInstance.destroy();
    performanceChartInstance = null;
  }

  // Load history
  let history = [];
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    history = raw ? JSON.parse(raw) : [];
  } catch (e) { }

  if (history.length < 2) {
    summaryChart.classList.add("hidden");
    return;
  }
  summaryChart.classList.remove("hidden");

  // Take last 10 sessions
  const recent = history.slice(-10);

  const labels = recent.map((h, i) => `Run ${i + 1}`);
  const dataPoints = recent.map(h => Math.round((h.score / h.total) * 100));

  performanceChartInstance = new Chart(chartCanvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Accuracy (%)',
        data: dataPoints,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99, 102, 241, 0.2)',
        tension: 0.4,
        fill: true,
        pointBackgroundColor: '#8b5cf6',
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.raw}% Accuracy`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#9ca3af' }
        },
        x: {
          display: false // hide labels for cleaner look
        }
      }
    }
  });
}

/**
 * --- SESSION STATE MANAGEMENT ---
 */

function persistSession() {
  if (typeof localStorage === "undefined") return;
  if (!state.activeTest || !state.questions.length) {
    try { localStorage.removeItem(SESSION_KEY); } catch (err) { }
    return;
  }
  const payload = { ...state }; // Clone state
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(payload));
  } catch (err) { }
}

function clearPersistedSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch (err) { }
}

function resetState() {
  stopSessionTimer();
  state.activeTest = null;
  state.questions = [];
  state.answers = {};
  state.currentIndex = 0;
  state.score = 0;
  state.selectedCount = 0;
  state.totalAvailable = 0;
  state.sessionComplete = false;
  state.endedByTimer = false;
  state.mode = "regular";
  state.questionStart = null;
  state.perQuestionMs = {};
  questionArea.classList.remove("hidden");
  summaryArea.classList.add("hidden");
  renderQuestionCard();
  updateScore();
  updateProgress();
  renderQuestionGrid();
  updateSessionMeta();
  clearPersistedSession();
}

function recomputeScoreFromAnswers() {
  state.score = state.questions.reduce((acc, q) => {
    const status = state.answers[q.id];
    return (status && status.correct === true) ? acc + 1 : acc;
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
    <div class="session-footer__meta">${countLabel} | ${modeLabel} | ${orderLabel} | ${limitLabel} | ${statusLabel}</div>
    <div class="session-footer__progress">Answered ${answered}/${state.questions.length}</div>
  `;
}

/**
 * --- TIMER SUBSYSTEM ---
 */

function updateTimerDisplay() {
  if (toggleTimerBtn) {
    toggleTimerBtn.textContent = state.timerHidden ? "Show" : "Hide";
  }
  if (state.timerHidden) {
    timerDisplay.textContent = "--";
    return;
  }
  if (!state.sessionStart) {
    if (state.sessionComplete && state.totalElapsedMs) {
      timerDisplay.textContent = formatMs(state.totalElapsedMs);
      return;
    }
    const base = formatMs(state.timeLimitMs || DEFAULT_TIME_LIMIT_MINUTES * 60 * 1000);
    timerDisplay.textContent = `${base}`;
    return;
  }
  const elapsed = Math.max(0, Date.now() - state.sessionStart);
  state.totalElapsedMs = elapsed;
  if (state.timeLimitMs) {
    const remaining = Math.max(state.timeLimitMs - elapsed, 0);
    state.timeRemainingMs = remaining;
    timerDisplay.textContent = `${formatMs(remaining)}`;
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
  if (window.sfx) window.sfx.playClick();
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

/**
 * --- SYSTEM LIFECYCLE ---
 */

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
  try { raw = localStorage.getItem(SESSION_KEY); } catch (err) { return false; }
  if (!raw) return false;
  let data = null;
  try { data = JSON.parse(raw); } catch (err) { return false; }

  if (!data || !data.activeTest || !Array.isArray(data.questions) || !data.questions.length) {
    return false;
  }

  // Restore state
  Object.assign(state, data);

  // Re-verify index bounds
  if (state.currentIndex < 0 || state.currentIndex >= state.questions.length) {
    state.currentIndex = 0;
  }

  // Ensure timers are sane
  if (!state.timeLimitMs || state.timeLimitMs <= 0) {
    state.timeLimitMs = DEFAULT_TIME_LIMIT_MINUTES * 60 * 1000;
  }

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

/**
 * --- DATA FETCHING & UI RENDERING ---
 */

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
          <span class="muted small-label">Count</span>
          <select class="count-select" data-test-id="${test.id}">
            ${options
        .map((opt) => `<option value="${opt.value}">${opt.value === 0 ? "All" : opt.label}</option>`)
        .join("")}
          </select>
        </label>
        <label>
          <span class="muted small-label">Mins</span>
          <div class="time-input-row">
            <input
              class="time-select"
              data-test-id="${test.id}"
              type="text"
              inputmode="numeric"
              value="${DEFAULT_TIME_LIMIT_MINUTES}"
              spellcheck="false"
              style="width: 50px; text-align: center;"
            >
          </div>
        </label>
        <button class="primary" data-test-id="${test.id}">
          <i class="ph ph-play"></i> Start
        </button>
      </div>
    `;

    // Bindings
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
      if (window.sfx) window.sfx.playSelect();
      if (typeof window.unlockAudioAndPlay === "function") {
        window.unlockAudioAndPlay();
      }
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
      const msg = (data && (data.description || data.error || data.message)) || "Unable to load test";
      throw new Error(msg);
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
  if (window.sfx) window.sfx.playHover();
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
      questionGridToggle.textContent = "Show";
      questionGridToggle.disabled = true;
    }
    return;
  }

  questionGridWrapper.classList.remove("hidden");
  if (questionGridToggle) {
    questionGridToggle.disabled = false;
    questionGridToggle.innerHTML = state.questionGridCollapsed
      ? `<i class="ph ph-squares-four"></i> Show`
      : `<i class="ph ph-caret-up"></i> Hide`;
  }

  questionGridShell.classList.toggle("hidden", state.questionGridCollapsed);
  questionGrid.classList.toggle("hidden", state.questionGridCollapsed);
  const contentFragment = document.createDocumentFragment();
  const existingButtons = Array.from(questionGrid.children);
  const totalNeeded = state.questions.length;

  // 1. Create missing buttons
  if (existingButtons.length < totalNeeded) {
    for (let i = existingButtons.length; i < totalNeeded; i++) {
      const btn = document.createElement("button");
      btn.className = "qdot";
      questionGrid.appendChild(btn);
    }
  }
  // 2. Remove excess buttons (unlikely but safe)
  while (questionGrid.children.length > totalNeeded) {
    questionGrid.removeChild(questionGrid.lastChild);
  }

  const idToIndex = new Map(state.questions.map((q, i) => [q.id, i]));
  const sortedByNumber = [...state.questions].sort((a, b) => {
    const aNum = Number.isFinite(a.number) ? a.number : idToIndex.get(a.id) + 1;
    const bNum = Number.isFinite(b.number) ? b.number : idToIndex.get(b.id) + 1;
    return aNum - bNum;
  });
  const activeId = state.questions[state.currentIndex]?.id;

  // 3. Update existing buttons efficiently
  Array.from(questionGrid.children).forEach((btn, i) => {
    const q = sortedByNumber[i];
    if (!q) return;
    const idx = idToIndex.get(q.id);
    const status = state.answers[q.id] || {};
    const label = Number.isFinite(q.number) ? q.number : idx + 1;

    // Update text/title only if changed (text node check is fast)
    if (btn.textContent != label) btn.textContent = label;
    if (btn.title !== `Question ${label}`) btn.title = `Question ${label}`;

    // Efficient class management
    const isActive = q.id === activeId;
    const isCorrect = status.correct === true;
    const isIncorrect = status.correct === false;
    const isAnswered = (status.choice !== undefined || status.revealed) && !isCorrect && !isIncorrect;

    // Helper to minimize DOM tokens list touching
    const setClass = (cls, on) => {
      if (on && !btn.classList.contains(cls)) btn.classList.add(cls);
      if (!on && btn.classList.contains(cls)) btn.classList.remove(cls);
    };

    setClass("active", isActive);
    setClass("correct", isCorrect);
    setClass("incorrect", isIncorrect);
    setClass("answered", isAnswered);

    // Re-bind click listener only if needed? 
    // Actually, cleaner to just replace the clone or use event delegation. 
    // For simplicity in this codebase, let's just update the ONCLICK property to avoid adding multiple listeners
    btn.onclick = function () { goToQuestion(idx); };

    if (state.endedByTimer) {
      btn.disabled = true;
    } else {
      btn.disabled = false;
    }
  });

  if (!state.questionGridCollapsed) {
    scrollActiveQuestionIntoView();
  }
}

function areAnimationsEnabled() {
  try {
    const key = "deca-animations-enabled";
    const val = localStorage.getItem(key);
    return val === null || val === "true"; // Default true
  } catch { return true; }
}

function triggerConfetti() {
  if (!areAnimationsEnabled()) return;
  if (window.confetti) {
    window.confetti({
      particleCount: 100,
      spread: 70,
      origin: { y: 0.6 }
    });
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
  if (window.sfx) window.sfx.playClick();
  renderQuestionGrid();
  persistSession();
}

/**
 * --- KEYBOARD SHORTCUTS ---
 */
document.addEventListener("keydown", (e) => {
  // Only enable if test is active and not finished
  if (summaryArea && !summaryArea.classList.contains("hidden")) return;
  if (!state.activeTest || state.sessionComplete || state.endedByTimer) return;

  // Numbers 1-5 maps to options 0-4
  if (e.key >= '1' && e.key <= '5') {
    const idx = parseInt(e.key) - 1;
    const question = state.questions[state.currentIndex];
    if (question && idx < question.options.length) {
      handleAnswer(question, idx);
    }
  }
  // Letters A-E maps to options 0-4
  const code = e.key.toUpperCase().charCodeAt(0);
  if (code >= 65 && code <= 69) { // A=65, E=69
    const idx = code - 65;
    const question = state.questions[state.currentIndex];
    if (question && idx < question.options.length) {
      handleAnswer(question, idx);
    }
  }

  // Navigation
  if (e.key === "ArrowRight" || e.key === "Enter") {
    nextQuestion();
  }
  if (e.key === "ArrowLeft") {
    prevQuestion();
  }
  if (e.key === " ") { // Spacebar to toggle grid? Or maybe just ignore to prevent scrolling
    // e.preventDefault();
  }
});

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
      ? "Correct! Well done."
      : status.correct === false
        ? "Incorrect."
        : "Answer revealed."
    : "Pick an answer or press key (A, B, C, D).";

  const isLast = state.currentIndex === state.questions.length - 1;
  const letters = ["A", "B", "C", "D", "E"];

  questionArea.innerHTML = `
    <div class="question-head">
      <div>
        <p class="eyebrow">
            Question ${state.currentIndex + 1} of ${state.questions.length} ${question.number ? `| #${question.number}` : ""}
        </p>
        <div class="question-text">${escapeHtml(question.question)}</div>
      </div>
    </div>
    <div class="options">
      ${question.options
      .map(
        (option, idx) =>
          `<button class="option-btn" data-idx="${idx}" ${disableOptions ? "disabled" : ""}>
              <span class="kbd-hint">${letters[idx] || (idx + 1)}</span>
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
      <button id="prev-question" class="ghost" ${controlsDisabled ? "disabled" : ""}>
        <i class="ph ph-caret-left"></i> Previous
      </button>
      <button id="next-question" class="primary" ${controlsDisabled ? "disabled" : ""}>
        ${isLast ? '<i class="ph ph-check-circle"></i> Finish' : 'Next <i class="ph ph-caret-right" style="margin-left:6px; margin-right:0;"></i>'}
      </button>
      <button id="show-answer" class="secondary" ${controlsDisabled ? "disabled" : ""}>
        <i class="ph ph-eye"></i> Answer
      </button>
      <button id="submit-quiz" class="ghost" ${controlsDisabled ? "disabled" : ""}>
        <i class="ph ph-flag"></i> Submit
      </button>
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
    showSummary(false); // finish
    if (window.sfx) window.sfx.playClick();
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

    // Sound FX
    if (window.sfx) {
      if (data.correct) window.sfx.playCorrect();
      else window.sfx.playIncorrect();
    }

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
    if (window.sfx) window.sfx.playClick();
    const details = await ensureAnswerDetails(question);
    state.answers[question.id] = { ...(state.answers[question.id] || {}), ...details, revealed: true };
    renderQuestionCard();
    document.getElementById("next-question").disabled = false;
    persistSession();
  } catch (err) {
    // ignore
  }
}

async function nextQuestion() {
  if (window.sfx) window.sfx.playClick();
  if (state.currentIndex < state.questions.length - 1) {
    goToQuestion(state.currentIndex + 1);
  } else {
    // Finish
    await showSummary(false);
  }
}

function prevQuestion() {
  if (window.sfx) window.sfx.playClick();
  if (state.currentIndex > 0) {
    goToQuestion(state.currentIndex - 1);
  }
}

async function showSummary(forceShowExplanations) {
  state.sessionComplete = true;
  clearInterval(state.timerInterval);
  updateSessionMeta();

  // Persist history once
  if (!state.resultsPersisted) {
    saveSessionToHistory();
    state.resultsPersisted = true;
  }

  // UI Updates
  questionArea.classList.add("hidden");
  summaryArea.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });

  recomputeScoreFromAnswers();

  // Calc Stats
  const total = state.questions.length;
  const attempted = Object.keys(state.answers).length;
  const score = state.score;
  const percent = total > 0 ? Math.round((score / total) * 100) : 0;

  // Render Stats
  const sScore = document.getElementById("summary-score");
  const sAcc = document.getElementById("summary-accuracy");
  const sTime = document.getElementById("summary-time");

  if (sScore) sScore.textContent = `${score} / ${total}`;
  if (sAcc) sAcc.textContent = `${percent}% Accuracy`;
  if (sTime) sTime.textContent = `Total time: ${formatMs(state.totalElapsedMs)}`;

  // Render Badge
  const badgeEl = document.getElementById("summary-score-badge");
  if (badgeEl) {
    let badgeClass = "badge-neutral";
    let badgeText = "Completed";

    if (percent >= 90) { badgeClass = "badge-gold"; badgeText = "Outstanding!"; }
    else if (percent >= 80) { badgeClass = "badge-silver"; badgeText = "Great Job!"; }
    else if (percent >= 70) { badgeClass = "badge-bronze"; badgeText = "Good Effort"; }

    badgeEl.className = `summary-badge ${badgeClass}`;
    badgeEl.textContent = badgeText;
  }

  // Celebration effects
  const animEnabled = localStorage.getItem("deca-animations-enabled") !== "false";
  if (percent > 60 && animEnabled) {
    triggerConfetti();
    if (window.sfx && window.sfx.enabled) window.sfx.playFanfare();
  }

  // Render Charts
  setTimeout(() => {
    renderPerformanceChart();
  }, 100);
}

function renderExplanation(question, status) {
  const el = document.getElementById("explanation");
  if (!el || !status.explanation) return;
  el.innerHTML = `
    <strong>Correct Answer: ${status.correctLetter}</strong><br>
    ${escapeHtml(status.explanation)}
  `;
  el.classList.remove("hidden");
}

// --- Audio Player Logic ---
// Audio is handled by bg-music.js


// --- Settings Virtual Page Logic ---
function openSettings(fromHash = false) {
  const overlay = document.getElementById("settings-overlay");
  if (!overlay) return;
  settingsOpenedFromHash = Boolean(fromHash);
  initSettingsLogic(); // Refresh state
  overlay.classList.remove("hidden");

  const settingsState = { view: "settings" };
  if (fromHash) {
    history.replaceState(settingsState, "", "#/settings");
  } else if (!history.state || history.state.view !== "settings") {
    history.pushState(settingsState, "", "#/settings");
  } else if (window.location.hash !== "#/settings") {
    history.replaceState(settingsState, "", "#/settings");
  }
}

function closeSettings(opts = {}) {
  const overlay = document.getElementById("settings-overlay");
  if (!overlay) return;

  overlay.classList.add("hidden");
  const clearHash = () => {
    if (window.location.hash === "#/settings") {
      history.replaceState(null, "", window.location.pathname);
    }
  };

  if (opts.fromPop) {
    settingsOpenedFromHash = false;
    clearHash();
    return;
  }

  if (settingsOpenedFromHash) {
    settingsOpenedFromHash = false;
    clearHash();
    return;
  }

  if (history.state && history.state.view === "settings") {
    history.back();
    // If back() leaves us on the hash (single entry), clear it manually.
    setTimeout(clearHash, 80);
  } else {
    clearHash();
  }
}

// Handle Browser Back Button
window.addEventListener("popstate", (event) => {
  const overlay = document.getElementById("settings-overlay");
  if (!overlay) return;
  if (event.state && event.state.view === "settings") {
    initSettingsLogic();
    overlay.classList.remove("hidden");
  } else {
    closeSettings({ fromPop: true });
  }
});

function initSettingsLogic() {
  const themeButtons = Array.from(document.querySelectorAll("[data-theme-option]"));

  // Theme Logic
  const currentTheme = window.Theme ? window.Theme.get() : "light";
  themeButtons.forEach((btn) => {
    const t = btn.dataset.theme;
    const isActive = t === currentTheme;
    btn.classList.toggle("active", isActive);

    // Remove old listeners to avoid dupes (simple way: clone node? or just re-add is fine if careful)
    // Actually, cleaner to just set onclick
    btn.onclick = () => {
      if (window.Theme) window.Theme.apply(t);
      initSettingsLogic(); // Re-render active state
    };
  });

  // Toggles
  setupToggle("random-order-check", "deca-random-order", false);
  setupToggle("animations-toggle", "deca-animations-enabled", true);

  // Perf Mode
  const perfToggle = document.getElementById("perf-mode-toggle");
  if (perfToggle) {
    const isPerf = localStorage.getItem("deca-perf-mode") === "true";
    perfToggle.checked = isPerf;
    perfToggle.onchange = (e) => {
      localStorage.setItem("deca-perf-mode", e.target.checked);
      document.documentElement.classList.toggle("perf-mode", e.target.checked);
    };
  }

  // Audio Sync is handled by bg-music.js
}

function setupToggle(id, key, defaultVal) {
  const el = document.getElementById(id);
  if (!el) return;
  const stored = localStorage.getItem(key);
  el.checked = stored === null ? defaultVal : (stored === "true");
  el.onchange = (e) => localStorage.setItem(key, e.target.checked);
}


// Initialization
document.addEventListener("DOMContentLoaded", () => {
  // Audio init is handled by bg-music.js

  if (reloadBtn) reloadBtn.addEventListener("click", fetchTests);
  if (toggleTimerBtn) toggleTimerBtn.addEventListener("click", toggleTimer);
  if (questionGridToggle) questionGridToggle.addEventListener("click", toggleQuestionGrid);
  if (restartBtn) restartBtn.addEventListener("click", () => window.location.reload());
  if (backToTestsBtn) backToTestsBtn.addEventListener("click", () => window.location.reload());

  // Back to home from summary uses resetState
  const backSumm = document.getElementById("back-to-home-summ");
  if (backSumm) backSumm.onclick = () => {
    resetState();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (window.Theme) window.Theme.init();

  if (window.location.hash === "#/settings") {
    openSettings(true);
  }

  // Clean Slate: Force reset on load
  try {
    localStorage.removeItem(SESSION_KEY);
    resetState();
  } catch (e) { }

  // Always fetch tests to populate sidebar
  fetchTests();
});
