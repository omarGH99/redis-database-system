/* Shared front-end helpers for every page. */
function $(id) { return document.getElementById(id); }

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** fetch JSON; throws an Error with the server's message on any failure. */
async function api(url, opts) {
  let r;
  try {
    r = await fetch(url, opts);
  } catch (e) {
    throw new Error('Network error — is the server running?');
  }
  let j = null;
  try { j = await r.json(); } catch (e) { /* non-JSON body */ }
  if (!r.ok) throw new Error((j && j.error) || `Request failed (${r.status})`);
  return j;
}

/** Show a dismissible error banner at the top of the page. */
function showError(msg) {
  let b = $('err-banner');
  if (!b) {
    b = document.createElement('div');
    b.id = 'err-banner';
    b.setAttribute('role', 'alert');
    document.querySelector('main').prepend(b);
  }
  b.innerHTML = `<span>⚠ ${esc(msg)}</span><button class="btn btn-ghost btn-xs" aria-label="Dismiss">✕</button>`;
  b.querySelector('button').onclick = () => b.remove();
}

/** Render an array of objects as a table (no sorting). */
function tableFrom(rows, maxHeight = 480) {
  if (!rows?.length) return '<p class="muted"><em>No results.</em></p>';
  const cols = [...new Set(rows.flatMap(r => Object.keys(r)))];
  let h = `<div class="tbl-wrap" style="max-height:${maxHeight}px;"><table class="dt"><thead><tr>`;
  cols.forEach(c => { h += `<th>${esc(c)}</th>`; });
  h += '</tr></thead><tbody>';
  rows.forEach(r => { h += '<tr>' + cols.map(c => `<td>${esc(r[c] ?? '')}</td>`).join('') + '</tr>'; });
  return h + '</tbody></table></div>';
}

/** Keep the URL query string in sync with a state object (shareable links). */
function syncUrl(params) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v); });
  const qs = p.toString();
  history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
}

/** Connection indicator in the header. */
async function pollHealth() {
  const dot = document.querySelector('.conn .dot');
  if (!dot) return;
  try {
    await api('/healthz');
    dot.classList.remove('down');
    dot.title = 'Redis connected';
  } catch (e) {
    dot.classList.add('down');
    dot.title = 'Redis unreachable';
  }
}
document.addEventListener('DOMContentLoaded', () => {
  pollHealth();
  setInterval(pollHealth, 15000);
});

/** Mobile nav toggle. */
document.addEventListener('DOMContentLoaded', () => {
  const t = $('nav-toggle');
  if (t) t.addEventListener('click', () => {
    const open = document.querySelector('header').classList.toggle('nav-open');
    t.setAttribute('aria-expanded', open);
  });
});
