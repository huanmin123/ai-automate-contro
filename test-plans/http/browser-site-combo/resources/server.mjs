import http from "node:http";

const port = 43127;
const accounts = [
  { id: "A-100", name: "Alpha Admin", role: "owner", amount: "13" },
  { id: "B-200", name: "Beta Ops", role: "operator", amount: "17" },
  { id: "C-300", name: "Gamma QA", role: "auditor", amount: "12" }
];
const sessions = new Map();
const audits = new Map();

function htmlPage() {
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Browser Site Combo Fixture</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 32px; color: #1f2937; }
    label { display: block; margin: 10px 0; }
    input { padding: 6px 8px; min-width: 260px; }
    button { padding: 8px 12px; margin-top: 8px; }
    table { border-collapse: collapse; margin-top: 20px; min-width: 560px; }
    th, td { border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }
    #dashboard[hidden] { display: none; }
    #login-status { margin-top: 14px; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>Browser Site Combo Fixture</h1>
  <form id="login-form">
    <label>Account <input id="account" name="account" autocomplete="username" /></label>
    <label>Password <input id="password" name="password" type="password" autocomplete="current-password" /></label>
    <label>Token <input id="token" name="token" /></label>
    <button id="login-btn" type="submit">登录并加载账户</button>
  </form>
  <div id="login-status" data-state="idle">等待登录</div>
  <section id="dashboard" hidden>
    <h2>账户表</h2>
    <table id="accounts">
      <thead>
        <tr><th>id</th><th>name</th><th>role</th><th>amount</th></tr>
      </thead>
      <tbody></tbody>
    </table>
    <div id="total-result"></div>
  </section>
  <script>
    const form = document.querySelector("#login-form");
    const status = document.querySelector("#login-status");
    const dashboard = document.querySelector("#dashboard");
    const tbody = document.querySelector("#accounts tbody");
    const totalResult = document.querySelector("#total-result");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        account: document.querySelector("#account").value,
        password: document.querySelector("#password").value,
        token: document.querySelector("#token").value
      };
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      window.localStorage.setItem("sessionId", data.session_id);
      status.dataset.state = data.ok ? "logged-in" : "failed";
      status.textContent = "登录成功 account=" + data.account + " token=" + data.token + " session=" + data.session_id;
      tbody.innerHTML = data.accounts.map((item) => (
        "<tr data-id=\\"" + item.id + "\\">" +
        "<td>" + item.id + "</td>" +
        "<td>" + item.name + "</td>" +
        "<td>" + item.role + "</td>" +
        "<td>" + item.amount + "</td>" +
        "</tr>"
      )).join("");
      const total = data.accounts.reduce((sum, item) => sum + Number(item.amount), 0);
      totalResult.textContent = "total=" + total;
      dashboard.hidden = false;
    });
  </script>
</body>
</html>`;
}

function send(res, status, body, headers = {}) {
  const buffer = Buffer.from(body);
  res.writeHead(status, {
    "content-length": buffer.length,
    ...headers
  });
  res.end(buffer);
}

function sendJson(res, status, payload) {
  send(res, status, JSON.stringify(payload), { "content-type": "application/json; charset=utf-8" });
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString("utf8");
  return text ? JSON.parse(text) : {};
}

function accountById(id) {
  return accounts.find((item) => item.id === id);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "127.0.0.1"}`);
  const parts = url.pathname.split("/").filter(Boolean);

  if (req.method === "GET" && url.pathname === "/") {
    send(res, 200, htmlPage(), { "content-type": "text/html; charset=utf-8" });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/login") {
    const payload = await readJson(req);
    const sessionId = `session-${payload.account}-${payload.token}`;
    sessions.set(sessionId, {
      account: payload.account,
      password: payload.password,
      token: payload.token
    });
    sendJson(res, 200, {
      ok: true,
      account: payload.account,
      password: payload.password,
      token: payload.token,
      session_id: sessionId,
      accounts
    });
    return;
  }

  if (req.method === "GET" && parts[0] === "api" && parts[1] === "account" && parts[2]) {
    const item = accountById(parts[2]);
    if (!item) {
      sendJson(res, 404, { ok: false, error: "not found" });
      return;
    }
    sendJson(res, 200, {
      ok: true,
      ...item,
      query: Object.fromEntries(url.searchParams)
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/audit") {
    const payload = await readJson(req);
    const auth = String(req.headers.authorization ?? "");
    const sessionHeader = String(req.headers["x-session-id"] ?? "");
    const passwordHeader = String(req.headers["x-raw-password"] ?? "");
    const auditId = `audit-${audits.size + 1}`;
    const ok = (
      auth === `Bearer ${payload.token}` &&
      sessionHeader === payload.session_id &&
      passwordHeader === payload.password &&
      Number(payload.count) === accounts.length &&
      Number(payload.total) === 42 &&
      Array.isArray(payload.ids) &&
      payload.ids.join("|") === accounts.map((item) => item.id).join("|")
    );
    const record = {
      audit_id: auditId,
      ok,
      headers: { authorization: auth, "x-session-id": sessionHeader, "x-raw-password": passwordHeader },
      received: payload
    };
    audits.set(auditId, record);
    sendJson(res, 200, record);
    return;
  }

  if (req.method === "GET" && parts[0] === "api" && parts[1] === "audit" && parts[2]) {
    const record = audits.get(parts[2]);
    if (!record) {
      sendJson(res, 404, { ok: false, error: "not found" });
      return;
    }
    sendJson(res, 200, {
      ...record,
      query: Object.fromEntries(url.searchParams)
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/finalize") {
    const payload = await readJson(req);
    const audit = audits.get(payload.audit_id);
    const ok = Boolean(
      audit &&
      audit.ok &&
      String(req.headers.authorization ?? "") === `Bearer ${audit.received.token}` &&
      payload.session_id === audit.received.session_id &&
      Number(payload.line_count) === accounts.length &&
      payload.joined === accounts.map((item) => item.id).join("|") &&
      Number(payload.lookup_total) === 42
    );
    sendJson(res, 200, { ok, received: payload });
    return;
  }

  sendJson(res, 404, { ok: false, error: "not found", method: req.method, path: url.pathname });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`browser site combo fixture listening on ${port}`);
});
