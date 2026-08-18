// Guard stdout/stderr against EPIPE (#748).
//
// When the packaged app is launched from a terminal whose pipe later
// closes (parent shell exits, launcher process dies), any console write —
// electron-log's console transport included — raises an async 'error'
// event on the stream. With no handler installed, Node escalates it to an
// uncaught exception and Electron shows a crash dialog. Logging must
// never take the app down: swallow stream errors; the file transport is
// unaffected and keeps the record.

function installStdioGuard() {
  for (const stream of [process.stdout, process.stderr]) {
    if (stream && typeof stream.on === "function") {
      stream.on("error", () => {});
    }
  }
}

module.exports = { installStdioGuard };
