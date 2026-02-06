// wm.js
let timer = null;

async function refresh() {
  const meta = document.getElementById("meta");
  const body = document.getElementById("edges_body");
  const raw = document.getElementById("raw_json");

  meta.textContent = "Loading...";

  try {
    const r = await fetch("/wm");
    const data = await r.json();
    if (!r.ok || data.ok === false) throw new Error(data.error || ("HTTP " + r.status));

    const wm = data.wm;
    const snap = wm.snapshot;
    meta.textContent = `nodes=${snap.nodes}, edges=${snap.edges}, obs=${snap.obs}`;

    body.innerHTML = "";
    for (const e of (wm.top_edges || [])) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(e.src)}</td><td>${escapeHtml(e.rel)}</td><td>${escapeHtml(e.dst)}</td><td>${e.w.toFixed(2)}</td><td>${e.n}</td>`;
      body.appendChild(tr);
    }

    raw.textContent = JSON.stringify(wm, null, 2);
  } catch (e) {
    meta.textContent = "ERROR: " + (e?.message || String(e));
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setAuto(on) {
  if (timer) { clearInterval(timer); timer = null; }
  if (on) timer = setInterval(refresh, 2000);
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh_btn").addEventListener("click", refresh);
  document.getElementById("auto_chk").addEventListener("change", (e) => setAuto(e.target.checked));
  refresh();
});
