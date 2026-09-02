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
import { LANGUAGES, LANGUAGE_NAMES, strings } from '../lib/i18n.js';
import { legend, mountStation, stationData } from '../lib/station.js';

export async function home(root, { navigate, audio }) {
  const [station, scenarios, config] = await Promise.all([
    stationData(), api.scenarios(), api.config(),
  ]);

  // A session is monolingual (spec 16), so the choice made here is the whole
  // page's language, not just a filter -- the instructions above the map and
  // the scenario picker below it change together.
  let lang = 'en';

  function render() {
    const s = strings(lang);
    root.innerHTML = `
      <div class="cols">
        <div class="col grow">
          <div class="panel">
            <h2>${s.stationHeader(station.version)}</h2>
            <div class="body"><div data-station></div><div data-legend></div></div>
          </div>
        </div>
        <div class="col">
          <div class="panel">
            <h2>${s.beginShift}
              <span data-lang style="float:right;font-weight:normal"></span>
            </h2>
            <div class="body">
              <label for="who">${s.participant}</label>
              <input id="who" placeholder="${s.participantPlaceholder}" autocomplete="off">
              <label for="pick">${s.scenario}</label>
              <select id="pick"></select>
              <div data-detail class="note" style="margin:8px 0"></div>
              <button class="primary big" data-start>${s.startShift}</button>
              <div data-error class="note" style="color:var(--closed);margin-top:8px"></div>
            </div>
          </div>
          <div class="panel">
            <h2>${s.beforeYouStart}</h2>
            <div class="body note">
              ${s.instructions.map(p => `<p>${p}</p>`).join('')}
            </div>
          </div>
        </div>
      </div>`;

    const view = mountStation(root.querySelector('[data-station]'), station, id => {
      view.setDoorState(id, view.getDoorState(id) === 'open' ? 'closed' : 'open');
    });
    root.querySelector('[data-legend]').appendChild(legend(s));

    const langHost = root.querySelector('[data-lang]');
    for (const code of LANGUAGES) {
      const btn = document.createElement('button');
      btn.textContent = LANGUAGE_NAMES[code];
      btn.className = code === lang ? 'primary' : '';
      btn.style.marginLeft = '4px';
      btn.onclick = () => { lang = code; render(); };
      langHost.appendChild(btn);
    }

    const pick = root.querySelector('#pick');
    const detail = root.querySelector('[data-detail]');
    const startButton = root.querySelector('[data-start]');
    const error = root.querySelector('[data-error]');

    // Scenarios are generated whole in one language, text and audio alike
    // (spec 16), so a session in this language can only ever play one of these.
    const playable = scenarios.filter(sc => sc.playable && sc.language === lang);
    const anyPlayable = scenarios.filter(sc => sc.playable);
    if (!playable.length) {
      pick.innerHTML = `<option value="">${s.bankEmpty}</option>`;
      startButton.disabled = true;
      detail.innerHTML = anyPlayable.length
        ? `${s.someUnplayable(scenarios.length)}`
          + `<a href="/admin" data-nav>${s.openAdmin}</a>${s.toSeeWhy}`
        : `${s.noScenariosYet}<a href="/admin" data-nav>${s.generateOne}</a>.`;
    } else {
      pick.innerHTML = playable.map(sc => `<option value="${sc.scenario_id}">${s.scenarioOption(sc)}</option>`).join('');
    }

    function describe() {
      const chosen = playable.find(sc => sc.scenario_id === pick.value);
      if (!chosen) return;
      detail.textContent = s.describe(chosen);
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
        error.textContent = s.soundFailed(exc.message);
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

  render();
}
