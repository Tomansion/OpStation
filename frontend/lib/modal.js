/* The notification modal: message, failure notice, or Keeper challenge.
 *
 * Three rules from the spec drive everything here:
 *   - the modal can only be dismissed with ACKNOWLEDGE, and shakes otherwise;
 *   - a radio message is audio only — no transcript, ever, in any circumstance;
 *   - a challenge must be answered, but the station canvas behind it stays live
 *     and the clock never stops.
 */

import * as sfx from './sfx.js';

let veil = null;
//: Every sound and timer started while a modal is open, so closing it --
//: whether the player acknowledges, or the next item simply replaces it --
//: always leaves nothing playing behind it. Radio is audio-only and heard
//: once; a background loop that outlives its modal would quietly break that.
let tracked = [];

function track(stoppable) {
  tracked.push(stoppable);
  return stoppable;
}

export function closeModal() {
  for (const t of tracked) { try { t.stop(); } catch { /* already stopped */ } }
  tracked = [];
  if (veil) { veil.remove(); veil = null; }
}

export function isOpen() { return Boolean(veil); }

export function shake() {
  const modal = veil && veil.querySelector('.modal');
  if (!modal) return;
  modal.classList.remove('shake');
  void modal.offsetWidth;      // force a reflow so the animation restarts
  modal.classList.add('shake');
}

/* ctx: { scenarioId, dontKnow, onAcknowledge, onAnswer } */
export function showItem(item, ctx) {
  closeModal();
  veil = document.createElement('div');
  veil.id = 'veil';

  const alert = item.kind === 'failure_notice';
  const modal = document.createElement('div');
  modal.className = `modal${alert ? ' alert' : ''}`;

  const who = alert
    ? 'STATION ALERT'
    : (item.actor ? `${item.actor.name.toUpperCase()} — ${item.actor.type.toUpperCase()}` : 'STATION');
  const channel = item.kind === 'challenge'
    ? 'INCOMING QUERY'
    : (item.channel === 'radio' ? 'RADIO — AUDIO ONLY' : 'TEXT');

  modal.innerHTML = `
    <div class="head"><span>${who}</span><span class="chan">${channel}</span></div>
    <div class="content">
      ${item.actor && !alert
        ? `<img class="portrait" alt="" src="/assets/portraits/${item.actor.portrait}">`
        : ''}
      <div class="body" data-body></div>
    </div>
    <div class="foot" data-foot></div>`;

  const body = modal.querySelector('[data-body]');
  const foot = modal.querySelector('[data-foot]');

  if (item.kind === 'challenge') renderChallenge(item, ctx, body, foot);
  else renderMessage(item, ctx, body, foot);

  // Anything other than ACKNOWLEDGE shakes it.
  veil.addEventListener('mousedown', ev => { if (ev.target === veil) shake(); });
  document.addEventListener('keydown', onKey, true);
  veil.appendChild(modal);
  document.body.appendChild(veil);
  return veil;
}

function onKey(ev) {
  if (!veil) { document.removeEventListener('keydown', onKey, true); return; }
  if (ev.key === 'Escape') { ev.preventDefault(); shake(); }
}

//: Bars for the radio "speaking" animation. Pure CSS keyframes, toggled with a
//: class -- guaranteed to animate on every browser, unlike a Web Audio
//: analyser, which can silently fail to hook up and leave the panel looking
//: dead while the audio plays fine.
const WAVE_BARS = 14;

function barsHtml() {
  let out = '';
  for (let i = 0; i < WAVE_BARS; i++) {
    const duration = (0.55 + Math.random() * 0.5).toFixed(2);
    const delay = (Math.random() * 0.4).toFixed(2);
    out += `<span style="animation-duration:${duration}s;animation-delay:${delay}s"></span>`;
  }
  return out;
}

function renderMessage(item, ctx, body, foot) {
  if (item.channel === 'radio') {
    body.innerHTML = `
      <div class="radio">
        <div class="bars" data-bars>${barsHtml()}</div>
        <div class="state" data-state>OPENING CHANNEL</div>
      </div>`;
    playRadio(item, ctx, body);
  } else {
    body.textContent = '';
    typeText(body, item.text || '');
  }
  const ack = document.createElement('button');
  ack.className = 'primary';
  ack.textContent = 'Acknowledge';
  ack.onclick = () => ctx.onAcknowledge(item.uid);
  foot.appendChild(ack);
}

//: Milliseconds per character of the on-screen typewriter effect.
const TYPE_SPEED_MS = 16;

/* Text messages are received character by character rather than dumped on
 * screen whole, with a soft typing clatter under it -- a text order arriving
 * has its own sense of "coming in live", the same way radio does. */
function typeText(body, text) {
  if (!text) return;
  const caret = document.createElement('span');
  caret.className = 'caret';
  body.appendChild(caret);
  if (!text.trim()) { caret.remove(); return; }

  const writing = track(sfx.loop('writing', { volume: 0.4, fadeInSeconds: 0.3 }));
  let i = 0;
  const timer = setInterval(() => {
    if (!veil || !veil.contains(body)) { clearInterval(timer); writing.stop(); return; }
    caret.before(document.createTextNode(text[i]));
    i += 1;
    if (i >= text.length) {
      clearInterval(timer);
      writing.fadeOut(0.25);
      caret.remove();
      sfx.play('radio_end', { volume: 0.5 });
    }
  }, TYPE_SPEED_MS);
  track({ stop: () => clearInterval(timer) });
}

/* Audio only, played once. A reconnect returns the modal to the queue but the
 * server has already marked the audio spent, so it cannot be heard twice.
 * Bookended by a channel-open and channel-close cue, with quiet static
 * underneath the voice -- three separate assets, sequenced rather than mixed
 * blind, so the words are never competing with the effects. */
function playRadio(item, ctx, body) {
  const bars = body.querySelector('[data-bars]');
  const state = body.querySelector('[data-state]');
  const total = item.audio_duration ? `${item.audio_duration.toFixed(1)}s` : '';

  if (!item.audio) {
    state.textContent = 'AUDIO UNAVAILABLE — THIS SESSION IS VOID';
    return;
  }
  if (item.audio_played) {
    state.textContent = `TRANSMISSION ENDED — ${total}`;
    state.classList.add('done');
    return;
  }

  const noise = track(sfx.loop('radio_noise', {
    volume: 0.06, fadeInSeconds: 0.6, randomStart: true,
  }));

  let started = false;
  const beginVoice = () => {
    if (started) return;
    started = true;
    if (!veil || !veil.contains(body)) { noise.stop(); return; }

    bars.classList.add('playing');
    state.textContent = total ? `RECEIVING — ${total}` : 'RECEIVING';

    const audio = new Audio(`/api/scenarios/${ctx.scenarioId}/${item.audio}`);
    track({ stop: () => audio.pause() });
    audio.play().catch(() => {
      state.textContent = 'AUDIO BLOCKED — THIS SESSION IS VOID';
    });
    audio.ontimeupdate = () => {
      if (total) state.textContent = `RECEIVING — ${audio.currentTime.toFixed(1)}s / ${total}`;
    };
    audio.onended = () => {
      bars.classList.remove('playing');
      state.textContent = `TRANSMISSION ENDED — ${total}`;
      state.classList.add('done');
      noise.fadeOut(0.5);
      sfx.play('radio_end', { volume: 0.6 });
    };
  };

  const startCue = track(sfx.play('radio_start', { volume: 0.6 }));
  startCue.node.addEventListener('ended', beginVoice, { once: true });
  // Belt and braces: if the cue is blocked or its duration is unreliable, the
  // voice still has to start.
  setTimeout(beginVoice, 1800);
}

function renderChallenge(item, ctx, body, foot) {
  body.innerHTML = `<div data-prompt style="margin-bottom:10px"></div>
                    <div class="options" data-options></div>
                    <div data-verdict></div>`;
  body.querySelector('[data-prompt]').textContent = item.prompt || '';
  const options = body.querySelector('[data-options]');
  const verdict = body.querySelector('[data-verdict]');

  // The fifth option is supplied here and never appears in the scenario JSON.
  const all = [...(item.options || []), { id: ctx.dontKnow.id, text: ctx.dontKnow.text }];

  for (const option of all) {
    const button = document.createElement('button');
    button.textContent = option.text;
    if (option.id === ctx.dontKnow.id) button.classList.add('dunno');
    button.disabled = item.answered;
    button.dataset.optionId = option.id;
    button.onclick = () => ctx.onAnswer(item.uid, option.id);
    options.appendChild(button);
  }

  if (item.answered) {
    for (const button of options.querySelectorAll('button')) {
      const id = button.dataset.optionId;
      if (id === item.correct_option_id) button.classList.add('correct');
      else if (id === item.chosen) button.classList.add('wrong');
    }
    const label = { correct: 'CORRECT', wrong: 'WRONG', dont_know: 'NOT KNOWN' }[item.outcome];
    verdict.className = 'verdict';
    verdict.innerHTML =
      `<span class="${item.outcome === 'correct' ? 'ok' : 'no'}">${label}</span> — ` +
      `${escapeHtml(item.explanation || '')}`;
    const ack = document.createElement('button');
    ack.className = 'primary';
    ack.textContent = 'Acknowledge';
    ack.onclick = () => ctx.onAcknowledge(item.uid);
    foot.appendChild(ack);
  } else {
    foot.innerHTML = '<span class="note">AN ANSWER IS REQUIRED. THE STATION IS STILL LIVE '
                   + 'BEHIND THIS PANEL AND THE CLOCK IS STILL RUNNING.</span>';
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
