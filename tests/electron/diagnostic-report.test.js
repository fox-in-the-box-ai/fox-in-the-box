'use strict';

jest.mock('electron-log', () => ({ info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() }));

const os = require('os');
const fs = require('fs');
const path = require('path');
const { scrubText, readLogTail, formatAsMarkdown, gatherDiagnosticReport } = require('../../packages/electron/src/diagnostic-report');

// ─── scrubText ──────────────────────────────────────────────────────────────

describe('scrubText', () => {
  test('redacts OpenRouter-style API keys', () => {
    const input = 'Using key sk-or-v1-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz';
    expect(scrubText(input)).toBe('Using key sk-[REDACTED]');
  });

  test('redacts sk- prefixed keys', () => {
    const input = 'OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrst';
    expect(scrubText(input)).toBe('OPENAI_API_KEY=[REDACTED]');
  });

  test('redacts Bearer tokens', () => {
    const input = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature';
    expect(scrubText(input)).toBe('Authorization: Bearer [REDACTED]');
  });

  test('redacts env var assignments for known secret names', () => {
    const input = 'OPENROUTER_API_KEY=sk-or-v1-longvalue123456789012345';
    expect(scrubText(input)).toBe('OPENROUTER_API_KEY=[REDACTED]');
  });

  test('redacts PASSWORD env var', () => {
    expect(scrubText('DB_PASSWORD=hunter2')).toBe('DB_PASSWORD=[REDACTED]');
  });

  test('replaces home directory paths (unix)', () => {
    const home = os.homedir();
    const input = `Loading config from ${home}/Documents/config.json`;
    const result = scrubText(input);
    expect(result).not.toContain(home);
    if (process.platform !== 'win32') {
      expect(result).toContain('$HOME/Documents/config.json');
    }
  });

  test('handles multiple keys in one block', () => {
    const input = [
      'API_KEY=mysecretvalue123',
      'key-abcdefghijklmnopqrstuvwxyz',
      'Bearer tok_1234567890abcdefghijklmno',
    ].join('\n');
    const result = scrubText(input);
    expect(result).not.toContain('mysecretvalue123');
    expect(result).toContain('key-[REDACTED]');
    expect(result).toContain('Bearer [REDACTED]');
  });

  test('returns empty string for falsy input', () => {
    expect(scrubText(null)).toBe('');
    expect(scrubText(undefined)).toBe('');
    expect(scrubText('')).toBe('');
  });

  test('leaves safe text unchanged', () => {
    const input = 'Fox in the box v0.7.52 starting up';
    expect(scrubText(input)).toBe(input);
  });
});

// ─── readLogTail ────────────────────────────────────────────────────────────

describe('readLogTail', () => {
  const tmpDir = path.join(os.tmpdir(), 'fitb-diag-test-' + Date.now());
  const logFile = path.join(tmpDir, 'test.log');

  beforeAll(() => {
    fs.mkdirSync(tmpDir, { recursive: true });
    const lines = Array.from({ length: 20 }, (_, i) => `line ${i + 1}`);
    fs.writeFileSync(logFile, lines.join('\n'));
  });

  afterAll(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  test('returns last N lines', () => {
    const result = readLogTail(logFile, 5);
    const lines = result.split('\n');
    expect(lines).toContain('line 20');
    expect(lines).toContain('line 16');
    expect(lines).not.toContain('line 1');
  });

  test('returns error message for missing file', () => {
    const result = readLogTail('/nonexistent/path/log.txt', 10);
    expect(result).toMatch(/\[Could not read log:/);
  });
});

// ─── formatAsMarkdown ───────────────────────────────────────────────────────

describe('formatAsMarkdown', () => {
  const baseReport = {
    timestamp: '2026-06-20T12:00:00.000Z',
    installation_id: 'test-uuid-1234',
    fox_version: 'v0.7.53',
    os: {
      platform: 'darwin',
      arch: 'arm64',
      version: '25.5.0',
      free_ram_gb: 8.2,
      total_ram_gb: 16.0,
    },
    docker: {
      daemon_reachable: true,
      active_socket: 'default',
      version: { Version: '27.5.1', ApiVersion: '1.47', Os: 'linux', Arch: 'amd64' },
      container: { id: 'abc123def456', name: '/fox-in-the-box', state: 'running', status: 'Up 2 hours' },
    },
    log_tail: 'Fox in the box starting up\nContainer healthy',
  };

  test('includes header and version', () => {
    const md = formatAsMarkdown(baseReport);
    expect(md).toContain('# Fox in the Box — Diagnostic Report');
    expect(md).toContain('v0.7.53');
    expect(md).toContain('test-uuid-1234');
  });

  test('includes system info', () => {
    const md = formatAsMarkdown(baseReport);
    expect(md).toContain('darwin (arm64)');
    expect(md).toContain('8.2 GB free');
  });

  test('includes docker info', () => {
    const md = formatAsMarkdown(baseReport);
    expect(md).toContain('Daemon reachable: true');
    expect(md).toContain('27.5.1');
    expect(md).toContain('/fox-in-the-box');
  });

  test('includes log tail', () => {
    const md = formatAsMarkdown(baseReport);
    expect(md).toContain('Fox in the box starting up');
    expect(md).toContain('Container healthy');
  });

  test('includes windows section when present', () => {
    const report = { ...baseReport, windows: { wsl_status: 'Default: Ubuntu', wsl_list: '  NAME    STATE' } };
    const md = formatAsMarkdown(report);
    expect(md).toContain('Windows / WSL');
    expect(md).toContain('Default: Ubuntu');
  });

  test('includes darwin section when present', () => {
    const report = { ...baseReport, darwin: { docker_daemon: 'com.docker.vmnetd' } };
    const md = formatAsMarkdown(report);
    expect(md).toContain('macOS / Docker Daemon');
    expect(md).toContain('com.docker.vmnetd');
  });

  test('handles missing container gracefully', () => {
    const report = { ...baseReport, docker: { daemon_reachable: false } };
    const md = formatAsMarkdown(report);
    expect(md).toContain('Container: not found');
  });

  test('handles docker system_info when present', () => {
    const report = {
      ...baseReport,
      docker: {
        ...baseReport.docker,
        system_info: { OSType: 'linux', OperatingSystem: 'Docker Desktop', NCPU: 8, MemTotal: 17179869184 },
      },
    };
    const md = formatAsMarkdown(report);
    expect(md).toContain('linux');
    expect(md).toContain('Docker Desktop');
    expect(md).toContain('CPUs: 8');
  });
});

// ─── gatherDiagnosticReport ─────────────────────────────────────────────────

describe('gatherDiagnosticReport', () => {
  test('returns report with OS info even without docker', async () => {
    const report = await gatherDiagnosticReport({});
    expect(report.os.platform).toBeTruthy();
    expect(report.os.arch).toBeTruthy();
    expect(report.installation_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(report.timestamp).toBeTruthy();
  });

  test('calls dockerManager.getDiagnostics when provided', async () => {
    const mockDocker = {
      getDiagnostics: jest.fn().mockResolvedValue({
        daemonReachable: true,
        activeSocket: '/var/run/docker.sock',
        dockerVersion: { Version: '27.0.0', ApiVersion: '1.46', Os: 'linux', Arch: 'amd64' },
        container: { id: 'abcdef123456', name: '/fox-in-the-box', state: 'running', status: 'Up' },
      }),
      getDockerSystemInfo: jest.fn().mockResolvedValue({
        OSType: 'linux',
        OperatingSystem: 'Ubuntu 24.04',
        NCPU: 4,
      }),
    };

    const report = await gatherDiagnosticReport({ dockerManager: mockDocker });
    expect(mockDocker.getDiagnostics).toHaveBeenCalled();
    expect(mockDocker.getDockerSystemInfo).toHaveBeenCalled();
    expect(report.docker.daemon_reachable).toBe(true);
    expect(report.docker.version.Version).toBe('27.0.0');
    expect(report.docker.container.id).toBe('abcdef123456');
    expect(report.docker.system_info.NCPU).toBe(4);
  });

  test('handles dockerManager errors gracefully', async () => {
    const mockDocker = {
      getDiagnostics: jest.fn().mockRejectedValue(new Error('Docker not available')),
      getDockerSystemInfo: jest.fn().mockResolvedValue(null),
    };

    const report = await gatherDiagnosticReport({ dockerManager: mockDocker });
    expect(report.docker.error).toBe('Docker not available');
  });

  test('does not include container logs (SEC-1)', async () => {
    const mockDocker = {
      getDiagnostics: jest.fn().mockResolvedValue({
        daemonReachable: true,
        containerLogs: 'secret conversation content here',
        container: { id: 'abc', name: '/fox', state: 'running', status: 'Up' },
      }),
      getDockerSystemInfo: jest.fn().mockResolvedValue(null),
    };

    const report = await gatherDiagnosticReport({ dockerManager: mockDocker });
    const fullText = JSON.stringify(report);
    expect(fullText).not.toContain('secret conversation content');
  });

  test('scrubs log content', async () => {
    const tmpDir = path.join(os.tmpdir(), 'fitb-diag-gather-' + Date.now());
    const logFile = path.join(tmpDir, 'main.log');
    fs.mkdirSync(tmpDir, { recursive: true });
    fs.writeFileSync(logFile, 'Using API_KEY=sk-or-v1-reallylongsecretkeythatshouldberedacted\nNormal log line');

    try {
      const report = await gatherDiagnosticReport({ logPath: logFile });
      expect(report.log_tail).not.toContain('reallylongsecretkeythatshouldberedacted');
      expect(report.log_tail).toContain('API_KEY=[REDACTED]');
      expect(report.log_tail).toContain('Normal log line');
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  test('truncates container ID to 12 chars', async () => {
    const mockDocker = {
      getDiagnostics: jest.fn().mockResolvedValue({
        daemonReachable: true,
        container: { id: 'abcdef1234567890abcdef1234567890', name: '/fox', state: 'running', status: 'Up' },
      }),
      getDockerSystemInfo: jest.fn().mockResolvedValue(null),
    };

    const report = await gatherDiagnosticReport({ dockerManager: mockDocker });
    expect(report.docker.container.id).toBe('abcdef123456');
  });
});
