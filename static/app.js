const SESSION_KEY = "deca-active-session-v1";
const HISTORY_KEY = "deca-history-v1";
const LOCAL_TESTS_KEY = "deca-local-tests-v1";
const DEFAULT_TIME_LIMIT_MINUTES = 90;

const state = {
    tests: [],
    activeTest: null,
    questions: [],
    currentIndex: 0,
    score: 0,
    answers: {},
    currentSelection: null,
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
    isLocalActive: false,
    strikes: {},
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
const summaryChart = document.getElementById("summary-chart");
const chartCanvas = document.getElementById("performance-chart");
const uploadInput = document.getElementById("pdf-upload-input");
const uploadBtn = document.getElementById("pdf-upload-btn");
const uploadStatus = document.getElementById("pdf-upload-status");
const localTests = new Map();
const hiddenTestIds = new Set();
const HIDDEN_TESTS_KEY = "deca-hidden-tests";



if (!window.sfx) {
    window.sfx = {
        enabled: false,
        playClick() { },
        playHover() { },
        playSelect() { },
        playCorrect() { },
        playIncorrect() { },
        playFanfare() { },
    };
}

let performanceChartInstance = null;
let settingsOpenedFromHash = false;



function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (tag) => {
        const chars = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
        return chars[tag] || tag;
    });
}

function tidyText(str) {
    return (str || "").replace(/\s+/g, " ").trim();
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

function setUploadStatus(message, isError = false) {
    if (!uploadStatus) return;
    uploadStatus.textContent = message || "";
    uploadStatus.classList.toggle("error", Boolean(isError));
}


function persistHiddenTests() {
    localStorage.setItem("deca-hidden-tests", JSON.stringify(Array.from(hiddenTestIds)));
}

function persistLocalTestToIDB(testData) {
    if (!testData || !testData.id) return;
    // Ensure we save the full object structure expected by fetching/hydration
    const record = {
        id: testData.id,
        name: testData.name,
        description: testData.description,
        questions: testData.questions || [],
        question_count: (testData.questions || []).length,
        timestamp: Date.now()
    };
    IDB.saveTest(record).catch(e => console.error("Failed to save to IDB", e));
}

function deleteLocalTestFromIDB(testId) {
    IDB.deleteTest(testId).catch(e => console.error("Failed to delete from IDB", e));
}

function init() {
    try {
        const storedHidden = localStorage.getItem("deca-hidden-tests");
        if (storedHidden) {
            const parsed = JSON.parse(storedHidden);
            if (Array.isArray(parsed)) parsed.forEach(id => hiddenTestIds.add(id));
        }
    } catch (e) { console.error("Error loading hidden tests", e); }

    const storedTimerHidden = localStorage.getItem("deca-timer-hidden");
    state.timerHidden = storedTimerHidden === "true";

    const storedGridCollapsed = localStorage.getItem("deca-grid-collapsed");
    state.questionGridCollapsed = storedGridCollapsed !== "false";

    const storedDisableTimer = localStorage.getItem("deca-timer-disabled");
    if (disableTimerToggle) {
        disableTimerToggle.checked = storedDisableTimer === "true";
    }

    fetchTests();
    setupEventListeners();
    applyThemeFromStorage();



    if (activeTestName) activeTestName.textContent = "Select a test";
    updateSessionMeta();
    renderQuestionGrid();

    const savedSession = localStorage.getItem("deca-session-backup");
    if (savedSession) {
        try {
            const parsed = JSON.parse(savedSession);
            if (parsed && parsed.activeTestId && !state.sessionComplete) {
                restoreSession(parsed);
            }
        } catch (e) { console.error("Session restore failed", e); }
    }
}

async function fetchTests() {
    if (testListEl) testListEl.innerHTML = '<p class="muted">Loading tests...</p>';
    state.tests = [];
    const uniqueMap = new Map();

    // 1. Load from Server
    try {
        const res = await fetch("/api/tests", { credentials: "same-origin" });
        if (res.ok) {
            const list = await res.json();
            if (Array.isArray(list)) {
                list.forEach(t => uniqueMap.set(t.id, t));
            }
        }
    } catch (err) {
        console.warn("Server unavailable?", err);
    }

    // 2. Load from IndexedDB
    try {
        const localItems = await IDB.getAllTests();
        if (localItems && Array.isArray(localItems)) {
            localItems.forEach(t => {
                if (!uniqueMap.has(t.id)) {
                    uniqueMap.set(t.id, {
                        ...t,
                        isLocal: true,
                        name: t.name || "Local Test"
                    });
                }
            });
        }
    } catch (e) {
        console.error("IDB Error", e);
    }

    state.tests = Array.from(uniqueMap.values()).filter(t => !hiddenTestIds.has(t.id));
    state.tests.sort((a, b) => (a.name || "").localeCompare(b.name || ""));

    renderTestList();
}

function toggleStrike(e, idx, qId) {
    if (e) e.stopPropagation();
    if (state.sessionComplete || state.endedByTimer) return;

    if (!state.strikes[qId]) {
        state.strikes[qId] = new Set();
    }

    const currentSet = state.strikes[qId];
    if (currentSet.has(idx)) {
        currentSet.delete(idx);
    } else {
        currentSet.add(idx);
    }
    renderQuestionCard();
}

async function refreshTestsWithRetry(retries = 2, delayMs = 300) {
    await fetchTests();
    for (let i = 0; i < retries; i += 1) {
        await new Promise((r) => setTimeout(r, delayMs));
        await fetchTests();
    }
}

async function handleUpload() {
    if (!uploadInput || !uploadInput.files || !uploadInput.files[0]) {
        setUploadStatus("Choose a PDF first.", true);
        return;
    }
    const file = uploadInput.files[0];
    const formData = new FormData();
    formData.append("file", file);
    setUploadStatus("Uploading...", false);
    uploadBtn.disabled = true;

    try {
        const res = await fetch("/api/upload_pdf", {
            method: "POST",
            body: formData,
            credentials: "same-origin",
        });

        const data = await res.json().catch(() => null);
        if (!res.ok || !data) {
            throw new Error((data && (data.description || data.error || data.message)) || "Upload failed.");
        }

        // Save entire test response (which includes questions) to IndexedDB
        // structure of data: { id, name, questions: [...], ... }
        persistLocalTestToIDB(data);

        setUploadStatus(`Uploaded "${data.name}" (${(data.questions || []).length} questions). Saved offline.`);
        uploadInput.value = "";

        // Refresh list to show new test
        await fetchTests();

        setTimeout(() => setUploadStatus(""), 5000);

    } catch (err) {
        setUploadStatus(err.message || "Upload failed.", true);
    } finally {
        uploadBtn.disabled = false;
    }
}



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

        if (history.length > 50) history.shift();
        localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch (e) {
        console.error("Failed to save history", e);
    }
}

function renderPerformanceChart() {
    if (!chartCanvas || !summaryChart) return;


    performanceChartInstance?.destroy();
    performanceChartInstance = null;


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
                    display: false
                }
            }
        }
    });
}



function persistSession() {
    if (typeof localStorage === "undefined") return;
    if (!state.activeTest || !state.questions.length) {
        try { localStorage.removeItem(SESSION_KEY); } catch (err) { }
        return;
    }
    const payload = { ...state };
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
    state.strikes = {};
    state.currentSelection = null;
    state.currentIndex = 0;
    state.score = 0;
    state.selectedCount = 0;
    state.totalAvailable = 0;
    state.sessionComplete = false;
    state.endedByTimer = false;
    state.mode = "regular";
    state.questionStart = null;
    state.perQuestionMs = {};
    state.isLocalActive = false;
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



function updateTimerDisplay() {
    const timerBlock = document.querySelector(".timer-block");
    const timerDisplay = document.getElementById("timer-display");
    if (!timerBlock || !timerDisplay) return;

    const isDisabled = localStorage.getItem("deca-timer-disabled") === "true";
    if (isDisabled) {
        timerBlock.classList.add("hidden");
        return;
    }

    timerBlock.classList.remove("hidden");
    timerDisplay.classList.remove("hidden");

    if (toggleTimerBtn) {
        toggleTimerBtn.textContent = state.timerHidden ? "Show" : "Hide";
    }

    if (state.timerHidden) {

        const base = state.timeRemainingMs ? "Time Hidden" : "Timer";
        timerDisplay.textContent = `${base}`;
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
    // Ensure no duplicate intervals
    if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
    }


    const isDisabled = localStorage.getItem("deca-timer-disabled") === "true";
    if (isDisabled) {
        updateTimerDisplay();
        return;
    }

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
    const isDisabled = localStorage.getItem("deca-timer-disabled") === "true";
    if (isDisabled) return;

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
            state.endedByTimer = true;
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


    if (state.currentSelection !== null &&
        state.currentIndex >= 0 &&
        state.currentIndex < state.questions.length &&
        state.questions[state.currentIndex]) {
        const currentQ = state.questions[state.currentIndex];
        if (!state.answers[currentQ.id] || state.answers[currentQ.id].choice === undefined) {

            await handleAnswer(currentQ, state.currentSelection);
        }
    }

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
                credentials: "same-origin",
                body: JSON.stringify({ results }),
            }
        );
        if (!res.ok) throw new Error("Failed to store session results");
        state.resultsPersisted = true;
    } catch (err) {
        console.warn("Could not store missed questions", err);
    }
}



async function ensureAnswerDetails(question) {
    const existing = state.answers[question.id] || {};
    if (existing.correctIndex !== undefined && existing.explanation !== undefined) {
        return existing;
    }
    if (state.isLocalActive) {
        const q = state.questions.find((item) => item.id === question.id);
        if (q) {
            const mergedLocal = {
                ...existing,
                correctIndex: q.correct_index,
                correctLetter: q.correct_letter,
                explanation: q.explanation,
            };
            state.answers[question.id] = mergedLocal;
            return mergedLocal;
        }
    }
    const res = await fetch(
        `/api/tests/${encodeURIComponent(state.activeTest.id)}/answer/${encodeURIComponent(question.id)}`,
        { credentials: "same-origin" }
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



    Object.assign(state, data);

    // Reconstruct complex types that don't serialize properly
    if (state.strikes && typeof state.strikes === 'object') {
        Object.keys(state.strikes).forEach(qId => {
            if (Array.isArray(state.strikes[qId])) {
                state.strikes[qId] = new Set(state.strikes[qId]);
            } else if (state.strikes[qId] && typeof state.strikes[qId] === 'object' && !(state.strikes[qId] instanceof Set)) {
                state.strikes[qId] = new Set();
            }
        });
    } else {
        state.strikes = {};
    }


    if (state.currentIndex < 0 || state.currentIndex >= state.questions.length) {
        state.currentIndex = 0;
    }


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

    // Smart Review Card
    const missedCount = MissedMgr.getCount();
    if (missedCount > 0) {
        const div = document.createElement("div");
        div.className = "test-card special-card";
        div.style.borderColor = "var(--primary)";
        div.innerHTML = `
            <div class="test-meta">
                <h4><i class="ph ph-target" style="color:var(--primary)"></i> Practice Weaknesses</h4>
                <p>You have <strong>${missedCount}</strong> missed question${missedCount === 1 ? '' : 's'} saved directly for review.</p>
            </div>
            <div class="test-actions">
                <button class="primary" id="start-smart-review">
                    <i class="ph ph-lightning"></i> Review Now
                </button>
            </div>
        `;
        div.querySelector("#start-smart-review").onclick = startSmartReview;
        testListEl.appendChild(div);
    }

    if (!state.tests.length) {
        if (missedCount === 0) {
            testListEl.innerHTML = `<p class="muted">No tests yet. Upload a DECA PDF to begin.</p>`;
        }
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
        ].filter((opt) => opt.value === 0 || opt.value < test.question_count);
        card.innerHTML = `
      <div class="test-meta">
        <h4>${escapeHtml(test.name)}</h4>
        ${test.description ? `<p>${escapeHtml(test.description)}</p>` : ""}
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
        <label style="${localStorage.getItem("deca-timer-disabled") === "true" ? "display:none" : ""}">
          <span class="muted small-label">Time Limit</span>
          <input type="number" class="time-select" data-test-id="${test.id}" min="1" step="1" placeholder="Mins">
        </label>
        <button class="primary" data-test-id="${test.id}">
          <i class="ph ph-play"></i> Start
        </button>
        <button class="secondary exam-btn" data-test-id="${test.id}" title="Simulate Exam (No feedback, strict timer)">
          <i class="ph ph-graduation-cap"></i> Exam
        </button>
        <button class="ghost delete-btn" data-test-id="${test.id}" title="Remove from list">
          <i class="ph ph-trash"></i>
        </button>
      </div>
    `;


        const startBtn = card.querySelector("button.primary");
        const examBtn = card.querySelector("button.exam-btn");
        const deleteBtn = card.querySelector("button.ghost.delete-btn");

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
            const count = Number(selectEl.value);
            const parsed = normalizeTimeLimitInput(timeSelect.value);
            startTest(test.id, count, "regular", parsed.minutes);
        });

        if (examBtn) {
            examBtn.addEventListener("click", () => {
                if (window.sfx) window.sfx.playSelect();
                const count = Number(selectEl.value);
                const parsed = normalizeTimeLimitInput(timeSelect.value);
                // Force a reasonable time limit if none set, or use user's
                const limit = parsed.minutes > 0 ? parsed.minutes : 90;
                startTest(test.id, count, "exam", limit);
            });
        }

        if (deleteBtn) {
            deleteBtn.addEventListener("click", () => {
                deleteTest(test.id, test.name);
            });
        }

        testListEl.appendChild(card);
    });
}

function deleteTest(testId, name) {
    if (!confirm(`Remove "${name}" from your list?`)) return;


    hiddenTestIds.add(testId);
    persistHiddenTests();


    state.tests = state.tests.filter(t => t.id !== testId);


    if (localTests.has(testId)) {
        localTests.delete(testId);
        persistLocalTests();
    }


    renderTestList();
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
        let data = null;
        let usedLocal = false;
        try {
            const res = await fetch(`/api/tests/${encodeURIComponent(testId)}/start_quiz`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify(payload),
            });
            const bodyText = await res.text();
            data = bodyText ? JSON.parse(bodyText) : null;
            if (!res.ok || !data) {
                throw new Error((data && (data.description || data.error || data.message)) || "Unable to load test");
            }
        } catch (err) {
            const cached = localTests.get(testId);
            if (cached && cached.questions && cached.questions.length) {
                data = cached;
                usedLocal = true;
            } else {
                throw err;
            }
        }
        if (data && data.test && Array.isArray(data.questions) && data.questions.length) {
            const existingMeta = state.tests.find((t) => t.id === testId) || localTests.get(testId) || {};
            const enriched = {
                ...data,
                description: data.description || existingMeta.description,
                name: data.name || existingMeta.name,
            };
            if (enriched.test) {
                enriched.test.description = enriched.test.description || existingMeta.description;
                enriched.test.name = enriched.test.name || existingMeta.name;
            }
            localTests.set(data.test.id, enriched);
            persistLocalTests();
        }
        state.isLocalActive = usedLocal;
        const testMeta = data.test || { id: testId, name: data.name || "Uploaded Test", total: (data.questions || []).length };
        state.activeTest = testMeta;
        state.mode = data.mode || mode || "regular";
        state.randomOrderEnabled = isRandomOrderEnabled();
        state.questions = state.randomOrderEnabled ? shuffleQuestions(data.questions || []) : data.questions || [];
        if (!state.questions.length) throw new Error("No questions returned for this session.");
        state.currentIndex = 0;
        state.score = 0;
        state.answers = {};
        state.strikes = {};
        state.currentSelection = null;
        state.selectedCount = data.selected_count || state.questions.length;
        state.totalAvailable = data.test?.total || testMeta.total || state.questions.length;
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
        const isNotFound = err.message.includes("not found") || err.message.includes("404");
        const helpText = isNotFound
            ? "Tests store in memory may be lost if the server restarted. Please <strong>reload the page</strong> or <strong>re-upload the PDF</strong>."
            : "Please try reloading the page.";
        questionArea.innerHTML = `
      <div class="placeholder">
        <div class="empty-state-icon" style="color: var(--danger)">
          <i class="ph-duotone ph-warning-circle"></i>
        </div>
        <h3>Error Loading Test</h3>
        <p class="muted">${escapeHtml(err.message || "Unable to load test")}</p>
        <p class="small" style="margin-top:10px; color: var(--text-muted);">${helpText}</p>
        <button onclick="fetchTests()" class="secondary" style="margin-top:16px"><i class="ph ph-arrows-clockwise"></i> Reload List</button>
      </div>`;
    }
}

function questionDone(questionId) {
    const status = state.answers[questionId];
    return Boolean(status && (status.correct !== undefined || status.revealed || status.choice !== undefined));
}

function goToQuestion(idx) {
    if (state.sessionComplete || state.endedByTimer) return;
    if (!state.questions[idx]) return;
    if (state.currentIndex >= 0 && state.currentIndex < state.questions.length) {
        recordCurrentQuestionTime();
    }
    if (window.sfx) window.sfx.playHover();
    state.currentIndex = idx;
    state.currentSelection = null;
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


    if (existingButtons.length < totalNeeded) {
        for (let i = existingButtons.length; i < totalNeeded; i++) {
            const btn = document.createElement("button");
            btn.className = "qdot";
            questionGrid.appendChild(btn);
        }
    }

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


    Array.from(questionGrid.children).forEach((btn, i) => {
        const q = sortedByNumber[i];
        if (!q) return;
        const idx = idToIndex.get(q.id);
        const status = state.answers[q.id] || {};
        const label = Number.isFinite(q.number) ? q.number : idx + 1;


        if (btn.textContent != label) btn.textContent = label;
        if (btn.title !== `Question ${label}`) btn.title = `Question ${label}`;


        const isActive = q.id === activeId;
        const isCorrect = status.correct === true;
        const isIncorrect = status.correct === false;
        const isAnswered = (status.choice !== undefined || status.revealed) && !isCorrect && !isIncorrect;


        const setClass = (cls, on) => {
            if (on && !btn.classList.contains(cls)) btn.classList.add(cls);
            if (!on && btn.classList.contains(cls)) btn.classList.remove(cls);
        };

        setClass("active", isActive);
        setClass("correct", isCorrect);
        setClass("incorrect", isIncorrect);
        setClass("answered", isAnswered);




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
        return val === null || val === "true";
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


document.addEventListener("keydown", (e) => {

    if (summaryArea && !summaryArea.classList.contains("hidden")) return;
    if (!state.activeTest || state.sessionComplete || state.endedByTimer) return;


    const target = e.target;
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) {
        return;
    }


    if (e.key >= '1' && e.key <= '5') {
        const idx = parseInt(e.key) - 1;
        const question = state.questions[state.currentIndex];
        if (question && idx < question.options.length) {
            selectAnswer(idx);
        }
    }

    const code = e.key.toUpperCase().charCodeAt(0);
    if (code >= 65 && code <= 69) {
        const idx = code - 65;
        const question = state.questions[state.currentIndex];
        if (question && idx < question.options.length) {
            selectAnswer(idx);
        }
    }


    if (e.key === "ArrowRight" || e.key === "Enter") {
        nextQuestion();
    }
    if (e.key === "ArrowLeft") {
        prevQuestion();
    }
    if (e.key === " ") {

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
    const disableOptions = state.sessionComplete || state.endedByTimer || (status && (status.correct !== undefined || status.revealed));
    const controlsDisabled = state.sessionComplete || state.endedByTimer;


    let feedbackText = "Pick an answer.";
    let feedbackClass = "";

    if (status) {
        if (state.mode === "exam") {
            feedbackText = "Answer saved.";
        } else {
            if (status.correct === true) {
                feedbackText = "Correct! Well done.";
                feedbackClass = "correct";
            } else if (status.correct === false) {
                feedbackText = "Incorrect.";
                feedbackClass = "incorrect";
            } else if (status.revealed) {
                feedbackText = "Answer revealed.";
            }
        }
    } else if (state.currentSelection !== null) {
        if (state.mode === "exam") {
            feedbackText = "Press 'Next' to save.";
        } else {
            feedbackText = "Press 'Submit Answer' to check.";
        }
    }

    const isLast = state.currentIndex === state.questions.length - 1;
    const letters = ["A", "B", "C", "D", "E"];

    questionArea.innerHTML = `
    <div class="question-head">
      <div>
        <p class="eyebrow">
            Question ${state.currentIndex + 1} of ${state.questions.length} ${question.number ? `| #${question.number}` : ""} ${state.mode === "exam" ? "(Exam Mode)" : ""}
        </p>
        <div class="question-text">${escapeHtml(tidyText(question.question))}</div>
      </div>
    </div>
    <div class="options">
      ${question.options
            .map(
                (option, idx) => {
                    const isStruck = state.strikes[question.id] && state.strikes[question.id].has(idx);



                    return `<button class="option-btn ${isStruck ? "striked" : ""}" data-idx="${idx}" ${disableOptions ? "disabled" : ""}>
              <span class="kbd-hint">${letters[idx] || (idx + 1)}</span>
              <strong>${String.fromCharCode(65 + idx)}.</strong> ${escapeHtml(tidyText(option))}
              <div class="strike-toggle" onclick="toggleStrike(event, ${idx}, '${question.id}')" title="Strike out answer">
                 <i class="ph ph-eye-slash"></i>
              </div>
            </button>`;
                }
            )
            .join("")}
    </div>
    <div id="feedback" class="feedback ${feedbackClass}" style="display: ${status || state.currentSelection !== null ? 'block' : 'none'}">
      ${feedbackText}
    </div>
    <div id="explanation" class="explanation ${status && (status.revealed || status.correct !== undefined) && state.mode !== "exam" ? "" : "hidden"}"></div>
    <div class="actions">
      <button id="prev-question" class="ghost" ${controlsDisabled ? "disabled" : ""}>
        <i class="ph ph-caret-left"></i> Previous
      </button>
      <button id="next-question" class="secondary" ${controlsDisabled ? "disabled" : ""}>
        ${isLast ? 'Finish' : 'Next'} <i class="ph ph-caret-right" style="margin-left:6px; margin-right:0;"></i>
      </button>

      ${!status
            ? `<button id="submit-answer-btn" class="primary" ${state.currentSelection === null ? "disabled" : ""}>${state.mode === "exam" ? "Save & Next" : "Submit Answer"}</button>`
            : `<button id="show-answer" class="ghost" ${controlsDisabled || state.mode === "exam" ? "disabled" : ""}>
              <i class="ph ph-eye"></i> Show Exp
             </button>`
        }
      
      <button id="submit-quiz-btn" class="ghost" ${controlsDisabled ? "disabled" : ""}>
        <i class="ph ph-flag"></i> End Session
      </button>
    </div>
  `;

    const optionButtons = questionArea.querySelectorAll(".option-btn");
    optionButtons.forEach((btn) => {
        btn.addEventListener("click", (e) => {
            if (e.altKey || e.metaKey || e.ctrlKey) {
                e.preventDefault();
                btn.classList.toggle("striked");
                return;
            }
            const choice = Number(btn.dataset.idx);
            selectAnswer(choice);
        });
    });


    optionButtons.forEach((btn) => {
        const idx = Number(btn.dataset.idx);


        if (status) {

            if (state.mode === "exam" && !state.sessionComplete) {
                // In exam mode, just show selected
                if (status.choice === idx) {
                    btn.classList.add("selected");
                }
            } else {
                if (status.choice === idx) {
                    btn.classList.add(status.correct ? "correct" : "incorrect");
                }
                if (status.revealed && status.correctIndex === idx) {
                    btn.classList.add("revealed", "correct");
                }
            }
        }

        else if (state.currentSelection === idx) {
            btn.classList.add("selected");
        }

        if (state.mode !== "exam" || state.sessionComplete) {
            if (status && status.correctIndex === idx && (status.correct === false || status.revealed)) {
                btn.classList.add("correct-highlight");
            }
        }
    });

    if (status && (status.revealed || status.correct !== undefined)) {
        renderExplanation(question, status);
    }


    const submitAnsBtn = document.getElementById("submit-answer-btn");
    if (submitAnsBtn) {
        submitAnsBtn.addEventListener("click", () => submitCurrentAnswer());
    }

    const showAnswerBtn = document.getElementById("show-answer");
    if (showAnswerBtn) showAnswerBtn.addEventListener("click", () => revealAnswer(question));

    const endSessionBtn = document.getElementById("submit-quiz-btn");
    if (endSessionBtn) endSessionBtn.addEventListener("click", () => {
        if (state.sessionComplete || state.endedByTimer) return;
        showSummary(false);
        if (window.sfx) window.sfx.playClick();
    });

    const nextBtn = document.getElementById("next-question");
    if (nextBtn) nextBtn.addEventListener("click", nextQuestion);
    const prevBtn = document.getElementById("prev-question");
    if (prevBtn) prevBtn.addEventListener("click", prevQuestion);

    updateScore();
    updateProgress();
    renderQuestionGrid();
    persistSession();
}

function selectAnswer(choiceIndex) {
    if (state.sessionComplete || state.endedByTimer) return;
    if (state.currentIndex < 0 || state.currentIndex >= state.questions.length) return;

    const qId = state.questions[state.currentIndex].id;
    if (state.answers[qId]) return;

    if (window.sfx) window.sfx.playClick();
    state.currentSelection = choiceIndex;
    renderQuestionCard();
}

async function submitCurrentAnswer() {
    if (state.currentSelection === null) return;
    if (state.currentIndex < 0 || state.currentIndex >= state.questions.length) return;
    const question = state.questions[state.currentIndex];
    const choiceIndex = state.currentSelection;
    await handleAnswer(question, choiceIndex);
}



// -- Smart Review / Missed Questions Manager --
const MissedMgr = {
    key: "deca-missed-questions",
    getAll() {
        try {
            return JSON.parse(localStorage.getItem(this.key) || "[]");
        } catch { return []; }
    },
    add(testId, questionId) {
        const list = this.getAll();
        if (!list.find(i => i.t === testId && i.q === questionId)) {
            list.push({ t: testId, q: questionId, d: Date.now() });
            localStorage.setItem(this.key, JSON.stringify(list));
        }
    },
    remove(testId, questionId) {
        let list = this.getAll();
        const initLen = list.length;
        list = list.filter(i => !(i.t === testId && i.q === questionId));
        if (list.length !== initLen) {
            localStorage.setItem(this.key, JSON.stringify(list));
        }
    },
    getCount() {
        return this.getAll().length;
    }
};

async function handleAnswer(question, choiceIndex) {
    if (state.sessionComplete || state.endedByTimer) return;
    recordCurrentQuestionTime();

    const questionId = question.id;

    try {
        let isCorrect = false;
        let details = {};

        if (state.isLocalActive) {
            const q = state.questions.find((item) => item.id === question.id);
            if (!q || typeof q.correct_index !== "number") throw new Error("Question data missing");
            isCorrect = choiceIndex === q.correct_index;
            details = { correctIndex: q.correct_index, correctLetter: q.correct_letter, explanation: q.explanation };
        } else {
            // ... server check ...
            const res = await fetch(
                `/api/tests/${encodeURIComponent(state.activeTest.id)}/check/${encodeURIComponent(question.id)}`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    credentials: "same-origin",
                    body: JSON.stringify({ choice: choiceIndex }),
                }
            );
            if (!res.ok) throw new Error("Unable to submit answer");
            const data = await res.json();
            isCorrect = Boolean(data.correct);

            const detailsRes = await fetch(
                `/api/tests/${encodeURIComponent(state.activeTest.id)}/answer/${encodeURIComponent(question.id)}`,
                { credentials: "same-origin" }
            );
            if (detailsRes.ok) {
                details = await detailsRes.json();
            }
        }

        // Smart Review Tracking
        if (!isCorrect) {
            MissedMgr.add(state.activeTest.id, questionId);
        } else {
            MissedMgr.remove(state.activeTest.id, questionId);
        }

        // Check if question is still current to prevent race conditions
        if (state.questions[state.currentIndex]?.id !== questionId) {
            console.warn('Question changed during submission, ignoring result');
            return;
        }

        const existing = state.answers[questionId] || {};
        state.answers[questionId] = {
            ...existing,
            choice: choiceIndex,
            correct: isCorrect,
            ...details,
            revealed: state.mode !== "exam"
        };

        state.currentSelection = null;

        if (window.sfx && state.mode !== "exam") {
            if (isCorrect) window.sfx.playCorrect();
            else window.sfx.playIncorrect();
        }

        recomputeScoreFromAnswers();
        renderQuestionCard();
        persistSession();

        // Auto-advance in exam mode for smoother flow
        if (state.mode === "exam") {
            setTimeout(() => {
                if (state.currentIndex < state.questions.length - 1) {
                    nextQuestion();
                } else {
                    // Last question
                    renderQuestionCard(); // Update UI to show saved state
                }
            }, 200);
        }
    } catch (err) {

        console.error("Submission failed:", err);
        alert("Error submitting answer: " + err.message);
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

    }
}

async function nextQuestion() {
    if (window.sfx) window.sfx.playClick();
    if (state.currentIndex < state.questions.length - 1) {
        goToQuestion(state.currentIndex + 1);
    } else {

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
    recordCurrentQuestionTime();
    state.sessionComplete = true;
    clearInterval(state.timerInterval);
    updateSessionMeta();


    if (!state.resultsPersisted) {
        saveSessionToHistory();
    }
    await persistResults();
    state.resultsPersisted = true;
    state.showAllExplanations = Boolean(forceShowExplanations);


    questionArea.classList.add("hidden");
    summaryArea.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });

    recomputeScoreFromAnswers();


    const total = state.questions.length;
    const attempted = Object.keys(state.answers).length;
    const score = state.score;
    const percent = total > 0 ? Math.round((score / total) * 100) : 0;


    const sScore = document.getElementById("summary-score");
    const sAcc = document.getElementById("summary-accuracy");
    const sTime = document.getElementById("summary-time");
    const summaryList = document.getElementById("summary-list");
    const noteEl = document.getElementById("summary-note");

    if (sScore) sScore.textContent = `${score} / ${total}`;
    if (sAcc) sAcc.textContent = `${percent}% Accuracy`;
    if (sTime) sTime.textContent = `Total time: ${formatMs(state.totalElapsedMs)}`;


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


    const animEnabled = localStorage.getItem("deca-animations-enabled") !== "false";
    if (percent > 60 && animEnabled) {
        triggerConfetti();
        if (window.sfx && window.sfx.enabled) window.sfx.playFanfare();
    }


    const notes = [];
    if (state.endedByTimer) notes.push("Session ended because the timer ran out.");
    if (state.mode === "review_incorrect") notes.push("Reviewing missed questions only.");
    if (noteEl) {
        noteEl.textContent = notes.join(" ");
        noteEl.classList.toggle("hidden", !notes.length);
    }


    if (summaryList) {
        summaryList.innerHTML = "";
        const targets = state.questions;
        try {
            await Promise.all(targets.map((q) => ensureAnswerDetails(q)));
        } catch (err) {
            console.warn("Could not load explanations", err);
        }

        targets.forEach((q, idx) => {
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
            const showExplanation = forceShowExplanations || status.correct === false;
            const timeTaken = state.perQuestionMs[q.id] || 0;
            const explanationHtml =
                showExplanation && status.explanation !== undefined
                    ? `<div class="explanation"><strong>Correct (${status.correct_letter || status.correctLetter || "?"}):</strong> ${escapeHtml(
                        tidyText(status.explanation || "No explanation provided.")
                    )}<br><span class="muted">Time: ${formatMs(timeTaken)}</span></div>`
                    : `<div class="explanation muted">Time: ${formatMs(timeTaken)}</div>`;

            const item = document.createElement("div");
            item.className = "summary-item";
            item.innerHTML = `
        <strong>#${q.number || idx + 1}:</strong> ${escapeHtml(tidyText(q.question))}<br>
        <span class="${tone}">${label}</span>
        ${explanationHtml}
      `;
            summaryList.appendChild(item);
        });
    }


    setTimeout(() => {
        renderPerformanceChart();
    }, 100);
}

function renderExplanation(question, status) {
    const el = document.getElementById("explanation");
    if (!el || !status.explanation) return;
    el.innerHTML = `
    <strong>Correct Answer: ${status.correct_letter || status.correctLetter}</strong><br>
    ${escapeHtml(tidyText(status.explanation))}
  `;
    el.classList.remove("hidden");
}





function openSettings(fromHash = false) {
    const overlay = document.getElementById("settings-overlay");
    if (!overlay) return;
    settingsOpenedFromHash = Boolean(fromHash);
    initSettingsLogic();
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

        setTimeout(clearHash, 80);
    } else {
        clearHash();
    }
}


window.addEventListener("popstate", (event) => {
    const overlay = document.getElementById("settings-overlay");
    if (!overlay) return;
    if (event.state && event.state.view === "settings") {
        initSettingsLogic();
        overlay.classList.remove("hidden");
    } else {
        closeSettings({ fromPop: true });
        closeCredits();
    }
});


function openCredits() {
    const overlay = document.getElementById("credits-overlay");
    if (!overlay) return;
    overlay.classList.remove("hidden");
}

function closeCredits() {
    const overlay = document.getElementById("credits-overlay");
    if (!overlay) return;
    overlay.classList.add("hidden");
}


function initSettingsLogic() {
    const themeButtons = Array.from(document.querySelectorAll("[data-theme-option]"));
    const currentTheme = window.Theme ? window.Theme.get() : "light";


    themeButtons.forEach((btn) => {
        const t = btn.dataset.theme;
        const isActive = t === currentTheme;
        btn.classList.toggle("active", isActive);
    });



    themeButtons.forEach((btn) => {
        btn.onclick = () => {
            const t = btn.dataset.theme;
            if (window.Theme) window.Theme.apply(t);

            themeButtons.forEach(b => b.classList.toggle("active", b.dataset.theme === t));
        };
    });


    setupToggle("random-order-check", "deca-random-order", false);
    setupToggle("animations-toggle", "deca-animations-enabled", true);
    setupToggle("disable-timer-toggle", "deca-timer-disabled", false, (val) => {
        if (state.timerInterval || state.sessionStart) {
            updateTimerDisplay();
        }
    });
    setupToggle("perf-mode-toggle", "deca-perf-mode", true, (val) => {
        document.documentElement.classList.toggle("perf-mode", val);
    });
}


function setupToggle(id, key, defaultVal, onChange) {
    const el = document.getElementById(id);
    if (!el) return;
    const stored = localStorage.getItem(key);
    el.checked = stored === null ? defaultVal : (stored === "true");
    el.onchange = (e) => {
        localStorage.setItem(key, e.target.checked);
        if (typeof onChange === "function") onChange(e.target.checked);
    };
}



async function startSmartReview() {
    if (!state.tests.length && !localTests.size) await fetchTests();
    const missed = MissedMgr.getAll();
    if (!missed.length) {
        alert("No missed questions found!");
        renderTestList();
        return;
    }

    testListEl.innerHTML = '<p class="muted">Generating review session...</p>';

    const byTest = {};
    missed.forEach(item => {
        if (!byTest[item.t]) byTest[item.t] = [];
        byTest[item.t].push(item.q);
    });

    const combinedQuestions = [];

    for (const testId of Object.keys(byTest)) {
        const targetIds = new Set(byTest[testId]);

        try {
            const res = await fetch(`/api/tests/${encodeURIComponent(testId)}/start_quiz`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ count: 9999, mode: "regular" }),
            });

            if (res.ok) {
                const data = await res.json();
                if (data.questions && Array.isArray(data.questions)) {
                    data.questions.forEach(q => {
                        if (targetIds.has(q.id)) {
                            q._originalTestName = data.name || data.test?.name;
                            combinedQuestions.push(q);
                        }
                    });
                }
            } else {
                const cached = localTests.get(testId);
                if (cached && cached.questions && Array.isArray(cached.questions)) {
                    cached.questions.forEach(q => {
                        if (targetIds.has(q.id)) {
                            q._originalTestName = cached.name;
                            combinedQuestions.push(q);
                        }
                    });
                }
            }
        } catch (e) {
            console.warn(`Failed to load test ${testId}`, e);
            const cached = localTests.get(testId);
            if (cached && cached.questions && Array.isArray(cached.questions)) {
                cached.questions.forEach(q => {
                    if (targetIds.has(q.id)) {
                        q._originalTestName = cached.name;
                        combinedQuestions.push(q);
                    }
                });
            }
        }
    }

    if (!combinedQuestions.length) {
        alert("Could not load any missed questions.");
        renderTestList();
        return;
    }

    state.activeTest = {
        id: "smart-review",
        name: "Weakness Review",
        description: `Reviewing ${combinedQuestions.length} missed questions.`
    };
    state.mode = "review_incorrect";
    state.questions = shuffleQuestions(combinedQuestions);
    state.currentIndex = 0;
    state.score = 0;
    state.answers = {};
    state.strikes = {};
    state.currentSelection = null;
    state.timeLimitMs = 0;
    state.timeRemainingMs = 0;
    state.sessionStart = Date.now();
    state.questionStart = Date.now();
    state.sessionComplete = false;
    state.endedByTimer = false;
    state.resultsPersisted = false;
    state.timerHidden = false;

    activeTestName.textContent = state.activeTest.name;
    questionArea.classList.remove("hidden");
    summaryArea.classList.add("hidden");
    testListEl.innerHTML = "";

    startSessionTimer();
    renderQuestionCard();
    updateScore();
    updateProgress();
    updateSessionMeta();
}

document.addEventListener("DOMContentLoaded", () => {





    try {
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);








        }


    } catch (e) { }

    hydrateLocalTests();
    hydrateHiddenTests();

    for (const key of localTests.keys()) {
        if (typeof key === 'string' && key.startsWith('u-')) {
            localTests.delete(key);
        }
    }
    persistLocalTests();

    if (localTests.size) {
        state.tests = localTestSummaries();
        if (typeof renderTestList === "function") {
            renderTestList();
        }
    }

    if (reloadBtn) reloadBtn.addEventListener("click", fetchTests);
    if (toggleTimerBtn) toggleTimerBtn.addEventListener("click", toggleTimer);
    if (questionGridToggle) questionGridToggle.addEventListener("click", toggleQuestionGrid);
    if (restartBtn) restartBtn.addEventListener("click", () => window.location.reload());
    if (backToTestsBtn) backToTestsBtn.addEventListener("click", () => window.location.reload());
    if (uploadBtn) uploadBtn.addEventListener("click", handleUpload);
    if (uploadInput) {
        uploadInput.addEventListener("change", () => {
            setUploadStatus(uploadInput.files && uploadInput.files[0] ? uploadInput.files[0].name : "");
        });
    }


    const backSumm = document.getElementById("back-to-home-summ");
    if (backSumm) backSumm.onclick = () => {
        resetState();
        window.scrollTo({ top: 0, behavior: "smooth" });
    };
    const showAllBtn = document.getElementById("show-all-explanations");
    if (showAllBtn) {
        showAllBtn.addEventListener("click", () => showSummary(true));
    }
    if (reviewIncorrectBtn) {
        reviewIncorrectBtn.addEventListener("click", () => {
            if (!state.activeTest) return;
            startTest(
                state.activeTest.id,
                0,
                "review_incorrect",
                state.lastTimeLimitMinutes ?? DEFAULT_TIME_LIMIT_MINUTES
            );
        });
    }

    if (window.Theme) window.Theme.init();

    const storedPerf = localStorage.getItem("deca-perf-mode");
    const perfPref = storedPerf === null ? true : storedPerf === "true";
    if (storedPerf === null) {
        localStorage.setItem("deca-perf-mode", "true");
    }
    document.documentElement.classList.toggle("perf-mode", perfPref);

    if (window.location.hash === "#/settings") {
        openSettings(true);
    }


    try {
        localStorage.removeItem(SESSION_KEY);
        resetState();
    } catch (e) { }





});
