// Guard stdout/stderr against EPIPE (#748).
//
// When the packaged app is launched from a terminal whose pipe later
// closes (parent shell exits, launcher process dies), any console write —
// electron-log's console transport included — raises an async 'error'
// event on the stream. With no handler installed, Node escalates it to an
// uncaught exception and Electron shows a crash dialog. Logging must
// never take the app down: swallow stream errors; the file transport is
// unaffected and keeps the record. Non-EPIPE stream errors are recorded
// once via the file transport so observability isn't lost entirely.

let _warned = false;

function installStdioGuard() {
  for (const name of ['stdout', 'stderr']) {
    const stream = process[name];
    if (stream && typeof stream.on === 'function') {
      stream.on('error', (err) => {
        if (_warned || (err && err.code === 'EPIPE')) return;
        _warned = true;
        try {
          // Lazy require: the guard installs before the logger loads, and
          // electron-log's file transport is safe even when stdio is dead.
          require('electron-log').warn(
            `[stdio-guard] ${name} stream error: ${(err && (err.code || err.message)) || 'unknown'}`
          );
        } catch (_) { /* logging must never throw from here */ }
      });
    }
  }
}

module.exports = { installStdioGuard };
