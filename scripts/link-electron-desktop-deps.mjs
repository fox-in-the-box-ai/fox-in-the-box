/**
 * pnpm `node-linker=hoisted` places deps in the repo root; electron-builder still
 * expects `electron` under `packages/electron/node_modules`. Link the hoisted copy.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const desktopNm = path.join(root, "packages/electron/node_modules");
const names = ["electron"];

fs.mkdirSync(desktopNm, { recursive: true });

for (const name of names) {
  const src = path.join(root, "node_modules", name);
  const dest = path.join(desktopNm, name);
  if (!fs.existsSync(src)) {
    continue;
  }
  if (fs.existsSync(dest)) {
    continue;
  }
  try {
    if (process.platform === "win32") {
      fs.symlinkSync(src, dest, "junction");
    } else {
      fs.symlinkSync(src, dest, "dir");
    }
  } catch (e) {
    console.warn(`link-electron-desktop-deps: could not link ${name}: ${e.message}`);
  }
}
