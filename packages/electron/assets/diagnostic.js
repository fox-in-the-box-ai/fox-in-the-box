'use strict';

let _reportText = '';

if (window.fitbDiagnostic) {
  window.fitbDiagnostic.gather().then(function (markdown) {
    document.getElementById('loading').style.display = 'none';
    if (!markdown) {
      document.getElementById('error-text').style.display = 'flex';
      document.getElementById('error-text').textContent = 'Failed to generate diagnostic report.';
      return;
    }
    _reportText = markdown;
    const body = document.getElementById('report-body');
    body.textContent = markdown;
    body.style.display = 'block';
    document.getElementById('btn-copy').disabled = false;
  }).catch(function (err) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('error-text').style.display = 'flex';
    document.getElementById('error-text').textContent = 'Error: ' + (err.message || err);
  });
}

document.getElementById('btn-copy').addEventListener('click', function () {
  if (_reportText && window.fitbDiagnostic) {
    window.fitbDiagnostic.copy(_reportText);
    const btn = document.getElementById('btn-copy');
    btn.textContent = 'Copied!';
    setTimeout(function () { btn.textContent = 'Copy to clipboard'; }, 2000);
  }
});

document.getElementById('btn-close').addEventListener('click', function () {
  if (window.fitbDiagnostic) window.fitbDiagnostic.close();
});
