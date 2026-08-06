// Scriptr Forge — toolbar plugin template
// Shows: terminal icon + count of saved scripts + a "run" indicator when one is executing.
// Polls http://localhost:8765/scriptr  (served by phoenix_status_server.py)

const SCRIPTR_URL = "http://localhost:8765/scriptr";

let sf;
try {
  sf = env.fetchJson(SCRIPTR_URL, { timeout: 500 });
} catch (_) {
  sf = null;
}

if (!sf) {
  return [icon("TbTerminal2"), " ", "–"];
}

if (!sf.available) {
  return [icon("TbTerminal2"), " ", "offline"];
}

const saved   = sf.saved_scripts ?? 0;
const running = sf.running       ?? 0;

const parts = [icon("TbTerminal2"), " ", String(saved)];

if (running > 0) {
  parts.push("  ");
  parts.push(icon("VscRunAll"));    // script actively running
  parts.push(" " + running);
}

return parts;
