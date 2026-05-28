/**
 * SDLS v3 — Core App JS
 * Handles: theme, sidebar, UTC clock, Redis registry polling,
 * dynamic node/service sidebar, live Socket.IO connection, queue depth.
 */
(function () {
  "use strict";

  /* ── Theme ────────────────────────────────────────────────────────── */
  const root = document.documentElement;
  const THEME_KEY = "sdls_theme";

  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    localStorage.setItem(THEME_KEY, t);
    const icon = document.querySelector(".theme-icon");
    if (icon) icon.textContent = t === "dark" ? "☀" : "☾";
  }

  (function initTheme() {
    const saved = localStorage.getItem(THEME_KEY) || "dark";
    applyTheme(saved);
    const btn = document.getElementById("themeToggle");
    if (btn) btn.addEventListener("click", () => {
      applyTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
  })();

  /* ── Sidebar mobile ───────────────────────────────────────────────── */
  (function initSidebar() {
    const sidebar  = document.getElementById("sidebar");
    const overlay  = document.getElementById("sidebarOverlay");
    const hamburger = document.getElementById("hamburger");
    if (!sidebar || !hamburger) return;

    function open() { sidebar.classList.add("open"); overlay.classList.add("active"); }
    function close() { sidebar.classList.remove("open"); overlay.classList.remove("active"); }

    hamburger.addEventListener("click", () => sidebar.classList.contains("open") ? close() : open());
    overlay.addEventListener("click", close);
  })();

  /* ── UTC Clock ────────────────────────────────────────────────────── */
  function updateClock() {
    const now = new Date();
    const utc = now.toISOString().replace("T", " ").slice(0, 19) + " UTC";
    const el = document.getElementById("utcClock");
    if (el) el.textContent = utc;
    const localEl = document.getElementById("localTime");
    if (localEl) localEl.textContent = now.toLocaleTimeString();
    const syncEl = document.getElementById("syncedUtc");
    if (syncEl) syncEl.textContent = now.toISOString().slice(11, 19) + " UTC";
  }
  updateClock();
  setInterval(updateClock, 1000);

  /* ── Dynamic service-map (resolved via /api/service-map) ─────────── */
  window.SDLS = window.SDLS || {};
  window.SDLS.serviceMap = {};
  window.SDLS.getUrl = function (name) {
    return window.SDLS.serviceMap[name] || "";
  };

  async function loadServiceMap() {
    try {
      const r = await fetch("/api/service-map");
      if (r.ok) {
        const d = await r.json();
        if (d.success) window.SDLS.serviceMap = d.services;
      }
    } catch (e) { /* silently ignore */ }
  }
  loadServiceMap();
  setInterval(loadServiceMap, 30000);

  /* ── Registry / sidebar nodes ─────────────────────────────────────── */
  const ROLE_CLASS = { system1: "sys1", system2: "sys2", system3: "sys3", infra: "infra", unknown: "infra" };
  const ROLE_LABEL = { system1: "SYS1", system2: "SYS2", system3: "SYS3", infra: "INFRA" };

  async function refreshRegistry() {
    const nodeList = document.getElementById("nodeList");
    const svcList  = document.getElementById("svcList");
    if (!nodeList) return;

    let reg = {};
    try {
      const r = await fetch("/api/registry");
      if (r.ok) { const d = await r.json(); if (d.success) reg = d.data; }
    } catch (e) { return; }

    // Build per-role node groups
    const byRole = {};
    for (const [name, info] of Object.entries(reg)) {
      const role = info.role || "unknown";
      if (!byRole[role]) byRole[role] = [];
      byRole[role].push({ name, ...info });
    }

    // Render EC2 nodes (one per role = one physical/logical node)
    const roles = [...new Set(Object.values(reg).map(i => i.role || "unknown"))].sort();
    nodeList.innerHTML = roles.length ? "" : '<div class="node-placeholder">No nodes registered</div>';
    for (const role of roles) {
      const services = byRole[role] || [];
      const host = services[0]?.host || "—";
      const cls  = ROLE_CLASS[role] || "infra";
      const lbl  = ROLE_LABEL[role] || role.toUpperCase();
      const row = document.createElement("div");
      row.className = "node-row";
      row.innerHTML = `
        <span class="node-badge ${cls}">${lbl}</span>
        <span class="node-ip">${host}</span>
        <span class="node-status-dot up"></span>`;
      nodeList.appendChild(row);
    }

    // Render service list
    if (svcList) {
      const entries = Object.entries(reg);
      svcList.innerHTML = entries.length ? "" : '<div class="node-placeholder">No services</div>';
      for (const [name, info] of entries) {
        const cls = ROLE_CLASS[info.role || "unknown"];
        const row = document.createElement("div");
        row.className = "node-row";
        row.innerHTML = `
          <span class="node-badge ${cls}" style="font-size:8px;padding:1px 4px">${String(info.port || "")}</span>
          <span class="node-ip">${name}</span>
          <span class="node-status-dot up" title="Registered"></span>`;
        svcList.appendChild(row);
      }
    }

    // Update global cluster dot
    const count = Object.keys(reg).length;
    const dot = document.getElementById("globalDot");
    const txt = document.getElementById("globalStatusText");
    if (dot) {
      dot.className = "clock-dot " + (count > 6 ? "healthy" : count > 3 ? "degraded" : "critical");
    }
    if (txt) txt.textContent = `${count} service${count !== 1 ? "s" : ""} registered`;

    // Update active nodes count if element exists
    const anEl = document.getElementById("activeNodes");
    if (anEl) anEl.textContent = `${count}/11`;
  }

  refreshRegistry();
  setInterval(refreshRegistry, 15000);

  /* ── Redis queue depth (via coordinator) ──────────────────────────── */
  async function pollQueueDepth() {
    const qEl   = document.getElementById("queueLen");
    const qPill = document.getElementById("queuePill");
    try {
      const coordUrl = window.SDLS.getUrl("coordinator");
      if (!coordUrl) return;
      const r = await fetch(`${coordUrl}/api/cluster/state`);
      if (!r.ok) return;
      const d = await r.json();
      const services = d.data?.services || {};
      // Derive queue depth from coordinator state if available
      const qLen = d.data?.queue_depth ?? "—";
      if (qEl) qEl.textContent = qLen;
      if (qPill) qPill.textContent = `Q: ${qLen}`;
    } catch (e) { /* ignore */ }
  }
  setTimeout(() => { pollQueueDepth(); setInterval(pollQueueDepth, 10000); }, 5000);

  /* ── Socket.IO live log feed ──────────────────────────────────────── */
  window.SDLS.socket = null;
  window.SDLS.liveLog = [];

  function connectSocket() {
    const logUrl = window.SDLS.getUrl("logging-service");
    if (!logUrl) { setTimeout(connectSocket, 3000); return; }
    try {
      const socket = io(logUrl, { transports: ["websocket", "polling"], reconnectionDelay: 2000 });
      window.SDLS.socket = socket;

      socket.on("connect", () => console.log("[SDLS] Socket.IO connected"));
      socket.on("disconnect", () => console.log("[SDLS] Socket.IO disconnected"));

      socket.on("new_log", (entry) => {
        window.SDLS.liveLog.unshift(entry);
        if (window.SDLS.liveLog.length > 500) window.SDLS.liveLog.pop();
        // Notify listeners
        if (typeof window.SDLS.onNewLog === "function") window.SDLS.onNewLog(entry);
        // Update error badge
        if (entry.status === "ERROR") {
          const badge = document.getElementById("errorBadge");
          if (badge) {
            const cur = parseInt(badge.textContent) || 0;
            badge.textContent = cur + 1;
            badge.style.display = "";
          }
        }
      });
    } catch (e) { setTimeout(connectSocket, 5000); }
  }

  // Connect after service map is loaded
  setTimeout(connectSocket, 2000);

  /* ── Helper: format timestamp ─────────────────────────────────────── */
  window.SDLS.fmtTs = function (ts) {
    if (!ts) return "—";
    try { return new Date(ts).toISOString().slice(11, 23); }
    catch (e) { return ts; }
  };

  /* ── Helper: status badge HTML ────────────────────────────────────── */
  window.SDLS.badge = function (status) {
    const map = { SUCCESS: "success", ERROR: "error", WARNING: "warning", INFO: "info" };
    const cls = map[status] || "info";
    return `<span class="badge badge-${cls}">${status}</span>`;
  };

  /* ── Simulate orders (calls API gateway) ─────────────────────────── */
  window.simulateOrders = async function (n = 5) {
    const gwUrl = window.SDLS.getUrl("api-gateway");
    if (!gwUrl) { alert("API Gateway not yet discovered"); return; }
    let ok = 0;
    for (let i = 0; i < n; i++) {
      try {
        await fetch(`${gwUrl}/api/order`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ item: "widget-" + i, qty: Math.ceil(Math.random() * 5), price: +(Math.random() * 100).toFixed(2) }),
        });
        ok++;
      } catch (e) { /* ignore */ }
      await new Promise(r => setTimeout(r, 80));
    }
    console.log(`[SDLS] Simulated ${ok}/${n} orders`);
  };

})();
