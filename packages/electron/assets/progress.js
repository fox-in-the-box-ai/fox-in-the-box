'use strict';

const STEPS = [
  'Checking system',
  'Setting up Docker',
  'Pulling container image',
  'Starting container',
  'Waiting for Fox to be ready',
  'Opening Fox',
];

let currentIdx = 0;

function render(idx) {
  currentIdx = idx;
  document.getElementById('steps').innerHTML = STEPS.map((label, i) => {
    let iconHtml, cls;
    if (i < idx)        { iconHtml = '<span style="color:#4CAF50;font-size:15px;">✓</span>'; cls = 'done'; }
    else if (i === idx) { iconHtml = '<div class="spinner"></div>'; cls = 'active'; }
    else                { iconHtml = '<span style="opacity:0.35;font-size:11px;">○</span>'; cls = 'pending'; }
    return `<div class="step ${cls}"><div class="icon">${iconHtml}</div><span>${label}</span></div>`;
  }).join('');

  const diag = document.getElementById('diag');
  if (diag && idx === 1) {
    diag.open = true;
  }
}

function appendLog(line) {
  const el = document.getElementById('diag-body');
  el.textContent = el.textContent ? el.textContent + '\n' + line : line;
  el.scrollTop = el.scrollHeight;
}

render(currentIdx);

if (window.fitb) {
  window.fitb.onStepUpdate((idx) => render(idx));
  window.fitb.onLogLine((line) => appendLog(line));
}
