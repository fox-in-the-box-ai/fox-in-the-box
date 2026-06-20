'use strict';

const os = require('os');
const fs = require('fs');
const { execFile } = require('child_process');
const { randomUUID } = require('crypto');

const SCRUB_PATTERNS = [
  { re: /sk-[A-Za-z0-9_-]{20,}/g, sub: 'sk-[REDACTED]' },
  { re: /key-[A-Za-z0-9_-]{20,}/g, sub: 'key-[REDACTED]' },
  { re: /Bearer\s+[A-Za-z0-9._-]{20,}/gi, sub: 'Bearer [REDACTED]' },
  { re: /(OPENROUTER_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|API_KEY|SECRET|TOKEN|PASSWORD)\s*=\s*\S+/gi, sub: '$1=[REDACTED]' },
];

function scrubText(text) {
  if (!text) return '';
  let result = text;
  const home = os.homedir();
  if (home) {
    const escaped = home.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const placeholder = process.platform === 'win32' ? '%USERPROFILE%' : '$HOME';
    result = result.replace(new RegExp(escaped, 'g'), placeholder);
  }
  for (const { re, sub } of SCRUB_PATTERNS) {
    result = result.replace(re, sub);
  }
  return result;
}

function readLogTail(logPath, lines) {
  try {
    const content = fs.readFileSync(logPath, 'utf8');
    const allLines = content.split('\n');
    return allLines.slice(-lines).join('\n');
  } catch (err) {
    return `[Could not read log: ${err.message}]`;
  }
}

function runSafe(command, args, timeoutMs) {
  return new Promise((resolve) => {
    try {
      execFile(command, args, { timeout: timeoutMs }, (err, stdout, stderr) => {
        if (err) {
          resolve(`[Error: ${err.message}]`);
          return;
        }
        resolve((stdout || '') + (stderr ? `\n[stderr] ${stderr}` : ''));
      });
    } catch (err) {
      resolve(`[Failed to run: ${err.message}]`);
    }
  });
}

async function gatherDiagnosticReport({ dockerManager, logPath, foxVersion, platform }) {
  platform = platform || process.platform;
  const report = {
    timestamp: new Date().toISOString(),
    installation_id: randomUUID(),
    fox_version: foxVersion || 'unknown',
    os: {
      platform,
      arch: process.arch,
      version: os.release(),
      free_ram_gb: Math.round(os.freemem() / (1024 ** 3) * 10) / 10,
      total_ram_gb: Math.round(os.totalmem() / (1024 ** 3) * 10) / 10,
    },
    docker: {},
    log_tail: '',
  };

  if (dockerManager) {
    try {
      const diag = await dockerManager.getDiagnostics();
      report.docker.daemon_reachable = diag.daemonReachable;
      report.docker.active_socket = diag.activeSocket;
      if (diag.dockerVersion) {
        const v = diag.dockerVersion;
        report.docker.version = {
          Version: v.Version,
          ApiVersion: v.ApiVersion,
          Os: v.Os,
          Arch: v.Arch,
          KernelVersion: v.KernelVersion,
        };
      }
      if (diag.container) {
        report.docker.container = {
          id: diag.container.id ? diag.container.id.substring(0, 12) : null,
          name: diag.container.name,
          state: diag.container.state,
          status: diag.container.status,
        };
      }
      if (diag.error) report.docker.error = diag.error;
      const sysInfo = await dockerManager.getDockerSystemInfo();
      if (sysInfo) report.docker.system_info = sysInfo;
    } catch (err) {
      report.docker.error = err.message;
    }
  }

  if (logPath) {
    report.log_tail = scrubText(readLogTail(logPath, 500));
  }

  if (platform === 'win32') {
    const [wslStatus, wslList] = await Promise.all([
      runSafe('wsl', ['--status'], 5000),
      runSafe('wsl', ['--list', '--verbose'], 5000),
    ]);
    report.windows = { wsl_status: wslStatus, wsl_list: wslList };
  } else if (platform === 'darwin') {
    const raw = await runSafe('launchctl', ['list'], 5000);
    let filtered = raw;
    if (!raw.startsWith('[')) {
      filtered = raw.split('\n').filter(l => /docker/i.test(l)).join('\n')
        || '[No docker entries in launchctl]';
    }
    report.darwin = { docker_daemon: filtered };
  }

  return report;
}

function formatAsMarkdown(report) {
  const lines = [];
  lines.push('# Fox in the Box — Diagnostic Report');
  lines.push('');
  lines.push(`**Generated:** ${report.timestamp}`);
  lines.push(`**Installation ID:** ${report.installation_id}`);
  lines.push(`**Fox version:** ${report.fox_version}`);
  lines.push('');

  lines.push('## System');
  lines.push(`- Platform: ${report.os.platform} (${report.os.arch})`);
  lines.push(`- OS version: ${report.os.version}`);
  lines.push(`- RAM: ${report.os.free_ram_gb} GB free / ${report.os.total_ram_gb} GB total`);
  lines.push('');

  lines.push('## Docker');
  if (report.docker.error) {
    lines.push(`- Error: ${report.docker.error}`);
  }
  lines.push(`- Daemon reachable: ${report.docker.daemon_reachable || false}`);
  if (report.docker.active_socket) {
    lines.push(`- Socket: ${report.docker.active_socket}`);
  }
  if (report.docker.version) {
    const v = report.docker.version;
    lines.push(`- Docker version: ${v.Version || 'unknown'} (API ${v.ApiVersion || '?'})`);
    lines.push(`- Docker OS/Arch: ${v.Os || '?'}/${v.Arch || '?'}`);
  }
  if (report.docker.system_info) {
    const si = report.docker.system_info;
    if (si.OperatingSystem) lines.push(`- OS type: ${si.OSType || '?'} — ${si.OperatingSystem}`);
    if (si.NCPU) lines.push(`- CPUs: ${si.NCPU}`);
    if (si.MemTotal) lines.push(`- Docker memory: ${Math.round(si.MemTotal / (1024 ** 3) * 10) / 10} GB`);
  }
  if (report.docker.container) {
    const c = report.docker.container;
    lines.push(`- Container: ${c.name || '?'} — ${c.state || '?'} (${c.status || '?'})`);
    lines.push(`- Container ID: ${c.id || '?'}`);
  } else {
    lines.push('- Container: not found');
  }
  lines.push('');

  if (report.windows) {
    lines.push('## Windows / WSL');
    lines.push('');
    lines.push('**WSL --status:**');
    lines.push('```');
    lines.push(report.windows.wsl_status || '[not available]');
    lines.push('```');
    lines.push('');
    lines.push('**WSL --list --verbose:**');
    lines.push('```');
    lines.push(report.windows.wsl_list || '[not available]');
    lines.push('```');
    lines.push('');
  }

  if (report.darwin) {
    lines.push('## macOS / Docker Daemon');
    lines.push('```');
    lines.push(report.darwin.docker_daemon || '[not available]');
    lines.push('```');
    lines.push('');
  }

  if (report.log_tail) {
    lines.push('## Electron log (last 500 lines)');
    lines.push('');
    lines.push('```');
    lines.push(report.log_tail);
    lines.push('```');
  }

  return lines.join('\n');
}

module.exports = {
  gatherDiagnosticReport,
  formatAsMarkdown,
  scrubText,
  readLogTail,
  SCRUB_PATTERNS,
};
