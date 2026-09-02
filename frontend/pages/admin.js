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
          <label for="lang">Language</label>
          <select id="lang">
            <option value="en">English</option>
            <option value="fr">French</option>
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
        <div class="panel"><h2>Voices</h2><div class="body">
          ${Object.entries(status.voices).map(([lang, assignment]) => `
            <div class="note" style="margin-top:${lang === 'en' ? '0' : '8px'}">${lang.toUpperCase()}</div>
            <table>${Object.entries(assignment).map(([type, v]) => `<tr>
              <td>${type}</td>
              <td>${v.voice}${v.speaker_id != null ? ` #${v.speaker_id}` : ''}${v.post_filter ? ` + ${v.post_filter}` : ''}</td>
            </tr>`).join('')}</table>`).join('')}
        </div></div>
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
      language: root.querySelector('#lang').value,
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
    <tr><th>Scenario</th><th>Name</th><th>Lang</th><th>Min</th><th>Msg</th><th>Thr</th>
        <th>Audio</th><th>Verdict</th></tr>
    ${scenarios.map(s => `<tr>
      <td><a href="/admin/scenarios/${s.scenario_id}" data-nav>${s.scenario_id}</a></td>
      <td>${esc(s.name)}</td>
      <td>${(s.language || 'en').toUpperCase()}</td>
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
  const threads = Object.fromEntries(sc.threads.map(t => [t.id, t]));

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

    <div class="panel"><h2>Traffic over time</h2><div class="body">
      <div class="note">One dot per message, coloured and grouped by thread. A
      diamond is a question. The bars below count messages per 4 minutes, so a
      pacing problem — a dead second half, a pile-up early — is visible at a
      glance.</div>
      <div style="overflow-x:auto">${timelineChart(sc)}</div>
      <div style="overflow-x:auto;margin-top:6px">${densityChart(sc)}</div>
    </div></div>

    <div class="panel"><h2>Door obligations over time</h2><div class="body">
      ${doorChartWithNote(sc)}
    </div></div>

    <div class="panel"><h2>Threads — ${sc.threads.length}</h2><div class="body">
      ${threadsBody(sc, actors)}
    </div></div>

    <div class="cols">
      <div class="col grow">
        <div class="panel"><h2>Timeline — transcripts visible here only</h2>
          <div class="body"><table>
          <tr><th>At</th><th>Id</th><th>Thread</th><th>Actor</th><th>Ch</th><th>Kind</th><th>Text</th></tr>
          ${sc.messages.map(m => `<tr>
            <td>${fmt.clock(m.at)}</td><td>${m.id}</td>
            <td>${threadTag(threads[m.thread_id], m.thread_id)}</td>
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
              <div class="note">${c.slot} · ${c.kind} · ${fmt.clock(c.at)} ·
                ${threadTag(threads[c.thread_id], c.thread_id)}</div>
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

/* ------------------------------------------------------- threads and traffic */

//: A stable colour per thread id, so the same thread reads as the same colour
//: across the timeline table, the scatter chart and the thread panel.
function threadColor(threadId) {
  let h = 0;
  for (const c of String(threadId)) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h}, 60%, 60%)`;
}

function threadTag(thread, fallbackId) {
  const label = thread ? thread.title : fallbackId;
  const color = threadColor(fallbackId);
  return `<span class="tag" style="border-color:${color};color:${color}">${esc(label)}</span>`;
}

function threadsBody(sc, actors) {
  if (!sc.threads.length) return '<div class="note">No threads.</div>';
  const byThread = {};
  for (const m of sc.messages) (byThread[m.thread_id] ??= []).push(m);
  return sc.threads.map(t => {
    const color = threadColor(t.id);
    const msgs = byThread[t.id] || [];
    return `<div style="border-bottom:1px solid var(--rule);padding:8px 0;margin-bottom:4px">
      <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
        <span class="tag" style="border-color:${color};color:${color}">${esc(t.grade)}</span>
        <strong>${esc(t.title)}</strong>
        <span class="note">phase ${t.phase_span[0]}–${t.phase_span[1]} · ${msgs.length} messages</span>
      </div>
      <div class="note" style="margin:4px 0">${esc(t.debrief_summary)}</div>
      <div class="mono-block" style="max-height:160px">${
        msgs.map(m => `${fmt.clock(m.at).padEnd(7)}${((actors[m.actor_id] || {}).type || '').padEnd(14)}${
          m.kind.padEnd(18)}${m.text.slice(0, 100)}`).join('\n')
        || 'no messages landed'
      }</div>
    </div>`;
  }).join('');
}

function timelineChart(sc) {
  const threads = sc.threads;
  if (!threads.length) return '<div class="note">No threads.</div>';
  const lane = Object.fromEntries(threads.map((t, i) => [t.id, i]));
  const duration = sc.duration_seconds;
  const W = 900, laneH = 20, padL = 150, padR = 10, padT = 6;
  const H = padT + threads.length * laneH + 4;
  const x = t => padL + (Math.max(0, Math.min(t, duration)) / duration) * (W - padL - padR);

  const rows = threads.map((t, i) => {
    const y = padT + i * laneH;
    const color = threadColor(t.id);
    return `<text x="4" y="${(y + laneH - 6).toFixed(1)}" font-size="9" fill="${color}">${
      esc(t.title.length > 22 ? t.title.slice(0, 21) + '…' : t.title)}</text>
      <line x1="${padL}" x2="${W - padR}" y1="${(y + laneH).toFixed(1)}" y2="${(y + laneH).toFixed(1)}"
        stroke="var(--rule)" stroke-width="1"/>`;
  }).join('');

  const dots = sc.messages.map(m => {
    const i = lane[m.thread_id];
    if (i === undefined) return '';
    const cy = padT + i * laneH + laneH / 2;
    return `<circle cx="${x(m.at).toFixed(1)}" cy="${cy.toFixed(1)}" r="2.6" fill="${threadColor(m.thread_id)}">
      <title>${esc(`${fmt.clock(m.at)} ${m.kind}: ${m.text.slice(0, 70)}`)}</title></circle>`;
  }).join('');

  const diamonds = [...sc.challenges, ...sc.debrief_challenges].map(c => {
    const i = lane[c.thread_id];
    const cy = i === undefined ? padT + laneH / 2 : padT + i * laneH + laneH / 2;
    const cx = x(c.at);
    return `<rect x="${(cx - 4).toFixed(1)}" y="${(cy - 4).toFixed(1)}" width="8" height="8"
      transform="rotate(45 ${cx.toFixed(1)} ${cy.toFixed(1)})" fill="#000" stroke="#fff" stroke-width="1.3">
      <title>${esc(`${fmt.clock(c.at)} question (${c.kind}): ${c.prompt.slice(0, 70)}`)}</title></rect>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="min-width:640px">
    <rect x="0" y="0" width="${W}" height="${H}" fill="#000"/>${rows}${dots}${diamonds}</svg>`;
}

function densityChart(sc) {
  const BUCKET = 240; // 4 minutes, per the request that motivated this chart
  const buckets = Math.max(1, Math.ceil(sc.duration_seconds / BUCKET));
  const counts = new Array(buckets).fill(0);
  for (const m of sc.messages) counts[Math.min(buckets - 1, Math.floor(m.at / BUCKET))] += 1;
  const W = 900, H = 70, padL = 4, padR = 10, padB = 14;
  const max = Math.max(1, ...counts);
  const bw = (W - padL - padR) / buckets;
  const bars = counts.map((c, i) => {
    const h = (c / max) * (H - padB - 6);
    const x1 = padL + i * bw;
    const y1 = H - padB - h;
    return `<rect x="${x1.toFixed(1)}" y="${y1.toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}"
      height="${Math.max(1, h).toFixed(1)}" fill="var(--cyan)">
      <title>${esc(`${fmt.clock(i * BUCKET)}–${fmt.clock(Math.min(sc.duration_seconds, (i + 1) * BUCKET))}: ${c} messages`)}</title>
    </rect>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="min-width:640px">
    <rect x="0" y="0" width="${W}" height="${H}" fill="#000"/>
    <line x1="${padL}" x2="${W - padR}" y1="${H - padB}" y2="${H - padB}" stroke="var(--rule)"/>${bars}</svg>`;
}

//: D before H, then numeric, so D2 sorts before D13 and hangar doors trail
//: the internal ones -- matches the order the station brief and the map use.
function doorSortKey(id) {
  const m = /^([DH])(\d+)$/.exec(id);
  return m ? [m[1] === 'D' ? 0 : 1, Number(m[2])] : [2, 0];
}

function doorChartWithNote(sc) {
  const { svg, conflicts, doors } = doorTimelineChart(sc);
  if (!doors.length) return '<div class="note">No obligations touch a door.</div>';
  const note = conflicts > 0
    ? `<div class="note" style="color:var(--closed)">${conflicts} door(s) show two real
       obligations demanding opposite states at overlapping times — that would make the
       scenario unsolvable and should not happen; the scheduler is supposed to rule this
       out. Everything else here (a request with no bar under it) is a designed
       conflicting request, not a bug: it has no task, so refusing it costs nothing.</div>`
    : `<div class="note">Green is a window where a real obligation requires the door
       open, red where one requires it closed. No door shows two obligations
       overlapping in opposite states, so every "close this now" the player hears is
       consistent with every other live obligation. A message that asks for a door
       state with nothing shown here is exactly the conflicting-request pattern
       (spec 6.5): plausible, and free to refuse.</div>`;
  return `${note}<div style="overflow-x:auto;margin-top:6px">${svg}</div>`;
}

function doorTimelineChart(sc) {
  const intervals = {};
  for (const t of sc.tasks) {
    for (const [door, state] of Object.entries(t.require)) {
      (intervals[door] ??= []).push({ at: t.at, hold: t.hold, state, task_id: t.id });
    }
  }
  const doors = Object.keys(intervals).sort((a, b) => {
    const ka = doorSortKey(a), kb = doorSortKey(b);
    return ka[0] - kb[0] || ka[1] - kb[1];
  });
  const duration = sc.duration_seconds;
  const W = 900, laneH = 18, padL = 34, padR = 10, padT = 4;
  const H = padT + doors.length * laneH + 4;
  const x = t => padL + (Math.max(0, Math.min(t, duration)) / duration) * (W - padL - padR);

  let conflicts = 0;
  const rows = doors.map((door, i) => {
    const y = padT + i * laneH;
    const segs = intervals[door];
    let warn = false;
    for (let a = 0; a < segs.length; a++) {
      for (let b = a + 1; b < segs.length; b++) {
        const A = segs[a], B = segs[b];
        if (A.state !== B.state && A.at < B.at + B.hold && B.at < A.at + A.hold) warn = true;
      }
    }
    if (warn) conflicts += 1;
    const bars = segs.map(s => {
      const w = Math.max(2, x(s.at + Math.max(s.hold, 6)) - x(s.at));
      return `<rect x="${x(s.at).toFixed(1)}" y="${(y + 2).toFixed(1)}" width="${w.toFixed(1)}"
        height="${laneH - 6}" fill="${s.state === 'open' ? 'var(--open)' : 'var(--closed)'}" opacity="0.8">
        <title>${esc(`${door} ${s.state} ${fmt.clock(s.at)}–${fmt.clock(s.at + s.hold)} (${s.task_id})`)}</title>
      </rect>`;
    }).join('');
    return `<text x="2" y="${(y + laneH - 6).toFixed(1)}" font-size="9"
      fill="${warn ? 'var(--closed)' : 'var(--dim)'}">${door}${warn ? ' !' : ''}</text>${bars}`;
  }).join('');

  return {
    svg: `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="min-width:640px">
      <rect x="0" y="0" width="${W}" height="${H}" fill="#000"/>${rows}</svg>`,
    conflicts, doors,
  };
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
