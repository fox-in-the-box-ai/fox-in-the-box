// Regenerate latest.yml's checksums after in-place installer signing.
//
// electron-builder writes latest.yml (sha512 + size per artifact, plus
// the legacy top-level pair) during the build; the Azure Trusted
// Signing step then modifies the .exe in place, so the recorded hash
// no longer matches the shipped binary and electron-updater would
// download the update and refuse it (#819/#820 review). Run AFTER
// signing, from packages/electron: recomputes sha512/size for every
// file the yml references. Fails loud on any missing artifact.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const yaml = require('js-yaml');

const ymlPath = process.argv[2] || path.join('dist', 'latest.yml');
const dist = path.dirname(ymlPath);
const doc = yaml.load(fs.readFileSync(ymlPath, 'utf8'));

const digest = (file) =>
  crypto.createHash('sha512').update(fs.readFileSync(path.join(dist, file))).digest('base64');

for (const f of doc.files || []) {
  const before = f.sha512;
  f.sha512 = digest(f.url);
  f.size = fs.statSync(path.join(dist, f.url)).size;
  console.log(`${f.url}: sha512 ${before === f.sha512 ? 'unchanged' : 'updated'}, size ${f.size}`);
}
if (doc.path) doc.sha512 = digest(doc.path);

fs.writeFileSync(ymlPath, yaml.dump(doc, { lineWidth: -1 }));
console.log(`${ymlPath} rewritten`);
