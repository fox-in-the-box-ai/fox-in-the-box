const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const SCRIPT = path.join(__dirname, '..', '..', 'packages', 'electron', 'scripts', 'repair-updater-yml.js');

// The repair script rewrites latest.yml's sha512/size from the artifacts
// on disk — the release pipeline runs it after in-place installer
// signing (#819/#820). This locks in the digest math and the yml
// round-trip against a fixture.
describe('repair-updater-yml', () => {
  test('recomputes sha512 and size for every referenced file', () => {
    const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'repair-yml-'));
    const exe = 'fox-in-the-box-setup-x64.exe';
    fs.writeFileSync(path.join(dist, exe), 'signed-binary-contents-v2');
    const rightHash = crypto
      .createHash('sha512')
      .update(fs.readFileSync(path.join(dist, exe)))
      .digest('base64');
    const staleYml = [
      'version: 0.7.61',
      'files:',
      `  - url: ${exe}`,
      '    sha512: STALEHASHFROMBEFORESIGNING==',
      '    size: 1',
      `path: ${exe}`,
      'sha512: STALEHASHFROMBEFORESIGNING==',
      "releaseDate: '2026-09-06T00:00:00.000Z'",
      '',
    ].join('\n');
    const ymlPath = path.join(dist, 'latest.yml');
    fs.writeFileSync(ymlPath, staleYml);

    execFileSync('node', [SCRIPT, ymlPath]);

    const yaml = require('js-yaml');
    const doc = yaml.load(fs.readFileSync(ymlPath, 'utf8'));
    expect(doc.files[0].sha512).toBe(rightHash);
    expect(doc.files[0].size).toBe(fs.statSync(path.join(dist, exe)).size);
    expect(doc.sha512).toBe(rightHash);
    expect(doc.version).toBe('0.7.61');
    expect(doc.releaseDate).toBeTruthy();
  });

  test('fails loud when a referenced artifact is missing', () => {
    const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'repair-yml-'));
    fs.writeFileSync(
      path.join(dist, 'latest.yml'),
      'version: 0.7.61\nfiles:\n  - url: missing.exe\n    sha512: X\n    size: 1\n'
    );
    expect(() => execFileSync('node', [SCRIPT, path.join(dist, 'latest.yml')], { stdio: 'pipe' })).toThrow();
  });
});
