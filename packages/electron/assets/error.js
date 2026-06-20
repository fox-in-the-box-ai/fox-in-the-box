'use strict';

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

if (window.fitbError) {
  window.fitbError.getData().then(d => {
    document.getElementById('meta').innerHTML =
      `<div><b>Session:</b> ${esc(d.sessionId)}</div>` +
      `<div><b>Phase:</b> ${esc(d.phase)}</div>` +
      `<div><b>Error code:</b> ${esc(d.code)}</div>`;
    document.getElementById('message').textContent = d.message;
    document.getElementById('remediation').innerHTML = `<b>Try:</b> ${esc(d.remediation)}`;
    document.getElementById('log-path').textContent = d.logPath;
    document.getElementById('diag-body').textContent = d.diagnosticsText;
  });
}

document.getElementById('btn-diag').addEventListener('click', () => {
  if (window.fitbError) window.fitbError.openDiagnosticReport();
});

document.getElementById('btn-copy').addEventListener('click', () => {
  if (window.fitbError) window.fitbError.copyDiagnostics();
});

document.getElementById('btn-close').addEventListener('click', () => {
  if (window.fitbError) window.fitbError.close();
});
