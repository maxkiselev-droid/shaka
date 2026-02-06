// app.js
async function runQuery() {
  const textEl = document.getElementById("user_text");
  const rawOut = document.getElementById("raw_out");
  const capOut = document.getElementById("cap_out");
  const statusEl = document.getElementById("status");

  const text = (textEl?.value || "").trim();
  if (!text) return;

  statusEl.textContent = "Running...";

  try {
    const r = await fetch("/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    const ct = r.headers.get("content-type") || "";
    let data = null;

    if (ct.includes("application/json")) {
      data = await r.json();
    } else {
      // backend must not do this, but handle anyway
      const t = await r.text();
      throw new Error("Non-JSON response: " + t.slice(0, 200));
    }

    if (!r.ok || !data || data.ok === false) {
      throw new Error((data && data.error) ? data.error : ("HTTP " + r.status));
    }

    rawOut.textContent = data.raw ?? "";
    capOut.textContent = data.cap ?? "";

    const snap = data.wm?.snapshot;
    if (snap) {
      statusEl.textContent = `OK. WM: nodes=${snap.nodes}, edges=${snap.edges}, obs=${snap.obs}`;
    } else {
      statusEl.textContent = "OK.";
    }
  } catch (e) {
    statusEl.textContent = "ERROR: " + (e?.message || String(e));
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("run_btn");
  if (btn) btn.addEventListener("click", runQuery);

  const textEl = document.getElementById("user_text");
  if (textEl) {
    textEl.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") runQuery();
    });
  }
});
