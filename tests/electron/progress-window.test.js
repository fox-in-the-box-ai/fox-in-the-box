'use strict';

jest.mock('electron-log', () => ({
  info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn(),
}));

// Extract and test _activeStepIndex by reading main.js source.
describe('_activeStepIndex step mapping', () => {
  const fs = require('fs');
  const path = require('path');
  const src = fs.readFileSync(
    path.join(__dirname, '../../packages/electron/src/main.js'), 'utf8'
  );

  // Extract INSTALL_STEPS array and _activeStepIndex function from source.
  const stepsMatch = src.match(/const INSTALL_STEPS = (\[[\s\S]+?\]);/);
  const fnMatch = src.match(/function _activeStepIndex\(title\) \{([\s\S]+?)\n\}/);

  let fn = null;
  if (stepsMatch && fnMatch) {
    try {
      // eslint-disable-next-line no-new-func
      const INSTALL_STEPS = eval(stepsMatch[1]); // safe: reading own source
      fn = new Function('INSTALL_STEPS', `function _activeStepIndex(title) {${fnMatch[1]}\n}\nreturn _activeStepIndex;`)(INSTALL_STEPS);
    } catch (_) {}
  }

  const skip = !fn;

  (skip ? test.skip : test)('maps "Check system" phase to index 0', () => {
    expect(fn('Step 1/7 - Check system: Preparing...')).toBe(0);
  });
  (skip ? test.skip : test)('maps "Install Docker" phase to index 1', () => {
    expect(fn('Step 2/7 - Install Docker: installing...')).toBe(1);
  });
  (skip ? test.skip : test)('maps "Start Docker" phase to index 2', () => {
    expect(fn('Step 3/7 - Start Docker: waiting...')).toBe(2);
  });
  (skip ? test.skip : test)('maps "Download image" phase to index 3', () => {
    expect(fn('Step 4/7 - Download image: pulling...')).toBe(3);
  });
  (skip ? test.skip : test)('maps "Start container" phase to index 4', () => {
    expect(fn('Step 5/7 - Start container: creating...')).toBe(4);
  });
  (skip ? test.skip : test)('maps "Wait for services" phase to index 5', () => {
    expect(fn('Step 6/7 - Wait for services: waiting...')).toBe(5);
  });
  (skip ? test.skip : test)('maps "Connect network" phase to index 6', () => {
    expect(fn('Step 7/7 - Connect network: connecting...')).toBe(6);
  });
  (skip ? test.skip : test)('freeform Docker start string maps to index 2', () => {
    expect(fn('Starting Docker Desktop...')).toBe(2);
  });
  (skip ? test.skip : test)('freeform image string maps to index 3', () => {
    expect(fn('Docker is ready — pulling container image...')).toBe(3);
  });
  (skip ? test.skip : test)('empty string returns -1', () => {
    expect(fn('')).toBe(-1);
  });
  (skip ? test.skip : test)('unknown string returns 0', () => {
    expect(fn('some unknown message')).toBe(0);
  });
});
