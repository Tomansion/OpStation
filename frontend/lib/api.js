/* Thin fetch helpers. The server is authoritative about everything: time,
 * delivery, failure and score. The client renders and reports clicks. */

async function json(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'content-type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* keep status */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  station:    () => json('/api/station'),
  config:     () => json('/api/config'),
  scenarios:  () => json('/api/scenarios'),
  createSession: (participant_name, scenario_id) =>
    json('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ participant_name, scenario_id }),
    }),
  session:    id => json(`/api/sessions/${id}`),
  summary:    id => json(`/api/sessions/${id}/summary`),
  adminStatus:   () => json('/api/admin/status'),
  adminSessions: () => json('/api/admin/sessions'),
  adminSession:  id => json(`/api/admin/sessions/${id}`),
  deleteSession: id => json(`/api/admin/sessions/${id}`, { method: 'DELETE' }),
  adminScenario: id => json(`/api/admin/scenarios/${id}`),
  generate:   body => json('/api/admin/scenarios/generate', {
    method: 'POST', body: JSON.stringify(body),
  }),
  job:        id => json(`/api/admin/jobs/${id}`),
};

/* One socket per session. Reconnects on drop, because elapsed time keeps
 * running while the browser is away — the world does not wait. */
export function connect(sessionId, onMessage) {
  let socket = null;
  let closed = false;
  let retry = null;

  function open() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${proto}://${location.host}/ws/sessions/${sessionId}`);
    socket.onmessage = ev => onMessage(JSON.parse(ev.data));
    socket.onclose = () => {
      if (!closed) retry = setTimeout(open, 900);
    };
  }
  open();

  return {
    send(payload) {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
    },
    close() {
      closed = true;
      clearTimeout(retry);
      if (socket) socket.close();
    },
  };
}

export const fmt = {
  /* Elapsed as mm:ss — the counter beside the station clock. */
  clock(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  },
  /* The station's own wall-clock time. */
  wall(date = new Date()) {
    return date.toTimeString().slice(0, 8);
  },
};
