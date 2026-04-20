const viewLogin = document.getElementById("view-login");
const viewDash = document.getElementById("view-dashboard");
const formLogin = document.getElementById("form-login");
const loginError = document.getElementById("login-error");
const btnLogout = document.getElementById("btn-logout");
const welcome = document.getElementById("welcome");

function show(view) {
  viewLogin.hidden = view !== "login";
  viewDash.hidden = view !== "dashboard";
}

function setMetric(id, value, tone = "") {
  const el = document.getElementById(id);
  el.textContent = value;
  el.className = "big" + (tone ? " " + tone : "");
}

async function carregarDashboard() {
  const r = await fetch("/api/dashboard", { credentials: "same-origin" });
  if (r.status === 401) {
    show("login");
    return;
  }
  if (!r.ok) return;
  const d = await r.json();

  welcome.textContent = `${d.usuario.nome} · ${d.usuario.email}`;
  setMetric("m-ambiente", d.ambiente);
  setMetric(
    "m-obsidian",
    d.obsidian,
    d.obsidian === "online" ? "status-ok" : "status-err",
  );
  setMetric(
    "m-whisper",
    d.whisper,
    d.whisper === "ativo" ? "status-ok" : "status-warn",
  );
  setMetric(
    "m-briefing",
    d.briefing,
    d.briefing.startsWith("agendado") ? "status-ok" : "status-warn",
  );
  setMetric(
    "m-deadletter",
    String(d.dead_letter_pendentes),
    d.dead_letter_pendentes > 0 ? "status-warn" : "status-ok",
  );
  setMetric("m-whatsapp", d.whatsapp_numero);

  document.getElementById("last-update").textContent =
    "Atualizado em " + new Date().toLocaleTimeString("pt-BR");

  show("dashboard");
}

formLogin.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.hidden = true;
  const fd = new FormData(formLogin);
  const r = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({
      email: fd.get("email"),
      senha: fd.get("senha"),
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    loginError.textContent = err.detail || "Falha no login.";
    loginError.hidden = false;
    return;
  }
  formLogin.reset();
  await carregarDashboard();
});

btnLogout.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST", credentials: "same-origin" });
  show("login");
});

// boot: tenta sessão existente
(async () => {
  const r = await fetch("/api/me", { credentials: "same-origin" });
  if (r.ok) {
    await carregarDashboard();
  } else {
    show("login");
  }
})();

// auto-refresh a cada 30s quando logado
setInterval(() => {
  if (!viewDash.hidden) carregarDashboard();
}, 30000);
