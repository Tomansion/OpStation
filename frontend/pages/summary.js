/* The debrief. Reveals the breakdown the player could not see during play:
 * what failed, who had asked for it, when it broke, and what each thread cost. */

import { api, fmt } from '../lib/api.js';
import { strings } from '../lib/i18n.js';

export async function summary(root, { params }) {
  const data = await api.summary(params[0]);
  const s = strings(data.language);

  const failures = data.failed_tasks.length
    ? `<table>
        <tr><th>${s.thread}</th><th>${s.obligation}</th><th>${s.door}</th><th>${s.askedBy}</th>
            <th>${s.asked}</th><th>${s.broke}</th></tr>
        ${data.failed_tasks.map(f => `<tr class="bad">
          <td>${esc(f.thread)}</td><td>${esc(f.obligation)}</td>
          <td>${esc(f.door || '')}</td><td>${esc(f.requested_by || '')}</td>
          <td>${fmt.clock(f.requested_at || 0)}</td>
          <td>${fmt.clock(f.failed_at || 0)}</td></tr>`).join('')}
       </table>`
    : `<div class="note">${s.nothingFailed}</div>`;

  const challenges = data.challenges.length
    ? data.challenges.map(c => `
        <div style="border-bottom:1px solid var(--rule);padding:8px 0">
          <div class="note">${c.slot === 'debrief' ? s.debriefTag : s.onShiftTag} ·
            ${c.kind.toUpperCase()} · ${esc(c.thread)}</div>
          <div style="margin:4px 0">${esc(c.prompt)}</div>
          <div class="note">${s.youSaid}<span class="${c.outcome === 'correct' ? 'tag ok' : 'tag no'}">
            ${esc(c.your_answer)}</span></div>
          ${c.outcome === 'correct' ? ''
            : `<div class="note">${s.correctWas}<strong>${esc(c.correct_answer || '')}</strong></div>`}
          <div class="note">${esc(c.explanation)}</div>
        </div>`).join('')
    : `<div class="note">${s.noQuestionsAnswered}</div>`;

  root.innerHTML = `
    <div class="readouts">
      <div class="readout"><div class="k">${s.penalties}</div>
        <div class="v ${data.penalties ? 'bad' : ''}">${data.penalties}</div></div>
      <div class="readout"><div class="k">${s.failedObligations}</div>
        <div class="v">${data.failed_tasks.length}</div></div>
      <div class="readout"><div class="k">${s.wrongOrUnknown}</div>
        <div class="v">${data.challenges.filter(c => c.outcome !== 'correct').length}</div></div>
      <div class="readout"><div class="k">${s.onShiftTag}</div>
        <div class="v">${fmt.clock(data.elapsed)}</div></div>
      <div class="readout"><div class="k">${s.expiredUnread}</div>
        <div class="v ${data.messages_unread_at_expiry ? 'warn' : ''}">
          ${data.messages_unread_at_expiry}</div></div>
    </div>

    <div class="cols" style="margin-top:12px">
      <div class="col grow">
        <div class="panel"><h2>${s.whatBroke}</h2><div class="body">${failures}</div></div>
        <div class="panel"><h2>${s.questions}</h2><div class="body">${challenges}</div></div>
      </div>
      <div class="col">
        <div class="panel"><h2>${esc(data.scenario_name)}</h2>
          <div class="body note">
            <p>${esc(data.participant_name)}</p>
            ${data.per_thread.length ? `<table><tr><th>${s.thread}</th><th>${s.cost}</th></tr>
              ${data.per_thread.map(t => `<tr><td>${esc(t.thread)}</td>
                <td>${t.penalties}</td></tr>`).join('')}</table>`
              : `<p>${s.noThreadCost}</p>`}
          </div>
        </div>
        <div class="panel"><h2>${s.whatWasHappening}</h2>
          <div class="body note">
            ${data.threads.map(t => `<p><strong>${esc(t.title)}</strong><br>
              ${esc(t.summary)}</p>`).join('')}
          </div>
        </div>
        <a href="/" data-nav><button class="big">${s.backToStart}</button></a>
      </div>
    </div>`;
}

function esc(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML;
}
