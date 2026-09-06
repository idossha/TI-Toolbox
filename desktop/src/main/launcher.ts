// The launcher is a local page on the privileged app:// scheme (never server content).
// It connects to a manually-typed server, or picks a project directory and starts/attaches to
// its Docker stack itself — either path ends the same way: a token handed to the main process.

export const LAUNCHER_ORIGIN = "app://launcher";

export const LAUNCHER_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'unsafe-inline'">
<title>TI-Toolbox</title>
<style>
  :root { color-scheme: light dark; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  body { margin: 0; display: grid; place-items: center; min-height: 100vh; background: #0f172a; color: #e2e8f0; }
  main { width: min(28rem, 90vw); padding: 2rem; border-radius: 12px; background: #1e293b; box-shadow: 0 10px 30px rgb(0 0 0 / .4); }
  h1 { font-size: 1.25rem; margin: 0 0 .25rem; }
  h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #64748b; margin: 1.5rem 0 .5rem; }
  p.sub { margin: 0 0 1.5rem; color: #94a3b8; font-size: .875rem; }
  label { display: block; font-size: .8rem; color: #94a3b8; margin: .75rem 0 .25rem; }
  input { width: 100%; box-sizing: border-box; padding: .5rem .6rem; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: inherit; font: inherit; }
  input[readonly] { color: #94a3b8; }
  .row { display: flex; gap: .5rem; margin-top: 1.25rem; align-items: center; }
  .row input { flex: 1; margin-top: 0; }
  hr { border: none; border-top: 1px solid #334155; margin: 1.5rem 0 0; }
  button { padding: .5rem .9rem; border-radius: 6px; border: 1px solid #334155; background: #334155; color: inherit; font: inherit; cursor: pointer; }
  button.primary { background: #2563eb; border-color: #2563eb; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  #status { min-height: 1.25rem; margin-top: 1rem; font-size: .875rem; color: #94a3b8; }
  #status.error { color: #f87171; }
  footer { margin-top: 1.5rem; font-size: .75rem; color: #64748b; }
</style>
</head>
<body>
<main>
  <h1>TI-Toolbox</h1>
  <p class="sub">Connect to a running <code>tit.server</code>, or start one from a project folder.</p>
  <form id="connect-form">
    <label for="server-url">Server URL</label>
    <input id="server-url" name="url" type="url" value="http://127.0.0.1:8765" autocomplete="off" spellcheck="false" required>
    <label for="token">Token</label>
    <input id="token" name="token" type="password" autocomplete="off" required>
    <div class="row">
      <button id="connect" class="primary" type="submit">Connect</button>
    </div>
  </form>
  <hr>
  <h2>Or start the Docker stack</h2>
  <label for="project-dir">Project directory</label>
  <div class="row">
    <input id="project-dir" type="text" readonly placeholder="Choose a project folder…">
    <button id="browse" type="button">Browse…</button>
  </div>
  <div class="row">
    <button id="start-stack" class="primary" type="button" disabled>Start the Docker stack</button>
  </div>
  <div id="status" role="status"></div>
  <footer id="footer"></footer>
</main>
<script src="/launcher.js"></script>
</body>
</html>
`;

export const LAUNCHER_JS = `(async () => {
  const form = document.getElementById("connect-form");
  const urlInput = document.getElementById("server-url");
  const tokenInput = document.getElementById("token");
  const connectButton = document.getElementById("connect");
  const projectDirInput = document.getElementById("project-dir");
  const browseButton = document.getElementById("browse");
  const startStackButton = document.getElementById("start-stack");
  const status = document.getElementById("status");
  const footer = document.getElementById("footer");
  const setStatus = (text, isError) => { status.textContent = text; status.className = isError ? "error" : ""; };

  try {
    const settings = await window.tit.getSettings();
    if (settings.lastServerUrl) urlInput.value = settings.lastServerUrl;
    if (settings.lastProjectDir) projectDirInput.value = settings.lastProjectDir;
    startStackButton.disabled = !projectDirInput.value;
    footer.textContent = "desktop " + (await window.tit.appVersion()) + " \\u00b7 " + window.tit.platform();
  } catch (err) { setStatus(String(err), true); }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const url = urlInput.value.trim();
    const token = tokenInput.value;
    tokenInput.value = "";
    connectButton.disabled = true;
    setStatus("Waiting for " + url + "/api/health \\u2026", false);
    try {
      const result = await window.tit.connect({ url, token });
      if (!result.ok) { setStatus(result.error, true); connectButton.disabled = false; }
      else setStatus("Connected. Loading \\u2026", false);
    } catch (err) { setStatus(String(err), true); connectButton.disabled = false; }
  });

  browseButton.addEventListener("click", async () => {
    const dir = await window.tit.selectDirectory();
    if (dir) {
      projectDirInput.value = dir;
      startStackButton.disabled = false;
    }
  });

  window.tit.stack.onEvent((event) => {
    if (event.type === "progress") setStatus(event.message, false);
    else if (event.type === "error") setStatus(event.message, true);
    else if (event.type === "started") setStatus("Docker stack is up" + (event.attached ? " (attached to an existing stack)" : "") + ". Loading \\u2026", false);
    else if (event.type === "stopped") setStatus("Docker stack stopped.", false);
  });

  startStackButton.addEventListener("click", async () => {
    const dir = projectDirInput.value;
    if (!dir) return;
    startStackButton.disabled = true;
    connectButton.disabled = true;
    setStatus("Starting the Docker stack \\u2026", false);
    try {
      const result = await window.tit.stack.start(dir);
      if (!result.ok) { setStatus(result.error, true); }
    } catch (err) { setStatus(String(err), true); }
    startStackButton.disabled = false;
    connectButton.disabled = false;
  });
})();
`;
