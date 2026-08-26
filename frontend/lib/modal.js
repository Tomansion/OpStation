/* The notification modal: message, failure notice, or Keeper challenge.
 *
 * Three rules from the spec drive everything here:
 *   - the modal can only be dismissed with ACKNOWLEDGE, and shakes otherwise;
 *   - a radio message is audio only — no transcript, ever, in any circumstance;
 *   - a challenge must be answered, but the station canvas behind it stays live
 *     and the clock never stops.
 */

let veil = null;

export function closeModal() {
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

function renderMessage(item, ctx, body, foot) {
  if (item.channel === 'radio') {
    body.innerHTML = `
      <div class="radio">
        <canvas data-wave width="600" height="64"></canvas>
        <div class="state" data-state>OPENING CHANNEL</div>
      </div>`;
    playRadio(item, ctx, body);
  } else {
    body.textContent = item.text || '';
  }
  const ack = document.createElement('button');
  ack.className = 'primary';
  ack.textContent = 'Acknowledge';
  ack.onclick = () => ctx.onAcknowledge(item.uid);
  foot.appendChild(ack);
}

/* Audio only, played once. A reconnect returns the modal to the queue but the
 * server has already marked the audio spent, so it cannot be heard twice. */
function playRadio(item, ctx, body) {
  const canvas = body.querySelector('[data-wave]');
  const state = body.querySelector('[data-state]');
  const total = item.audio_duration ? `${item.audio_duration.toFixed(1)}s` : '';

  if (!item.audio) {
    state.textContent = 'AUDIO UNAVAILABLE — THIS SESSION IS VOID';
    drawIdle(canvas);
    return;
  }
  if (item.audio_played) {
    state.textContent = `TRANSMISSION ENDED — ${total}`;
    state.classList.add('done');
    drawIdle(canvas);
    return;
  }

  // Draw something before the first animation frame, so the panel is never a
  // blank box while the audio is still loading.
  drawIdle(canvas);
  state.textContent = total ? `RECEIVING — ${total}` : 'RECEIVING';

  const audio = new Audio(`/api/scenarios/${ctx.scenarioId}/${item.audio}`);
  let analyser = null;
  try {
    const ac = ctx.audioContext;
    const source = ac.createMediaElementSource(audio);
    analyser = ac.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(ac.destination);
  } catch {
    // No analyser: the audio still plays, the bars just do not react to it.
  }

  audio.play().catch(() => {
    state.textContent = 'AUDIO BLOCKED — THIS SESSION IS VOID';
  });
  audio.onended = () => {
    state.textContent = `TRANSMISSION ENDED — ${total}`;
    state.classList.add('done');
  };

  const bins = analyser ? new Uint8Array(analyser.frequencyBinCount) : null;
  (function frame() {
    if (!veil || !veil.contains(canvas)) return;
    if (!audio.ended) {
      const played = audio.currentTime || 0;
      state.textContent = `RECEIVING — ${played.toFixed(1)}s / ${total}`;
      if (analyser) { analyser.getByteFrequencyData(bins); drawWave(canvas, bins); }
      else drawBusy(canvas, played);
    }
    requestAnimationFrame(frame);
  })();
}

function drawWave(canvas, bins) {
  const ctx = canvas.getContext('2d');
  const { width: w, height: h } = canvas;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#00e5ff';
  const bars = 48;
  const bw = w / bars;
  for (let i = 0; i < bars; i++) {
    const v = bins[Math.floor((i / bars) * bins.length)] / 255;
    const bh = Math.max(2, v * (h - 6));
    ctx.fillRect(i * bw + 1, (h - bh) / 2, bw - 2, bh);
  }
}

/* A dead channel: a baseline with tick marks, so the panel never looks broken. */
function drawIdle(canvas) {
  const ctx = canvas.getContext('2d');
  const { width: w, height: h } = canvas;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#2a2e30';
  ctx.fillRect(0, h / 2 - 1, w, 2);
  for (let x = 0; x < w; x += 24) ctx.fillRect(x, h / 2 - 4, 1, 8);
}

/* Fallback when no analyser is available: bars that move with the clock, so the
 * player can see the transmission is running without it pretending to be a
 * reading of the actual audio. */
function drawBusy(canvas, seconds) {
  const ctx = canvas.getContext('2d');
  const { width: w, height: h } = canvas;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#00e5ff';
  const bars = 48;
  const bw = w / bars;
  for (let i = 0; i < bars; i++) {
    const v = 0.35 + 0.3 * Math.sin(seconds * 6 + i * 0.7) + 0.2 * Math.sin(i * 2.3);
    const bh = Math.max(2, Math.abs(v) * (h - 8));
    ctx.fillRect(i * bw + 1, (h - bh) / 2, bw - 2, bh);
  }
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
