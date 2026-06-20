// packages/electron/build/afterPack.js
//
// electron-builder `afterPack` hook (configured in electron-builder.yml).
// Runs after the app is packed (unpacked dir ready) but BEFORE distribution-
// specific work (NSIS installer pack on Windows). We use it to embed the
// Fox app icon into the inner Windows executable.
//
// ## Why we need this
//
// `electron-builder` normally embeds the win.icon into the inner .exe via
// rcedit during its sign-and-edit phase. We disabled `signAndEditExecutable`
// (set to false) because we sign separately with Azure Trusted Signing —
// but that flag controls BOTH signing AND editing. So rcedit never ran, and
// the inner FoxInTheBox.exe shipped with the default Electron icon (FITB #287
// reported by bsdigital 2026-05-20).
//
// ## Why this hook is safe for the Azure signing path
//
// Azure Trusted Signing (configured in .github/workflows/build-electron.yml)
// signs the OUTER NSIS installer .exe AFTER electron-builder finishes — and
// only the outer installer, not the inner FoxInTheBox.exe. So:
//
//   1. electron-builder packs (this hook runs here)        ← icon embed
//   2. electron-builder packs NSIS installer with the iconned inner exe
//   3. Azure signs the outer NSIS installer
//
// Signature on the outer installer covers the bytes of the inner exe at
// the moment of NSIS packing — embedding the icon BEFORE step 2 means the
// signed bytes include the icon. No signature invalidation.
//
// ## Why not just set signAndEditExecutable: true
//
// That flag would re-enable BOTH rcedit (good) AND electron-builder's
// built-in signing (bad — would need a cert we don't have locally; would
// fail the build). Using afterPack lets us turn on JUST the rcedit half.

'use strict';

const path = require('path');
const { execFileSync } = require('child_process');

exports.default = async function afterPack(context) {
  // Only runs for Windows; Mac uses a separate signing/iconning path that
  // already works (icon.icns is embedded by electron-builder for darwin
  // regardless of signAndEditExecutable, because that flag is Windows-only).
  if (context.electronPlatformName !== 'win32') return;

  const productFilename = context.packager.appInfo.productFilename;
  const exePath = path.join(context.appOutDir, `${productFilename}.exe`);
  const iconPath = path.resolve(__dirname, '..', 'assets', 'icon.ico');

  console.log(`[afterPack] Embedding ${iconPath} into ${exePath} via rcedit`);

  // electron-builder bundles `app-builder-bin` which ships rcedit, but the
  // path isn't stable. `rcedit` npm package is the simpler dep — installed
  // as a devDependency of packages/electron.
  const { rcedit } = require('rcedit');
  await rcedit(exePath, {
    icon: iconPath,
  });

  console.log(`[afterPack] Icon embedded successfully.`);
};
