// The Electron.app npm installs is only linker-signed (`codesign -dv`: "adhoc,linker-signed",
// "Info.plist=not bound"), and macOS refuses such a bundle's notification requests with
// UNErrorDomain error 1 without ever asking or listing it in System Settings ▸ Notifications. An
// ad-hoc re-sign of the whole bundle is enough; the packaged TI-Toolbox.app is signed by
// electron-builder and never needs this. Runs on `npm install`/`npm ci` and as
// `npm run sign:dev-electron`; a no-op off macOS or when the signature is already valid.
// Quit a running dev app first: re-signing a bundle under a live process can crash it.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const app = join(dirname(fileURLToPath(import.meta.url)), "..", "node_modules", "electron", "dist", "Electron.app");
if (process.platform === "darwin" && existsSync(app)) {
  try {
    execFileSync("codesign", ["--verify", "--deep", "--strict", app], { stdio: "ignore" });
  } catch {
    execFileSync("codesign", ["--force", "--deep", "--sign", "-", app], { stdio: "inherit" });
    console.log("sign-dev-electron: re-signed node_modules Electron.app ad hoc (macOS notifications need a valid signature)");
  }
}
