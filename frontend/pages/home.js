/* The home page. Carries the same station canvas the game uses, fully operable,
 * with no clock and nothing recorded.
 *
 * This exists because the first minutes of a session are the worst possible
 * place to learn an interface: once START SHIFT is pressed the clock runs and
 * never stops, so fumbling with the controls contaminates the very thing being
 * measured. There is deliberately no sector highlighting and no isolation-target
 * list here — those belong to the printed handbook, not to an interactive
 * lookup handed over during setup. */

import { api } from '../lib/api.js';
import { legend, mountStation, stationData } from '../lib/station.js';

export async function home(root, { navigate, audio }) {
  const [station, scenarios, config] = await Promise.all([
    stationData(), api.scenarios(), api.config(),
  ]);

  root.innerHTML = `
    <div class="cols">
      <div class="col grow">
        <div class="panel">
          <h2>Station — ${station.version} — practice mode, nothing is recorded</h2>
          <div class="body"><div data-station></div><div data-legend></div></div>
        </div>
      </div>
      <div class="col">
        <div class="panel">
          <h2>Begin a shift</h2>
          <div class="body">
            <label for="who">Participant</label>
            <input id="who" placeholder="name or code" autocomplete="off">
            <label for="pick">Scenario</label>
            <select id="pick"></select>
            <div data-detail class="note" style="margin:8px 0"></div>
            <button class="primary big" data-start>Start shift</button>
            <div data-error class="note" style="color:var(--closed);margin-top:8px"></div>
          </div>
        </div>
        <div class="panel">
          <h2>Before you start</h2>
          <div class="body note">
            <p><strong>Click a door to open or close it.</strong> Green is open, red is
            closed. Try every one now — once the shift starts the clock runs and
            never pauses.</p>
            <p><strong>Two places have no door of their own.</strong> Find them. They
            are drawn as a break in the wall rather than a bar.</p>
            <p><strong>Work through the printed sector cards against this map.</strong>
            Which doors bound a sector is the one thing you cannot read off the
            station, and it is not what the session is measuring.</p>
            <p><strong>You get each message once.</strong> No history, no replay, no
            pause. Radio messages are spoken and have no transcript. Pen and
            paper are allowed.</p>
            <p>Pressing <strong>Start shift</strong> resets every door to its standard
            position and turns the sound on.</p>
          </div>
        </div>
      </div>
    </div>`;

  const view = mountStation(root.querySelector('[data-station]'), station, id => {
    view.setDoorState(id, view.getDoorState(id) === 'open' ? 'closed' : 'open');
  });
  root.querySelector('[data-legend]').appendChild(legend());

  const pick = root.querySelector('#pick');
  const detail = root.querySelector('[data-detail]');
  const startButton = root.querySelector('[data-start]');
  const error = root.querySelector('[data-error]');

  const playable = scenarios.filter(s => s.playable);
  if (!playable.length) {
    pick.innerHTML = '<option value="">— the bank is empty —</option>';
    startButton.disabled = true;
    detail.innerHTML = scenarios.length
      ? `${scenarios.length} scenario(s) in the bank, none playable. `
        + `<a href="/admin" data-nav>Open admin</a> to see why.`
      : `No scenarios yet. <a href="/admin" data-nav>Generate one</a>.`;
  } else {
    pick.innerHTML = playable
      .map(s => `<option value="${s.scenario_id}">${s.name} — ${Math.round(s.duration_seconds / 60)} min</option>`)
      .join('');
  }

  function describe() {
    const chosen = playable.find(s => s.scenario_id === pick.value);
    if (!chosen) return;
    detail.textContent =
      `${chosen.messages} messages, ${chosen.threads} threads, `
      + `${chosen.radio_messages} spoken. Station ${chosen.station_version}.`
      + (chosen.tunables_match ? '' : ' Validated against different difficulty settings.');
  }
  pick.onchange = describe;
  describe();

  startButton.onclick = async () => {
    error.textContent = '';
    startButton.disabled = true;
    try {
      // The gesture that primes audio. If priming fails, refuse to start rather
      // than beginning a session that will have to be thrown away.
      await audio.prime();
    } catch (exc) {
      error.textContent = `Sound could not be started (${exc.message}). `
        + 'A session without audio is void, so it will not begin. '
        + 'Check the browser is not muted and try again.';
      startButton.disabled = false;
      return;
    }
    try {
      const { session_id } = await api.createSession(
        root.querySelector('#who').value, pick.value,
      );
      navigate(`/game/${session_id}`);
    } catch (exc) {
      error.textContent = exc.message;
      startButton.disabled = false;
    }
  };
}
