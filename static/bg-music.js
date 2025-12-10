const BG_MUSIC_FILE = "/static/BK - ICY (Official Music Video) - BK.mp3";
const AUDIO_PREF_KEY = "deca-audio-enabled";
const AUDIO_TIME_KEY = "deca-audio-time";
const AUDIO_TS_KEY = "deca-audio-timestamp";
const RESUME_WINDOW_MS = 300000;

let bgPlayer = null;
let bgPlaying = false;
let userPrefersAudio = true;
let audioUnlocked = false;

function initBgMusic() {
    bgPlayer = new Audio(BG_MUSIC_FILE);
    bgPlayer.loop = true;
    bgPlayer.volume = 0.3;

    userPrefersAudio = localStorage.getItem(AUDIO_PREF_KEY) !== "false";
    const savedTime = parseFloat(localStorage.getItem(AUDIO_TIME_KEY) || "0");
    const savedStamp = parseInt(localStorage.getItem(AUDIO_TS_KEY) || "0", 10);

    // If saved less than 5 mins ago, resume
    if (Date.now() - savedStamp < RESUME_WINDOW_MS) {
        bgPlayer.currentTime = savedTime;
    }

    // Save progress frequently
    setInterval(() => {
        if (bgPlayer && !bgPlayer.paused) {
            localStorage.setItem(AUDIO_TIME_KEY, bgPlayer.currentTime);
            localStorage.setItem(AUDIO_TS_KEY, Date.now());
        }
    }, 1000);

    updateBgUi();
}

function attemptPlayBgMusic() {
    if (!bgPlayer || !userPrefersAudio) {
        bgPlaying = false;
        updateBgUi();
        return Promise.resolve(false);
    }
    return bgPlayer.play().then(() => {
        bgPlaying = true;
        updateBgUi();
        return true;
    }).catch((e) => {
        console.warn("Audio start failed", e);
        bgPlaying = false;
        updateBgUi();
        return false;
    });
}

function toggleBgMusic(forceState) {
    if (!bgPlayer) return false;
    const newPreference = forceState !== undefined ? forceState : !userPrefersAudio;
    userPrefersAudio = newPreference;
    localStorage.setItem(AUDIO_PREF_KEY, String(newPreference));

    if (!newPreference) {
        bgPlayer.pause();
        bgPlaying = false;
        updateBgUi();
        return false;
    }

    if (!audioUnlocked) {
        bgPlaying = false;
        updateBgUi();
        return false;
    }

    return attemptPlayBgMusic();
}

function updateBgUi() {
    // Index/Nav Button
    const btn = document.getElementById("audio-toggle-btn");
    if (btn) {
        btn.innerHTML = userPrefersAudio
            ? '<i class="ph-fill ph-speaker-high"></i>'
            : '<i class="ph ph-speaker-slash"></i>';
        btn.classList.toggle("active", userPrefersAudio);
    }

    // Settings Toggle
    const settingToggle = document.getElementById("global-audio-toggle");
    if (settingToggle) {
        settingToggle.checked = userPrefersAudio;
    }
}

function unlockAudioAndPlay() {
    audioUnlocked = true;
    if (window.sfx && window.sfx.ctx && typeof window.sfx.ctx.resume === "function") {
        window.sfx.ctx.resume().catch(() => { });
    }
    return attemptPlayBgMusic();
}

function handleOverlayUnlock() {
    return unlockAudioAndPlay();
}

// Save on exit
window.addEventListener("beforeunload", () => {
    if (bgPlayer) {
        localStorage.setItem(AUDIO_TIME_KEY, bgPlayer.currentTime);
        localStorage.setItem(AUDIO_TS_KEY, Date.now());
    }
});

document.addEventListener("DOMContentLoaded", () => {
    initBgMusic();

    // Unlock via Overlay
    const overlay = document.getElementById("unlock-overlay");
    if (overlay) {
        overlay.addEventListener("click", () => {
            overlay.classList.add("hidden");
            // Let transition finish before removing
            setTimeout(() => {
                if (overlay.parentElement) overlay.remove();
            }, 600);
            handleOverlayUnlock();
        }, { once: true });
    }

    const btn = document.getElementById("audio-toggle-btn");
    if (btn) btn.addEventListener("click", () => toggleBgMusic());

    const settingsToggle = document.getElementById("global-audio-toggle");
    if (settingsToggle) {
        settingsToggle.addEventListener("change", (e) => toggleBgMusic(e.target.checked));
    }

    // expose for other scripts if needed
    window.toggleBgMusic = toggleBgMusic;
    window.unlockAudioAndPlay = unlockAudioAndPlay;
});
