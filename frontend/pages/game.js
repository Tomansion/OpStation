/* The game. Station canvas, one notification button, the penalty total, the
 * station clock and an elapsed timer. Nothing else. */

import { api, connect, fmt } from '../lib/api.js';
import { closeModal, isOpen, showItem, shake } from '../lib/modal.js';
import * as sfx from '../lib/sfx.js';
import { mountStation, stationData } from '../lib/station.js';

export async function game(root, { navigate, params }) {
  sfx.preload();
  const sessionId = params[0];
  const [station, config] = await Promise.all([stationData(), api.config()]);

  let snapshot;
  try {
    snapshot = await api.session(sessionId);
  } catch (exc) {
    root.innerHTML = `<div class="panel alert"><h2>Session unavailable</h2>
      <div class="body note">${exc.message}. Sessions do not survive a backend
      restart. <a href="/" data-nav>Back to the start</a></div></div>`;
    return;
  }

  root.innerHTML = `
    <div class="cols">
      <div class="col grow">
        <div class="panel"><div class="body" style="padding:4px">
          <div data-station></div>
        </div></div>
      </div>
      <div class="col">
        <button id="notify" data-notify disabled>NOTHING WAITING</button>
        <div class="readouts">
          <div class="readout"><div class="k">PENALTIES</div><div class="v" data-penalties>0</div></div>
          <div class="readout"><div class="k">ELAPSED</div><div class="v" data-elapsed>00:00</div></div>
          <div class="readout"><div class="k">STATION TIME</div><div class="v" data-wall>--:--:--</div></div>
        </div>
        <div class="panel" style="margin-top:12px">
          <h2 data-phase>On shift</h2>
          <div class="body note" data-hint>
            Doors are yours. Messages arrive on the panel above.
          </div>
        </div>
      </div>
    </div>`;

  const el = {
    notify: root.querySelector('[data-notify]'),
    penalties: root.querySelector('[data-penalties]'),
    elapsed: root.querySelector('[data-elapsed]'),
    wall: root.querySelector('[data-wall]'),
    phase: root.querySelector('[data-phase]'),
    hint: root.querySelector('[data-hint]'),
  };

  const view = mountStation(root.querySelector('[data-station]'), station,
    id => socket.send({ type: 'toggle_door', door: id }));

  let state = snapshot;
  // A signature rather than just the uid: the modal must be redrawn when a
  // challenge goes from unanswered to answered, and at no other time. Redrawing
  // on every state push would restart the audio of a radio message, which is
  // the one thing the game exists to prevent.
  let shownSignature = null;

  const ctx = {
    scenarioId: snapshot.scenario_id,
    dontKnow: config.dont_know,
    onAcknowledge: uid => socket.send({ type: 'acknowledge', uid }),
    onAnswer: (uid, option_id) => socket.send({ type: 'answer_challenge', uid, option_id }),
  };

  // The player's only other control. Opens the oldest queued item; the server
  // decides what that is and what may be revealed about it.
  el.notify.onclick = () => socket.send({ type: 'open_notification' });

  const socket = connect(sessionId, payload => {
    if (payload.type === 'shake') { shake(); return; }
    if (payload.type === 'confirmed') { showConfirmation(payload.text); return; }
    if (payload.type === 'opened' || payload.type === 'answered') return; // state follows
    if (payload.type === 'error') {
      el.hint.textContent = payload.message;
      return;
    }
    state = { ...state, ...payload };
    render();
  });

  // Set on the first render so the very first snapshot never fires a door or
  // notification cue for state the player did not just cause.
  let knownDoors = null;
  let knownWaiting = null;

  function render() {
    const doors = state.doors || {};
    if (knownDoors) {
      for (const [id, next] of Object.entries(doors)) {
        if (knownDoors[id] && knownDoors[id] !== next) {
          sfx.play(next === 'open' ? 'door_open' : 'door_close', { volume: 0.5 });
        }
      }
    }
    knownDoors = doors;
    view.setDoorStates(doors);
    el.penalties.textContent = state.penalties ?? 0;
    el.penalties.className = 'v' + (state.penalties ? ' bad' : '');

    const waiting = state.pending_count || 0;
    if (knownWaiting !== null && waiting > knownWaiting) sfx.play('notification', { volume: 0.6 });
    knownWaiting = waiting;
    const front = state.front;
    el.notify.disabled = waiting === 0;
    el.notify.className = waiting ? 'waiting' : '';
    el.notify.innerHTML = waiting
      ? `OPEN NOTIFICATION${config.show_pending_count && waiting > 1
          ? `<span class="count">${waiting} WAITING</span>` : ''}`
      : 'NOTHING WAITING';

    // The modal follows the server's view of the front of the queue, so a
    // refresh or a reconnect puts the player back where they were.
    if (front && front.opened) {
      const signature = `${front.uid}:${front.answered === true}`;
      if (signature !== shownSignature) {
        shownSignature = signature;
        showItem(front, ctx);
      }
    } else if (isOpen()) {
      closeModal();
      shownSignature = null;
    }

    if (state.phase === 'debrief') {
      el.phase.textContent = 'Debrief — untimed';
      el.hint.textContent = 'The shift is over. Nothing can fail now. '
        + 'Answer the last questions from memory.';
    } else if (state.phase === 'complete') {
      socket.close();
      navigate(`/summary/${sessionId}`);
    }
  }

  const timer = setInterval(() => {
    el.wall.textContent = fmt.wall();
    if (state.phase === 'running') {
      // Interpolate between server ticks so the counter does not stutter; the
      // server's value always wins on the next state push.
      state.elapsed = (state.elapsed || 0) + 0.25;
      el.elapsed.textContent = fmt.clock(state.elapsed);
    }
  }, 250);

  render();
  return () => { clearInterval(timer); socket.close(); closeModal(); };
}

/* A quiet, non-blocking confirmation for an instruction the player already
 * carried out right away -- unlike everything else in the queue, this does
 * not need acknowledging and does not compete with real traffic. */
function showConfirmation(text) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = `CONFIRMED — ${text}`;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 400);
  }, 2600);
}
