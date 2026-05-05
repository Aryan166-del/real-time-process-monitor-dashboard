/**
 * RTOS Monitor — script.js
 * CSE316 Operating Systems Dashboard
 * Full client-side logic: real-time polling, charts, algorithm UI
 */

"use strict";

// ─────────────────────────────────────────────
// Utility helpers
// ─────────────────────────────────────────────
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

function toast(msg, type = "ok", duration = 3000) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast show" + (type === "error" ? " error" : "");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = "toast"; }, duration);
}

function fmtNum(n, dec = 1) { return Number(n).toFixed(dec); }

// GANTT colours cycle
const GANTT_COLORS = [
  "#00ff88", "#00c8ff", "#ff6b35", "#ffd600",
  "#a78bfa", "#fb7185", "#34d399", "#60a5fa",
  "#f97316", "#c084fc",
];

function ganttColor(pid) {
  const idx = Math.abs(String(pid).split("").reduce((a, c) => a + c.charCodeAt(0), 0)) % GANTT_COLORS.length;
  return GANTT_COLORS[idx];
}

// ─────────────────────────────────────────────
// Chart.js shared defaults
// ─────────────────────────────────────────────
Chart.defaults.color = "#5c7a8a";
Chart.defaults.borderColor = "#1e2e38";
Chart.defaults.font.family = "'Share Tech Mono', monospace";

function makeLineChart(canvasId, label, color) {
  const ctx = $(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label,
        data: [],
        borderColor: color,
        backgroundColor: color + "18",
        borderWidth: 1.5,
        tension: 0.3,
        fill: true,
        pointRadius: 0,
      }]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { display: false },
        y: {
          min: 0, max: 100,
          grid: { color: "#1e2e38" },
          ticks: { font: { size: 10 }, callback: v => v + "%" }
        }
      },
      plugins: { legend: { display: false } }
    }
  });
}

function makeBarChart(canvasId, labels, label, color) {
  const ctx = $(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Read MB/s", data: [], borderColor: "#00c8ff", backgroundColor: "#00c8ff18", borderWidth: 1.5, tension: 0.3, fill: true, pointRadius: 0 },
        { label: "Write MB/s", data: [], borderColor: "#ff6b35", backgroundColor: "#ff6b3518", borderWidth: 1.5, tension: 0.3, fill: true, pointRadius: 0 },
      ]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { display: false },
        y: { min: 0, grid: { color: "#1e2e38" }, ticks: { font: { size: 10 } } }
      },
      plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } }
    }
  });
}

// ─────────────────────────────────────────────
// Main App
// ─────────────────────────────────────────────
const App = (() => {

  let cpuChart, memChart, diskChart, diskHeadChart;
  let procRows = [];     // scheduling input rows
  let procIdCounter = 1;

  // ── Tab switching ──────────────────────────
  function initTabs() {
    $$(".tab-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        $$(".tab-btn").forEach(b => b.classList.remove("active"));
        $$(".tab-content").forEach(s => s.classList.remove("active"));
        btn.classList.add("active");
        $("tab-" + btn.dataset.tab).classList.add("active");
      });
    });
  }

  // ── Clock ──────────────────────────────────
  function updateClock() {
    $("clock").textContent = new Date().toLocaleTimeString("en-US", { hour12: false });
  }

  // ── Overview polling ───────────────────────
  async function pollOverview() {
    try {
      const r = await fetch("/api/overview");
      const d = await r.json();
      $("h-cpu").textContent    = fmtNum(d.cpu_percent, 1) + "%";
      $("h-mem").textContent    = fmtNum(d.mem_percent) + "%";
      $("h-disk").textContent   = fmtNum(d.disk_percent) + "%";
      $("h-procs").textContent  = d.process_count;
      $("h-uptime").textContent = d.uptime;

      $("ov-cpu").textContent      = fmtNum(d.cpu_percent) + "%";
      $("ov-cpu-bar").style.width  = d.cpu_percent + "%";
      $("ov-cpu-cores").textContent= d.cpu_cores + " cores";

      $("ov-mem").textContent      = fmtNum(d.mem_percent) + "%";
      $("ov-mem-bar").style.width  = d.mem_percent + "%";
      $("ov-mem-detail").textContent = d.mem_used_gb + " / " + d.mem_total_gb + " GB";

      $("ov-disk").textContent     = fmtNum(d.disk_percent) + "%";
      $("ov-disk-bar").style.width = d.disk_percent + "%";
      $("ov-disk-detail").textContent = d.disk_used_gb + " / " + d.disk_total_gb + " GB";

      $("ov-net").textContent      = fmtNum(d.net_sent_kbps) + " KB/s";
      $("ov-net-detail").textContent = "↑ " + fmtNum(d.net_sent_kbps) + " KB/s · ↓ " + fmtNum(d.net_recv_kbps) + " KB/s";

      $("ov-uptime").textContent   = d.uptime;
      $("ov-boot").textContent     = "boot: " + d.boot_time;
    } catch (e) { console.warn("Overview poll failed", e); }
  }

  async function pollCPU() {
    try {
      const r = await fetch("/api/cpu");
      const d = await r.json();

      // CPU chart
      if (cpuChart && d.history) {
        cpuChart.data.labels = d.history.map(h => h.t);
        cpuChart.data.datasets[0].data = d.history.map(h => h.v);
        cpuChart.update("none");
      }

      // Per-core bars — height is the raw % value (0-100 scale maps to 0-80px track)
      // We add a 2px minimum so even idle cores show a sliver (not invisible)
      const wrap = $("core-bars");
      wrap.innerHTML = "";
      (d.per_core || []).forEach((pct, i) => {
        // clamp: minimum 2px out of 80px track = ~2.5%; show real value in label
        const fillPct = Math.max(pct, 2);
        const color = pct > 80 ? "var(--danger)" : pct > 50 ? "var(--accent3)" : "var(--accent)";
        const div = document.createElement("div");
        div.className = "core-bar-item";
        div.innerHTML = `
          <div class="core-bar-track">
            <div class="core-bar-fill" style="height:${fillPct}%;background:${color}"></div>
          </div>
          <div class="core-bar-label">C${i}</div>
          <div class="core-bar-pct" style="color:${color}">${fmtNum(pct)}%</div>`;
        wrap.appendChild(div);
      });
    } catch (e) { console.warn("CPU poll failed", e); }
  }

  async function pollMemChart() {
    try {
      const r = await fetch("/api/memory");
      const d = await r.json();
      if (memChart && d.history) {
        memChart.data.labels = d.history.map(h => h.t);
        memChart.data.datasets[0].data = d.history.map(h => h.v);
        memChart.update("none");
      }
      // Memory dashboard
      $("m-used").textContent   = d.used_gb + " GB";
      $("m-free").textContent   = d.free_gb + " GB";
      $("m-cached").textContent = d.cached_gb + " GB";
      $("m-swap").textContent   = d.swap_used_gb + " GB";
      $("ram-used-bar").style.width   = d.percent + "%";
      const cachedPct = d.total_gb > 0 ? (d.cached_gb / d.total_gb * 100) : 0;
      $("ram-cached-bar").style.width = Math.min(cachedPct, 100 - d.percent) + "%";
    } catch (e) { console.warn("Mem poll failed", e); }
  }

  async function pollDisk() {
    try {
      const r = await fetch("/api/disk");
      const d = await r.json();
      // Partition cards
      const wrap = $("disk-partitions");
      if (wrap) {
        wrap.innerHTML = "";
        (d.partitions || []).forEach(p => {
          const card = document.createElement("div");
          card.className = "disk-part-card";
          card.innerHTML = `
            <div class="disk-part-name">${p.device}</div>
            <div class="disk-part-detail">${p.mountpoint} · ${p.fstype}</div>
            <div class="disk-part-detail">${p.used_gb} GB / ${p.total_gb} GB</div>
            <div class="disk-part-bar"><div class="disk-part-fill" style="width:${p.percent}%"></div></div>
            <div class="disk-part-pct">${p.percent}%</div>`;
          wrap.appendChild(card);
        });
      }
      // Disk I/O chart
      if (diskChart && d.read_history) {
        diskChart.data.labels = d.read_history.map(h => h.t);
        diskChart.data.datasets[0].data = d.read_history.map(h => h.v);
        diskChart.data.datasets[1].data = d.write_history.map(h => h.v);
        diskChart.update("none");
      }
    } catch (e) { console.warn("Disk poll failed", e); }
  }

  // ── Process table ──────────────────────────
  async function refreshProcesses() {
    try {
      const r = await fetch("/api/processes");
      const d = await r.json();
      const filter = ($("proc-filter")?.value || "").toLowerCase();
      const tbody = $("proc-tbody");
      if (!tbody) return;
      tbody.innerHTML = "";

      let procs = d.processes;
      if (filter) procs = procs.filter(p => p.name.toLowerCase().includes(filter));

      procs.forEach(p => {
        const tr = document.createElement("tr");
        const stateClass = {
          running: "status-running", sleeping: "status-sleeping",
          zombie: "status-zombie", stopped: "status-stopped", idle: "status-idle"
        }[p.status] || "";
        tr.innerHTML = `
          <td class="text-dim">${p.pid}</td>
          <td class="text-bright">${p.name}</td>
          <td class="${stateClass}">${p.status}</td>
          <td class="${p.cpu > 10 ? "text-accent" : ""}">${p.cpu}%</td>
          <td>${p.mem}%</td>
          <td>${p.priority}</td>
          <td>${p.threads}</td>
          <td class="text-dim">${p.started}</td>
          <td><button class="kill-btn" data-pid="${p.pid}" data-name="${p.name}" title="Terminate process">✕ Kill</button></td>`;
        tbody.appendChild(tr);
      });
      // Attach kill button handlers
      tbody.querySelectorAll(".kill-btn").forEach(btn => {
        btn.addEventListener("click", () => App.killProcess(+btn.dataset.pid, btn.dataset.name));
      });

      $("proc-footer").textContent = `Showing ${procs.length} / ${d.total} processes`;
    } catch (e) { toast("Failed to load processes", "error"); }
  }

  // ── Scheduling Simulator ───────────────────
  function addProcRow(pid, arrival = 0, burst = 4, priority = 1) {
    const id = pid || ("P" + procIdCounter++);
    const tbody = $("sched-input-tbody");
    const tr = document.createElement("tr");
    tr.dataset.pid = id;
    tr.innerHTML = `
      <td><input value="${id}" style="width:52px" data-field="pid"></td>
      <td><input type="number" value="${arrival}" min="0" data-field="arrival"></td>
      <td><input type="number" value="${burst}" min="1" data-field="burst"></td>
      <td><input type="number" value="${priority}" min="1" data-field="priority"></td>
      <td><button class="proc-delete-btn" onclick="App.removeProcRow(this)">✕</button></td>`;
    tbody.appendChild(tr);
  }

  function removeProcRow(btn) {
    btn.closest("tr").remove();
  }

  function loadSampleProcs() {
    $("sched-input-tbody").innerHTML = "";
    procIdCounter = 1;
    [
      ["P1", 0, 6, 3],
      ["P2", 1, 4, 1],
      ["P3", 2, 5, 4],
      ["P4", 3, 3, 2],
      ["P5", 4, 2, 5],
    ].forEach(([pid, arr, burst, pri]) => addProcRow(pid, arr, burst, pri));
  }

  function getScheduleInput() {
    const rows = $$('#sched-input-tbody tr');
    return Array.from(rows).map(tr => ({
      pid: tr.querySelector('[data-field="pid"]').value,
      arrival: +tr.querySelector('[data-field="arrival"]').value,
      burst: +tr.querySelector('[data-field="burst"]').value,
      priority: +tr.querySelector('[data-field="priority"]').value,
    }));
  }

  async function runSchedule() {
    const algo = $("sched-algo").value;
    const procs = getScheduleInput();
    if (!procs.length) { toast("Add at least one process", "error"); return; }

    const body = { processes: procs };
    if (algo === "rr") body.quantum = +$("rr-quantum").value;

    try {
      const r = await fetch("/api/schedule/" + algo, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const d = await r.json();
      if (d.error) { toast(d.error, "error"); return; }
      renderGantt(d);
      toast("Simulation complete");
    } catch (e) { toast("Simulation failed", "error"); }
  }

  function renderGantt(d) {
    const section = $("gantt-section");
    section.style.display = "block";

    // Gantt blocks
    const wrap = $("gantt-chart");
    const timeline = $("gantt-timeline");
    wrap.innerHTML = "";
    timeline.innerHTML = "";

    const total = d.gantt.reduce((m, g) => Math.max(m, g.end), 0);

    d.gantt.forEach(seg => {
      const w = Math.max(((seg.end - seg.start) / total) * 100, 2);
      const block = document.createElement("div");
      block.className = "gantt-block";
      block.style.cssText = `width:${w}%;background:${ganttColor(seg.pid)}22;border-color:${ganttColor(seg.pid)}55;color:${ganttColor(seg.pid)}`;
      block.textContent = seg.pid;
      block.title = `${seg.pid}: t=${seg.start}–${seg.end} (${seg.end - seg.start} units)`;
      wrap.appendChild(block);

      const tick = document.createElement("div");
      tick.className = "gantt-tick";
      tick.style.width = w + "%";
      tick.textContent = seg.start;
      timeline.appendChild(tick);
    });

    // Append last tick
    const last = document.createElement("div");
    last.className = "gantt-tick";
    last.textContent = total;
    timeline.appendChild(last);

    // Stats
    $("sched-stats").innerHTML = `
      <div class="sched-stat"><span class="sched-stat-label">Avg Waiting</span><span class="sched-stat-value">${d.avg_waiting} units</span></div>
      <div class="sched-stat"><span class="sched-stat-label">Avg Turnaround</span><span class="sched-stat-value">${d.avg_turnaround} units</span></div>
      ${d.quantum ? `<div class="sched-stat"><span class="sched-stat-label">Quantum</span><span class="sched-stat-value">${d.quantum}</span></div>` : ""}`;

    // Result table
    const tbody = $("sched-result-tbody");
    tbody.innerHTML = "";
    d.results.forEach(r => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="color:${ganttColor(r.pid)}">${r.pid}</td>
        <td>${r.arrival}</td><td>${r.burst}</td>
        <td>${r.start}</td><td>${r.end}</td>
        <td class="text-accent">${r.waiting}</td>
        <td class="text-accent2">${r.turnaround}</td>`;
      tbody.appendChild(tr);
    });
  }

  // ── Page Replacement ───────────────────────
  async function runPageReplacement() {
    const algo = $("pr-algo").value;
    const frames = +$("pr-frames").value;
    const raw = $("pr-pages").value.trim();
    const pages = raw.split(/\s+/).map(Number).filter(n => !isNaN(n));
    if (!pages.length) { toast("Enter a valid page reference string", "error"); return; }

    try {
      const r = await fetch("/api/page_replacement", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm: algo, frames, pages })
      });
      const d = await r.json();
      if (d.error) { toast(d.error, "error"); return; }
      renderPageReplacement(d);
      toast(`${algo.toUpperCase()}: ${d.page_faults} faults, ${d.page_hits} hits`);
    } catch (e) { toast("Page replacement failed", "error"); }
  }

  function renderPageReplacement(d) {
    $("pr-result").style.display = "block";
    $("pr-stats").innerHTML = `
      <span><span class="text-dim">Algorithm: </span><span class="text-accent">${d.algorithm}</span></span>
      <span><span class="text-dim">Frames: </span><span class="text-accent2">${d.frames}</span></span>
      <span><span class="text-dim">References: </span><span>${d.total_references}</span></span>
      <span><span class="text-danger">Page Faults: ${d.page_faults} (${d.fault_rate}%)</span></span>
      <span><span class="text-accent">Page Hits: ${d.page_hits} (${d.hit_rate}%)</span></span>`;

    // Trace table
    const table = document.createElement("table");
    table.className = "pr-trace-table";
    const header = document.createElement("tr");
    header.innerHTML = `<th>Ref</th>` + Array.from({ length: d.frames }, (_, i) => `<th>F${i}</th>`).join("") + `<th>Fault?</th>`;
    table.appendChild(header);

    d.trace.forEach(step => {
      const tr = document.createElement("tr");
      tr.className = step.fault ? "pr-fault" : "pr-hit";
      const frames = [...step.frames];
      while (frames.length < d.frames) frames.push("—");
      tr.innerHTML = `<td>${step.page}</td>` +
        frames.map(f => `<td>${f !== undefined ? f : "—"}</td>`).join("") +
        `<td>${step.fault ? "✗ FAULT" : "✓ HIT"}</td>`;
      table.appendChild(tr);
    });

    $("pr-trace").innerHTML = "";
    $("pr-trace").appendChild(table);
  }

  // ── Banker's Algorithm ─────────────────────
  async function runBankers() {
    const avail = $("bk-available").value.trim().split(/\s+/).map(Number);
    const allocLines = $("bk-allocation").value.trim().split("\n").filter(Boolean);
    const maxLines = $("bk-max").value.trim().split("\n").filter(Boolean);

    const allocation = allocLines.map(l => l.trim().split(/\s+/).map(Number));
    const max = maxLines.map(l => l.trim().split(/\s+/).map(Number));
    const processes = allocation.map((_, i) => "P" + i);

    if (allocation.length !== max.length) {
      toast("Allocation and Max must have same number of rows", "error"); return;
    }

    try {
      const r = await fetch("/api/bankers", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ processes, available: avail, allocation, max })
      });
      const d = await r.json();
      if (d.error) { toast(d.error, "error"); return; }
      renderBankers(d);
    } catch (e) { toast("Banker's algorithm failed", "error"); }
  }

  function renderBankers(d) {
    $("bk-result").style.display = "block";
    const safeClass = d.safe ? "result-safe" : "result-unsafe";
    const safeText = d.safe
      ? `✓ SAFE STATE — Safe Sequence: ${d.safe_sequence.join(" → ")}`
      : `✗ UNSAFE STATE — System may deadlock`;

    let html = `<div class="${safeClass}">${safeText}</div>`;

    html += `<div style="overflow-x:auto"><table class="matrix-table">
      <tr><th>Process</th><th colspan="${d.available.length}">Allocation</th><th colspan="${d.available.length}">Max</th><th colspan="${d.available.length}">Need</th></tr>`;
    d.processes.forEach((p, i) => {
      html += `<tr><td>${p}</td>
        ${d.allocation[i].map(v => `<td>${v}</td>`).join("")}
        ${d.max[i].map(v => `<td>${v}</td>`).join("")}
        ${d.need[i].map(v => `<td>${v}</td>`).join("")}</tr>`;
    });
    html += `<tr><th>Available</th>${d.available.map(v => `<td>${v}</td>`).join("")}<td colspan="${d.available.length * 2}">—</td></tr>`;
    html += `</table></div>`;
    $("bk-result").innerHTML = html;
    toast(d.safe ? "Safe state found" : "Unsafe state detected", d.safe ? "ok" : "error");
  }

  // ── Deadlock Detection ─────────────────────
  async function runDeadlockDetect() {
    const procs = $("rag-procs").value.trim().split(",").map(s => s.trim()).filter(Boolean);
    const res = $("rag-res").value.trim().split(",").map(s => s.trim()).filter(Boolean);
    const edgeLines = $("rag-edges").value.trim().split("\n").filter(Boolean);
    const edges = edgeLines.map(l => {
      const [from, to] = l.split("→").map(s => s.trim());
      return { from, to };
    });

    try {
      const r = await fetch("/api/deadlock_detect", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ processes: procs, resources: res, edges })
      });
      const d = await r.json();
      const wrap = $("rag-result");
      wrap.style.display = "block";
      if (d.deadlock) {
        wrap.innerHTML = `<div class="result-unsafe">✗ DEADLOCK DETECTED — Cycle involves: ${d.cycle_nodes.join(", ")}</div>
          <div class="text-dim" style="margin-top:.5rem;font-size:.72rem">Edges: ${edges.map(e=>e.from+"→"+e.to).join(", ")}</div>`;
        toast("Deadlock detected!", "error");
      } else {
        wrap.innerHTML = `<div class="result-safe">✓ NO DEADLOCK — System is in a safe state</div>`;
        toast("No deadlock found");
      }
    } catch (e) { toast("Detection failed", "error"); }
  }

  // ── Disk Scheduling ─────────────────────────
  async function runDiskSchedule() {
    const algo = $("ds-algo").value;
    const head = +$("ds-head").value;
    const raw = $("ds-requests").value.trim().split(/\s+/).map(Number).filter(n => !isNaN(n));
    if (!raw.length) { toast("Enter disk requests", "error"); return; }

    try {
      const r = await fetch("/api/disk_schedule", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm: algo, head, requests: raw, disk_size: 200 })
      });
      const d = await r.json();
      if (d.error) { toast(d.error, "error"); return; }
      renderDiskSchedule(d);
      toast(`Total head movement: ${d.total_movement} cylinders`);
    } catch (e) { toast("Disk schedule failed", "error"); }
  }

  function renderDiskSchedule(d) {
    $("ds-result").style.display = "block";
    $("ds-stats").innerHTML = `
      <span><span class="text-dim">Algorithm: </span><span class="text-accent">${d.algorithm}</span></span>
      <span><span class="text-dim">Initial Head: </span><span class="text-accent2">${d.head}</span></span>
      <span><span class="text-dim">Total Movement: </span><span class="text-accent">${d.total_movement} cylinders</span></span>`;

    // Sequence display
    const wrap = $("ds-sequence");
    wrap.innerHTML = "";
    d.sequence.forEach((pos, i) => {
      if (i > 0) {
        const arrow = document.createElement("span");
        arrow.className = "disk-seq-arrow";
        arrow.textContent = " → ";
        wrap.appendChild(arrow);
      }
      const item = document.createElement("span");
      item.className = "disk-seq-item";
      item.textContent = pos;
      if (i === 0) item.style.borderColor = "var(--accent)";
      wrap.appendChild(item);
    });

    // Head movement chart
    const ctx = $("diskHeadChart").getContext("2d");
    if (diskHeadChart) diskHeadChart.destroy();
    diskHeadChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: d.sequence.map((_, i) => i === 0 ? "Start" : "R" + i),
        datasets: [{
          label: "Head Position",
          data: d.sequence,
          borderColor: "#ffd600",
          backgroundColor: "rgba(255,214,0,0.1)",
          borderWidth: 2,
          tension: 0,
          fill: true,
          pointRadius: 4,
          pointBackgroundColor: "#ffd600",
        }]
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { color: "#1e2e38" } },
          y: { min: 0, max: 200, grid: { color: "#1e2e38" }, ticks: { font: { size: 10 } } }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  // ── IPC Monitor ────────────────────────────
  async function refreshIPC() {
    try {
      const r = await fetch("/api/ipc");
      const d = await r.json();
      $("ipc-summary").innerHTML = `
        <span><span class="ipc-stat-label">Connections: </span><span class="ipc-stat-val">${d.total_connections}</span></span>
        <span><span class="ipc-stat-label">Total Threads: </span><span class="ipc-stat-val">${d.total_threads}</span></span>
        <span><span class="ipc-stat-label">Snapshot: </span><span class="ipc-stat-val">${new Date(d.timestamp).toLocaleTimeString()}</span></span>`;

      const tbody = $("ipc-tbody");
      tbody.innerHTML = "";
      (d.connections || []).forEach(c => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="text-accent2">${c.type}</td>
          <td class="text-dim">${c.local}</td>
          <td>${c.remote}</td>
          <td class="${c.status === "ESTABLISHED" ? "status-running" : "status-sleeping"}">${c.status}</td>
          <td class="text-dim">${c.pid || "—"}</td>`;
        tbody.appendChild(tr);
      });
    } catch (e) { toast("IPC refresh failed", "error"); }
  }

  // ── Producer-Consumer ──────────────────────
  async function runProducerConsumer() {
    const body = {
      buffer_size: +$("pc-buffer").value,
      producers: +$("pc-producers").value,
      consumers: +$("pc-consumers").value,
      steps: +$("pc-steps").value,
    };
    try {
      const r = await fetch("/api/producer_consumer", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const d = await r.json();
      const wrap = $("pc-result");
      wrap.style.display = "block";
      wrap.innerHTML = "";
      d.log.forEach(entry => {
        const div = document.createElement("div");
        div.className = "log-entry " + entry.state;
        div.innerHTML = `
          <span class="log-step">#${entry.step}</span>
          <span class="log-actor">${entry.actor}</span>
          <span class="log-action">${entry.action}</span>
          <span class="log-buffer">[${entry.buffer.join(",")}]</span>`;
        wrap.appendChild(div);
      });
      toast("Producer-Consumer simulation done");
    } catch (e) { toast("Simulation failed", "error"); }
  }

  // ── Dining Philosophers ────────────────────
  async function runDiningPhilosophers() {
    const body = { philosophers: +$("dp-n").value, steps: +$("dp-steps").value };
    try {
      const r = await fetch("/api/dining_philosophers", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const d = await r.json();
      const wrap = $("dp-result");
      wrap.style.display = "block";
      wrap.innerHTML = "";
      d.log.forEach(entry => {
        const div = document.createElement("div");
        const blocked = entry.action.includes("blocked");
        div.className = "log-entry " + (blocked ? "blocked" : "ok");
        div.innerHTML = `
          <span class="log-step">#${entry.step}</span>
          <span class="log-actor">P${entry.philosopher}</span>
          <span class="log-action">${entry.action}</span>
          <span class="log-buffer">[${entry.states.join(",")}]</span>`;
        wrap.appendChild(div);
      });
      toast("Dining Philosophers simulation done");
    } catch (e) { toast("Simulation failed", "error"); }
  }

  // ── Initialization ─────────────────────────
  function init() {
    initTabs();

    // Charts
    cpuChart  = makeLineChart("cpuChart", "CPU %", "#00ff88");
    memChart  = makeLineChart("memChart", "MEM %", "#00c8ff");
    diskChart = makeBarChart("diskChart", [], "Disk", "#ff6b35");

    // Clock
    updateClock();
    setInterval(updateClock, 1000);

    // Filter input
    const filter = $("proc-filter");
    if (filter) filter.addEventListener("input", refreshProcesses);

    // Algo selector
    $("sched-algo")?.addEventListener("change", e => {
      $("quantum-row").style.display = e.target.value === "rr" ? "flex" : "none";
    });

    // Seed scheduling input
    loadSampleProcs();

    // Polling
    pollOverview();
    pollCPU();
    pollMemChart();
    pollDisk();
    refreshProcesses();
    refreshIPC();

    setInterval(pollOverview,   3000);
    setInterval(pollCPU,        2000);
    setInterval(pollMemChart,   3000);
    setInterval(pollDisk,       5000);
    setInterval(refreshProcesses, 5000);
    setInterval(refreshIPC,      10000);
  }

  // ── Kill Process ──────────────────────────────
  async function killProcess(pid, name) {
    if (!confirm(`Terminate PID ${pid} (${name})? This cannot be undone.`)) return;
    try {
      const r = await fetch("/api/kill_process", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pid })
      });
      const d = await r.json();
      if (!r.ok || d.error) {
        toast(d.error || "Kill failed", "error");
      } else {
        toast(`Killed PID ${pid} (${d.name})`);
        setTimeout(refreshProcesses, 400);
      }
    } catch (e) { toast("Kill request failed", "error"); }
  }

  // Public API
  return {
    init,
    refreshProcesses,
    refreshIPC,
    killProcess,
    addProcRow,
    removeProcRow,
    loadSampleProcs,
    runSchedule,
    runPageReplacement,
    runBankers,
    runDeadlockDetect,
    runDiskSchedule,
    runProducerConsumer,
    runDiningPhilosophers,
  };

})();

document.addEventListener("DOMContentLoaded", App.init);