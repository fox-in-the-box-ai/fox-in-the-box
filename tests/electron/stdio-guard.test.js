"use strict";

const { EventEmitter } = require("events");
const {
  installStdioGuard,
} = require("../../packages/electron/src/stdio-guard");

describe("installStdioGuard", () => {
  let originalStdout;
  let originalStderr;

  beforeEach(() => {
    originalStdout = Object.getOwnPropertyDescriptor(process, "stdout");
    originalStderr = Object.getOwnPropertyDescriptor(process, "stderr");
  });

  afterEach(() => {
    Object.defineProperty(process, "stdout", originalStdout);
    Object.defineProperty(process, "stderr", originalStderr);
  });

  function swapStream(name) {
    const fake = new EventEmitter();
    Object.defineProperty(process, name, { value: fake, configurable: true });
    return fake;
  }

  test("an EPIPE error on stdout no longer throws after the guard is installed", () => {
    const fakeOut = swapStream("stdout");
    const epipe = Object.assign(new Error("write EPIPE"), { code: "EPIPE" });

    // Without a handler, EventEmitter turns 'error' into a throw — the
    // exact escalation path that produced the #748 crash dialog.
    expect(() => fakeOut.emit("error", epipe)).toThrow("write EPIPE");

    installStdioGuard();
    expect(() => fakeOut.emit("error", epipe)).not.toThrow();
  });

  test("guards stderr as well", () => {
    const fakeErr = swapStream("stderr");
    installStdioGuard();
    expect(() => fakeErr.emit("error", new Error("write EPIPE"))).not.toThrow();
  });

  test("tolerates absent or handler-less streams", () => {
    Object.defineProperty(process, "stdout", {
      value: undefined,
      configurable: true,
    });
    Object.defineProperty(process, "stderr", { value: {}, configurable: true });
    expect(() => installStdioGuard()).not.toThrow();
  });
});
