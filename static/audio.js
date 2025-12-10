/**
 * Synthetic Audio System
 * Uses Web Audio API to generate sounds without external files.
 */
class SoundFX {
    constructor() {
        this.ctx = null;
        this.enabled = localStorage.getItem("deca-sound") !== "false";
        this.vol = 0.15;
    }

    init() {
        if (!this.ctx) {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (Ctx) this.ctx = new Ctx();
        }
        if (this.ctx && this.ctx.state === "suspended") {
            this.ctx.resume().catch(() => { });
        }
    }

    toggle(force) {
        this.enabled = force !== undefined ? force : !this.enabled;
        localStorage.setItem("deca-sound", this.enabled);
        return this.enabled;
    }

    _osc(freq, type, duration, startTime = 0, vol = this.vol) {
        if (!this.ctx || !this.enabled) return;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        osc.type = type;
        osc.frequency.setValueAtTime(freq, this.ctx.currentTime + startTime);

        gain.gain.setValueAtTime(vol, this.ctx.currentTime + startTime);
        gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + startTime + duration);

        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.start(this.ctx.currentTime + startTime);
        osc.stop(this.ctx.currentTime + startTime + duration);
    }

    playHover() {
        this.init();
        // High tick
        this._osc(800, "sine", 0.03, 0, 0.05);
    }

    playClick() {
        this.init();
        // Soft interaction
        this._osc(600, "sine", 0.05, 0, 0.08);
        this._osc(1200, "triangle", 0.02, 0, 0.02);
    }
    
    playSelect() {
        // Alias for click/select actions to avoid missing method errors
        this.playClick();
    }

    playCorrect() {
        this.init();
        // Major chord arpeggio
        this._osc(523.25, "sine", 0.3, 0); // C5
        this._osc(659.25, "sine", 0.3, 0.05); // E5
        this._osc(783.99, "sine", 0.4, 0.1); // G5
    }

    playIncorrect() {
        this.init();
        // Dissonant low thud
        this._osc(150, "sawtooth", 0.2, 0, 0.1);
        this._osc(140, "sawtooth", 0.2, 0.05, 0.1);
    }

    playFanfare() {
        this.init();
        // Victory sequence
        const now = 0;
        const root = 523.25; // C
        [1, 1.25, 1.5, 2].forEach((ratio, i) => {
            this._osc(root * ratio, "square", 0.4, i * 0.1, 0.1);
        });
        this._osc(root * 2, "square", 1.0, 0.4, 0.1);
    }
}

window.sfx = new SoundFX();
