/* Router and shell.
 *
 * Framework-free on purpose: the station renderer is already framework-free,
 * the app is four pages, and a research instrument that a researcher has to be
 * able to run should not need a build step. */

import { admin, adminScenario, adminSession } from './pages/admin.js';
import { game } from './pages/game.js';
import { home } from './pages/home.js';
import { summary } from './pages/summary.js';

/* One audio context for the whole app. START SHIFT is the user gesture that
 * primes it; if priming fails the session is refused rather than started and
 * thrown away later. */
const audio = {
  context: null,
  async prime() {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) throw new Error('this browser has no Web Audio');
    this.context = this.context || new Ctor();
    if (this.context.state === 'suspended') await this.context.resume();
    // Play one silent buffer: resuming is not proof that output works.
    const buffer = this.context.createBuffer(1, 1, this.context.sampleRate);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    source.start(0);
    if (this.context.state !== 'running') throw new Error('audio stayed suspended');
  },
};

const routes = [
  [/^\/$/, home],
  [/^\/game\/([^/]+)$/, game],
  [/^\/summary\/([^/]+)$/, summary],
  [/^\/admin$/, admin],
  [/^\/admin\/scenarios\/([^/]+)$/, adminScenario],
  [/^\/admin\/sessions\/([^/]+)$/, adminSession],
];

const root = document.getElementById('root');
let teardown = null;

async function render() {
  if (teardown) { try { teardown(); } catch { /* ignore */ } teardown = null; }
  const path = location.pathname.replace(/\/+$/, '') || '/';
  const hit = routes.find(([pattern]) => pattern.test(path));
  if (!hit) {
    root.innerHTML = '<div class="panel"><h2>No such page</h2>'
      + '<div class="body note"><a href="/" data-nav>Back to the start</a></div></div>';
    return;
  }
  const [pattern, page] = hit;
  const params = (path.match(pattern) || []).slice(1);
  root.innerHTML = '<div class="loading">LOADING</div>';
  try {
    teardown = await page(root, { navigate, audio, params }) || null;
  } catch (exc) {
    root.innerHTML = `<div class="panel alert"><h2>Something went wrong</h2>
      <div class="body note">${exc.message}<br><br>
      <a href="/" data-nav>Back to the start</a></div></div>`;
    // Keep the real error where a developer will find it.
    console.error(exc);
  }
}

function navigate(path) {
  history.pushState({}, '', path);
  render();
}

document.addEventListener('click', ev => {
  const link = ev.target.closest('a[data-nav]');
  if (!link) return;
  ev.preventDefault();
  navigate(link.getAttribute('href'));
});
window.addEventListener('popstate', render);
render();
