/* Admin. The only place ground truth is visible: the bank with its validator
 * verdicts, session history with the expected door trace beside the actual one,
 * and the generate button. No authentication anywhere, by design. */

import { api, fmt } from '../lib/api.js';

export async function admin(root, { navigate }) {
  const [status, scenarios, sessions] = await Promise.all([
    api.adminStatus(), api.scenarios(), api.adminSessions(),
  ]);

  root.innerHTML = `
    <div class="cols">
      <div class="col grow">
        <div class="panel"><h2>Scenario bank — ${status.bank.total} entries,
          ${status.bank.playable} playable</h2>
          <div class="body">${bankTable(scenarios)}</div></div>
        <div class="panel"><h2>Sessions</h2>
          <div class="body">${sessionTable(sessions)}</div></div>
      </div>
      <div class="col">
        <div class="panel"><h2>Generate a scenario</h2><div class="body">
          <label for="dur">Duration (minutes)</label>
          <input id="dur" type="number" value="27" min="20" max="30">
          <label for="thr">Incident threads</label>
          <input id="thr" type="number" value="5" min="4" max="7">
          <label for="fin">Finale</label>
          <select id="fin">
            <option value="">random</option>
            <option value="invasion">invaders attack</option>
            <option value="hull_breach">hull breach</option>
            <option value="reactor_emergency">reactor emergency</option>
            <option value="station_contamination">station-wide contamination</option>
          </select>
          <label for="thm">Theme hint (optional)</label>
          <input id="thm" placeholder="e.g. a supply ship is overdue">
          <label><input type="checkbox" id="aud" checked style="width:auto"> render audio</label>
          <button class="primary big" data-generate style="margin-top:8px">Generate</button>
          <div class="mono-block" data-job style="margin-top:8px;display:none"></div>
        </div></div>
        <div class="panel"><h2>Running</h2><div class="body">
          <div class="note">Station <strong>${status.station_version}</strong><br>
          ${status.bank.invalid} invalid · ${status.bank.stale_tunables} validated against
          different tunables</div>
          ${status.active_sessions.length
            ? `<table><tr><th>Session</th><th>Phase</th><th>Elapsed</th><th>Pen</th></tr>
               ${status.active_sessions.map(s => `<tr>
                 <td><a href="/admin/sessions/${s.session_id}" data-nav>${s.participant_name || s.session_id}</a></td>
                 <td>${s.phase}</td><td>${fmt.clock(s.elapsed)}</td>
                 <td>${s.penalties}</td></tr>`).join('')}</table>`
            : '<div class="note">No live sessions.</div>'}
        </div></div>
        <div class="panel"><h2>Voices</h2><div class="body"><table>
          ${Object.entries(status.voices).map(([type, v]) => `<tr>
            <td>${type}</td><td>${v.voice}${v.post_filter ? ` + ${v.post_filter}` : ''}</td>
          </tr>`).join('')}</table></div></div>
      </div>
    </div>`;

  root.querySelector('[data-generate]').onclick = async ev => {
    const button = ev.currentTarget;
    const log = root.querySelector('[data-job]');
    button.disabled = true;
    log.style.display = 'block';
    log.textContent = 'starting ...';
    const { job_id } = await api.generate({
      duration_seconds: Number(root.querySelector('#dur').value) * 60,
      threads: Number(root.querySelector('#thr').value),
      finale: root.querySelector('#fin').value,
      theme: root.querySelector('#thm').value,
      render_audio: root.querySelector('#aud').checked,
    });
    const poll = setInterval(async () => {
      const job = await api.job(job_id);
      log.textContent = job.progress.map(p => `${p.stage.padEnd(12)}${p.message}`).join('\n')
        + (job.error ? `\n\nFAILED: ${job.error}` : '')
        + (job.result ? `\n\n${job.result.scenario_id}: ${job.result.summary}` : '');
      log.scrollTop = log.scrollHeight;
      if (job.state !== 'running') {
        clearInterval(poll);
        button.disabled = false;
      }
    }, 1500);
  };
}

function bankTable(scenarios) {
  if (!scenarios.length) return '<div class="note">The bank is empty.</div>';
  return `<table>
    <tr><th>Scenario</th><th>Name</th><th>Min</th><th>Msg</th><th>Thr</th>
        <th>Audio</th><th>Verdict</th></tr>
    ${scenarios.map(s => `<tr>
      <td><a href="/admin/scenarios/${s.scenario_id}" data-nav>${s.scenario_id}</a></td>
      <td>${esc(s.name)}</td>
      <td>${Math.round(s.duration_seconds / 60)}</td>
      <td>${s.messages}</td><td>${s.threads}</td>
      <td>${s.radio_messages === 0 ? '—'
            : s.has_audio ? '<span class="tag ok">yes</span>'
            : '<span class="tag warn">missing</span>'}</td>
      <td>${s.valid ? '<span class="tag ok">valid</span>'
            : `<span class="tag no">${esc((s.failed_rules || []).join(' ')) || 'invalid'}</span>`}</td>
    </tr>`).join('')}
  </table>`;
}

function sessionTable(sessions) {
  if (!sessions.length) return '<div class="note">No sessions yet.</div>';
  return `<table>
    <tr><th>Session</th><th>Participant</th><th>Scenario</th><th>Phase</th>
        <th>Elapsed</th><th>Pen</th></tr>
    ${sessions.slice().reverse().map(s => `<tr>
      <td><a href="/admin/sessions/${s.session_id}" data-nav>${s.session_id}</a></td>
      <td>${esc(s.participant_name)}</td><td>${esc(s.scenario_name || s.scenario_id)}</td>
      <td>${s.phase}</td><td>${fmt.clock(s.elapsed || 0)}</td><td>${s.penalties}</td>
    </tr>`).join('')}
  </table>`;
}

/* -------------------------------------------------------- one scenario */

export async function adminScenario(root, { params }) {
  const data = await api.adminScenario(params[0]);
  const sc = data.scenario;
  const report = data.validation || {};
  const actors = Object.fromEntries(sc.actors.map(a => [a.id, a]));
  const groups = Object.fromEntries(sc.task_groups.map(g => [g.id, g]));

  root.innerHTML = `
    <div class="panel ${report.ok ? '' : 'alert'}">
      <h2>${esc(sc.name)} — ${sc.scenario_id} — ${report.ok ? 'valid' : 'INVALID'}</h2>
      <div class="body note">
        ${sc.messages.length} messages · ${sc.tasks.length} tasks ·
        ${sc.threads.filter(t => t.grade === 'ordinary' || t.grade === 'finale').length}
        incident threads · ${sc.threads.filter(t => t.grade === 'everyday').length}
        everyday exchanges · station ${sc.station_version} ·
        ${sc.generator.model || 'unknown model'} · ${sc.generator.attempts} repair attempts
        ${(report.errors || []).length
          ? `<div class="mono-block" style="margin-top:8px">${
              report.errors.map(e => `${e.rule} ${e.where || ''}: ${esc(e.message)}`).join('\n')
            }</div>` : ''}
      </div>
    </div>

    <div class="cols">
      <div class="col grow">
        <div class="panel"><h2>Timeline — transcripts visible here only</h2>
          <div class="body"><table>
          <tr><th>At</th><th>Id</th><th>Actor</th><th>Ch</th><th>Kind</th><th>Text</th></tr>
          ${sc.messages.map(m => `<tr>
            <td>${fmt.clock(m.at)}</td><td>${m.id}</td>
            <td>${esc((actors[m.actor_id] || {}).type || '')}</td>
            <td>${m.channel === 'radio'
                  ? `<a href="/api/scenarios/${sc.scenario_id}/${m.audio}" target="_blank">radio</a>`
                  : 'text'}</td>
            <td>${esc(m.kind)}${(m.cancels || []).length
                  ? `<br><span class="tag warn">${esc(m.retraction_style || '')}</span>` : ''}</td>
            <td>${esc(m.text)}</td></tr>`).join('')}
          </table></div></div>

        <div class="panel"><h2>Obligations</h2><div class="body"><table>
          <tr><th>Task</th><th>Group</th><th>At</th><th>Hold</th><th>Requires</th>
              <th>Derived from</th></tr>
          ${sc.tasks.map(t => `<tr>
            <td>${t.id}</td>
            <td>${esc((groups[t.group_id] || {}).label || t.group_id)}</td>
            <td>${fmt.clock(t.at)}</td><td>${t.hold}s</td>
            <td>${Object.entries(t.require).map(([d, s]) =>
                  `<span class="tag ${s === 'open' ? 'ok' : 'no'}">${d} ${s}</span>`).join(' ')}</td>
            <td>${t.derived_from ? esc(t.derived_from.isolation_target)
                  + (t.derived_from.include_hangar_doors ? ' +pressure' : '') : ''}</td>
          </tr>`).join('')}
        </table></div></div>
      </div>
      <div class="col">
        <div class="panel"><h2>Perfect-player trace</h2><div class="body">
          <div class="note">The minimum toggles that satisfy every obligation, at
          the latest safe moment. This is what proves the scenario is
          solvable.</div>
          <div class="mono-block">${
            ((report.simulation || {}).toggles || [])
              .map(t => `${fmt.clock(t.at).padEnd(7)}${t.door.padEnd(5)}${t.to.padEnd(8)}${t.because}`)
              .join('\n') || 'no toggles required'}</div>
        </div></div>
        <div class="panel"><h2>Questions</h2><div class="body">
          ${[...sc.challenges, ...sc.debrief_challenges].map(c => `
            <div style="border-bottom:1px solid var(--rule);padding:6px 0">
              <div class="note">${c.slot} · ${c.kind} · ${fmt.clock(c.at)}</div>
              <div>${esc(c.prompt)}</div>
              ${c.options.map(o => `<div class="note ${o.correct ? '' : ''}">
                ${o.correct ? '<span class="tag ok">correct</span>' : '·'} ${esc(o.text)}</div>`).join('')}
              <div class="note">${esc(c.explanation)}</div>
            </div>`).join('')}
        </div></div>
        <div class="panel"><h2>Generation log</h2>
          <div class="body"><div class="mono-block">${esc(data.generation_log)}</div></div></div>
      </div>
    </div>`;
}

/* --------------------------------------------------------- one session */

export async function adminSession(root, { params, navigate }) {
  const data = await api.adminSession(params[0]);
  const s = data.session;
  const sc = data.scenario;
  const groups = Object.fromEntries(sc.task_groups.map(g => [g.id, g]));
  const actors = Object.fromEntries(sc.actors.map(a => [a.id, a]));
  const messages = Object.fromEntries(sc.messages.map(m => [m.id, m]));

  const actual = s.events.filter(e => e.kind === 'door_toggled');

  root.innerHTML = `
    <div class="panel"><h2>${esc(s.participant_name)} — ${s.session_id}</h2>
      <div class="body note">
        ${esc(s.scenario_name)} · ${s.phase} · ${fmt.clock(s.elapsed)} of
        ${fmt.clock(s.duration_seconds)} · ${s.penalties} penalties
        <button data-delete style="float:right">Delete</button>
      </div></div>

    <div class="cols">
      <div class="col grow">
        <div class="panel"><h2>Obligations</h2><div class="body"><table>
          <tr><th>Task</th><th>Obligation</th><th>Asked by</th><th>At</th>
              <th>Outcome</th><th>Door</th></tr>
          ${s.tasks.map(t => `<tr class="${t.state === 'failed' ? 'bad' : ''}">
            <td>${t.task_id}</td>
            <td>${esc((groups[t.group_id] || {}).label || t.group_id)}</td>
            <td>${esc((actors[t.requested_by] || {}).type || '')}</td>
            <td>${fmt.clock(t.at)}</td>
            <td>${t.state}${t.resolved_at != null ? ` ${fmt.clock(t.resolved_at)}` : ''}</td>
            <td>${esc(t.failed_door || '')}</td></tr>`).join('')}
        </table></div></div>

        <div class="panel"><h2>Every event</h2><div class="body">
          <div class="mono-block">${s.events.map(e =>
            `${fmt.clock(e.at).padEnd(7)}${e.kind.padEnd(28)}${
              esc(JSON.stringify(Object.fromEntries(
                Object.entries(e).filter(([k]) => k !== 'at' && k !== 'kind'))))}`
            ).join('\n')}</div>
        </div></div>
      </div>
      <div class="col">
        <div class="panel"><h2>Doors: expected vs actual</h2><div class="body">
          <div class="note">Left is the perfect-player trace stored with the
          scenario. Right is what this player did.</div>
          <table><tr><th>Expected</th><th>Actual</th></tr><tr>
            <td><div class="mono-block">${data.expected_trace.map(t =>
              `${fmt.clock(t.at).padEnd(7)}${t.door.padEnd(5)}${t.to}`).join('\n')}</div></td>
            <td><div class="mono-block">${actual.map(e =>
              `${fmt.clock(e.at).padEnd(7)}${e.door.padEnd(5)}${e.state}`).join('\n')}</div></td>
          </tr></table>
        </div></div>
        <div class="panel"><h2>Queue</h2><div class="body"><table>
          <tr><th>Item</th><th>Arrived</th><th>Opened</th><th>Acked</th><th>Answer</th></tr>
          ${s.queue.map(q => `<tr class="${q.withdrawn_at != null ? 'bad' : ''}">
            <td>${q.ref_id} <span class="note">${q.kind}</span></td>
            <td>${fmt.clock(q.delivered_at)}</td>
            <td>${q.opened_at != null ? fmt.clock(q.opened_at)
                  : q.withdrawn_at != null ? 'expired unread' : '—'}</td>
            <td>${q.acknowledged_at != null ? fmt.clock(q.acknowledged_at) : '—'}</td>
            <td>${esc(q.answer_outcome || '')}</td></tr>`).join('')}
        </table></div></div>
      </div>
    </div>`;

  root.querySelector('[data-delete]').onclick = async () => {
    await api.deleteSession(s.session_id);
    navigate('/admin');
  };
}

function esc(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML;
}
