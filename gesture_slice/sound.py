"""
sound.py - optional sound effects.

Pygame is used *only* as an audio mixer (Tkinter has no sound support).  The
sounds are synthesised with NumPy at start-up, so no audio files are needed.
If pygame is not installed, or there is no audio device, every method simply
does nothing and the game stays silent.
"""

import os

import numpy as np

RATE = 22050


def _envelope(n, attack=0.01, release=0.2):
    env = np.ones(n, np.float32)
    a, r = int(RATE * attack), int(RATE * release)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[-r:] *= np.linspace(1, 0, r) ** 2
    return env


def _swoosh():
    n = int(RATE * 0.16)
    rng = np.random.default_rng(1)
    noise = rng.standard_normal(n).astype(np.float32)
    # crude band-pass: difference of two moving averages, sweeping upwards
    smooth = np.convolve(noise, np.ones(6) / 6, mode="same")
    tone = np.sin(2 * np.pi * np.cumsum(np.linspace(500, 1600, n)) / RATE)
    return (smooth * 0.6 + tone * 0.15) * _envelope(n, 0.01, 0.12)


def _splat():
    n = int(RATE * 0.22)
    rng = np.random.default_rng(2)
    noise = np.convolve(rng.standard_normal(n), np.ones(18) / 18, mode="same").astype(np.float32)
    thump = np.sin(2 * np.pi * np.cumsum(np.linspace(220, 70, n)) / RATE)
    return (noise * 1.6 + thump * 0.5) * _envelope(n, 0.002, 0.18)


def _boom():
    n = int(RATE * 0.7)
    rng = np.random.default_rng(3)
    noise = np.convolve(rng.standard_normal(n), np.ones(40) / 40, mode="same").astype(np.float32)
    rumble = np.sin(2 * np.pi * np.cumsum(np.linspace(110, 30, n)) / RATE)
    return (noise * 3.0 + rumble * 0.8) * _envelope(n, 0.003, 0.6)


def _chime(freqs=(660, 880, 1320), dur=0.32):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    wave = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * 6) for f in freqs) / len(freqs)
    return wave.astype(np.float32) * _envelope(n, 0.005, 0.1)


def _blip(freq=520, dur=0.08):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    return (np.sign(np.sin(2 * np.pi * freq * t)) * 0.25).astype(np.float32) * _envelope(n, 0.002, 0.05)


def _game_over():
    parts = [_chime((f, f * 1.5), 0.25) for f in (523, 415, 330)]
    return np.concatenate(parts)


GENERATORS = {
    "swoosh": (_swoosh, 0.35),
    "splat": (_splat, 0.5),
    "boom": (_boom, 0.7),
    "combo": (lambda: _chime((784, 988, 1175)), 0.45),
    "level": (lambda: _chime((523, 659, 784, 1047), 0.5), 0.45),
    "click": (_blip, 0.3),
    "tick": (lambda: _blip(880, 0.06), 0.3),
    "gameover": (_game_over, 0.5),
}


class SoundManager:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.available = False
        self.error = None
        self.sounds = {}
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            pygame.mixer.pre_init(RATE, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
            for name, (gen, volume) in GENERATORS.items():
                wave = gen()
                wave = wave / (np.max(np.abs(wave)) + 1e-6) * volume
                pcm = (wave * 32767).astype(np.int16)
                stereo = np.ascontiguousarray(np.column_stack([pcm, pcm]))
                self.sounds[name] = pygame.mixer.Sound(buffer=stereo.tobytes())
            self._pygame = pygame
            self.available = True
        except Exception as exc:  # ImportError, no audio device, ...
            self.error = f"Sound disabled ({exc.__class__.__name__})"

    def play(self, name):
        if self.enabled and self.available and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass

    def shutdown(self):
        if self.available:
            try:
                self._pygame.mixer.quit()
            except Exception:
                pass

