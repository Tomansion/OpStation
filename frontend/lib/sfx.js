/* Short cues and ambience. Plain HTMLAudioElement, not the Web Audio graph --
 * these are one-shots and loops, not something that needs analysis.
 *
 * Every player has a `stop()`. Nothing here is guaranteed to stop itself:
 * modal.js is responsible for tracking what it starts and stopping it when the
 * modal closes, so a radio message never keeps talking in the background. */

const FILES = {
  door_open: '/assets/sfx/door_open.wav',
  door_close: '/assets/sfx/door_close.wav',
  notification: '/assets/sfx/notification.wav',
  radio_start: '/assets/sfx/radio_start.wav',
  radio_end: '/assets/sfx/radio_end.wav',
  radio_noise: '/assets/sfx/radio_noise.wav',
  writing: '/assets/sfx/writing.wav',
};

const templates = new Map();

function template(name) {
  if (!templates.has(name)) {
    const audio = new Audio(FILES[name]);
    audio.preload = 'auto';
    templates.set(name, audio);
  }
  return templates.get(name);
}

/* Warms the browser's cache so the first play of each cue has no latency.
 * Safe to call before any user gesture -- it only loads, it does not play. */
export function preload() {
  for (const name of Object.keys(FILES)) template(name);
}

/* Fire-and-forget. Returns a stop() handle in case the caller wants to cut it
 * short, but nothing is required to call it. */
export function play(name, { volume = 1 } = {}) {
  const node = template(name).cloneNode();
  node.volume = volume;
  node.play().catch(() => { /* blocked or not yet primed -- silently skip */ });
  return { stop: () => node.pause(), node };
}

/* A looping cue -- radio static, the writing clatter. `randomStart` avoids the
 * same few seconds of loop being audible at the start of every transmission.
 * `fadeInSeconds` ramps from silence so a background loop never starts with a
 * click. Returns { stop(), fadeOut(seconds) }. */
export function loop(name, { volume = 1, fadeInSeconds = 0, randomStart = false } = {}) {
  const node = template(name).cloneNode();
  node.loop = true;
  node.volume = fadeInSeconds > 0 ? 0 : volume;

  if (randomStart) {
    const seek = () => {
      if (node.duration && isFinite(node.duration)) {
        node.currentTime = Math.random() * node.duration;
      }
    };
    if (node.readyState >= 1) seek();
    else node.addEventListener('loadedmetadata', seek, { once: true });
  }

  node.play().catch(() => { /* blocked -- the loop just never starts */ });

  let raf = null;
  const cancelRaf = () => { if (raf) { cancelAnimationFrame(raf); raf = null; } };

  if (fadeInSeconds > 0) {
    const t0 = performance.now();
    const step = now => {
      // The first rAF timestamp can land fractionally before `t0` was
      // captured, which without the lower clamp produces a small negative
      // volume -- and HTMLMediaElement.volume throws outside [0, 1] rather
      // than clamping it itself.
      const frac = Math.min(1, Math.max(0, (now - t0) / (fadeInSeconds * 1000)));
      node.volume = frac * volume;
      if (frac < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }

  return {
    stop() { cancelRaf(); node.pause(); },
    fadeOut(seconds = 0.4) {
      cancelRaf();
      const from = node.volume;
      const t0 = performance.now();
      const step = now => {
        const frac = Math.min(1, Math.max(0, (now - t0) / (seconds * 1000)));
        node.volume = from * (1 - frac);
        if (frac < 1) raf = requestAnimationFrame(step);
        else node.pause();
      };
      raf = requestAnimationFrame(step);
    },
  };
}
