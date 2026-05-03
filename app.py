"""
Real-Time OS Monitoring System — app.py
CSE316 Operating Systems | CA2 Project
Full Flask backend: live metrics, algorithm simulations, IPC monitoring
"""

import os
import json
import time
import math
import threading
import logging
import psutil
from collections import deque, defaultdict
from datetime import datetime
from flask import Flask, render_template, jsonify, request

# ─────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "rtos-monitor-secret-2024")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# In-memory metric ring buffers (last 60 samples)
# ─────────────────────────────────────────────
HISTORY_LEN = 60
cpu_history = deque(maxlen=HISTORY_LEN)
mem_history = deque(maxlen=HISTORY_LEN)
disk_read_history = deque(maxlen=HISTORY_LEN)
disk_write_history = deque(maxlen=HISTORY_LEN)
_prev_disk = None
_lock = threading.Lock()


def _sample_metrics():
    """Background thread: sample every second."""
    global _prev_disk
    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            disk_io = psutil.disk_io_counters()
            ts = datetime.now().strftime("%H:%M:%S")

            read_rate = write_rate = 0
            if _prev_disk and disk_io:
                read_rate = max(0, (disk_io.read_bytes - _prev_disk.read_bytes) / 1024 / 1024)
                write_rate = max(0, (disk_io.write_bytes - _prev_disk.write_bytes) / 1024 / 1024)
            _prev_disk = disk_io

            with _lock:
                cpu_history.append({"t": ts, "v": cpu})
                mem_history.append({"t": ts, "v": mem})
                disk_read_history.append({"t": ts, "v": round(read_rate, 3)})
                disk_write_history.append({"t": ts, "v": round(write_rate, 3)})
        except Exception as e:
            logger.warning(f"Metric sample error: {e}")
        time.sleep(1)


_sampler = threading.Thread(target=_sample_metrics, daemon=True)
_sampler.start()


# ═══════════════════════════════════════════════════════════════
# MODULE 1 — PROCESS & CPU
# ═══════════════════════════════════════════════════════════════

@app.route("/api/processes")
def api_processes():
    """Live process table: PID, name, state, CPU%, MEM%, priority."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "status", "cpu_percent",
                                   "memory_percent", "nice", "num_threads", "create_time"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "—",
                "status": info["status"],
                "cpu": round(info["cpu_percent"] or 0, 2),
                "mem": round(info["memory_percent"] or 0, 2),
                "priority": info["nice"],
                "threads": info["num_threads"],
                "started": datetime.fromtimestamp(info["create_time"]).strftime("%H:%M:%S")
                if info["create_time"] else "—"
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return jsonify({"processes": procs[:80], "total": len(procs)})


@app.route("/api/cpu")
def api_cpu():
    """CPU overview: per-core, frequency, load-avg, history."""
    per_core = psutil.cpu_percent(percpu=True)
    freq = psutil.cpu_freq()
    try:
        load = [round(x / psutil.cpu_count() * 100, 1) for x in psutil.getloadavg()]
    except AttributeError:
        load = [0, 0, 0]
    with _lock:
        hist = list(cpu_history)
    return jsonify({
        "overall": psutil.cpu_percent(),
        "per_core": per_core,
        "count": psutil.cpu_count(),
        "freq_mhz": round(freq.current, 0) if freq else 0,
        "freq_max": round(freq.max, 0) if freq else 0,
        "load_avg": load,
        "history": hist,
    })


# ── CPU Scheduling Algorithms ─────────────────────────────────

def _build_gantt(schedule):
    """Convert raw schedule list to Gantt segments merging consecutive same-pid."""
    if not schedule:
        return []
    gantt = []
    cur = schedule[0].copy()
    for s in schedule[1:]:
        if s["pid"] == cur["pid"]:
            cur["end"] = s["end"]
        else:
            gantt.append(cur)
            cur = s.copy()
    gantt.append(cur)
    return gantt


@app.route("/api/schedule/fcfs", methods=["POST"])
def api_fcfs():
    """FCFS scheduling."""
    data = request.get_json(force=True)
    processes = data.get("processes", [])
    if not processes:
        return jsonify({"error": "No processes provided"}), 400

    procs = sorted(processes, key=lambda p: p["arrival"])
    t = 0
    results, schedule = [], []
    for p in procs:
        t = max(t, p["arrival"])
        start = t
        end = t + p["burst"]
        results.append({
            "pid": p["pid"], "arrival": p["arrival"], "burst": p["burst"],
            "start": start, "end": end,
            "waiting": start - p["arrival"],
            "turnaround": end - p["arrival"],
        })
        schedule.append({"pid": p["pid"], "start": start, "end": end})
        t = end

    avg_wt = sum(r["waiting"] for r in results) / len(results)
    avg_tat = sum(r["turnaround"] for r in results) / len(results)
    return jsonify({"results": results, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2)})


@app.route("/api/schedule/sjf", methods=["POST"])
def api_sjf():
    """SJF Non-Preemptive."""
    data = request.get_json(force=True)
    processes = data.get("processes", [])
    if not processes:
        return jsonify({"error": "No processes provided"}), 400

    remaining = [dict(p) for p in processes]
    completed, schedule = [], []
    t = 0
    done = set()
    while len(done) < len(remaining):
        available = [p for p in remaining if p["arrival"] <= t and p["pid"] not in done]
        if not available:
            t += 1
            continue
        p = min(available, key=lambda x: x["burst"])
        start = t
        end = t + p["burst"]
        completed.append({
            "pid": p["pid"], "arrival": p["arrival"], "burst": p["burst"],
            "start": start, "end": end,
            "waiting": start - p["arrival"],
            "turnaround": end - p["arrival"],
        })
        schedule.append({"pid": p["pid"], "start": start, "end": end})
        done.add(p["pid"])
        t = end

    avg_wt = sum(r["waiting"] for r in completed) / len(completed)
    avg_tat = sum(r["turnaround"] for r in completed) / len(completed)
    return jsonify({"results": completed, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2)})


@app.route("/api/schedule/rr", methods=["POST"])
def api_rr():
    """Round-Robin scheduling."""
    data = request.get_json(force=True)
    processes = data.get("processes", [])
    quantum = int(data.get("quantum", 2))
    if not processes:
        return jsonify({"error": "No processes provided"}), 400

    remaining = {p["pid"]: p["burst"] for p in processes}
    arrival = {p["pid"]: p["arrival"] for p in processes}
    burst_orig = {p["pid"]: p["burst"] for p in processes}
    start_time = {}
    finish_time = {}

    queue = deque()
    procs_sorted = sorted(processes, key=lambda p: p["arrival"])
    t = 0
    idx = 0
    schedule = []
    in_queue = set()

    if procs_sorted:
        t = procs_sorted[0]["arrival"]
        queue.append(procs_sorted[0]["pid"])
        in_queue.add(procs_sorted[0]["pid"])
        idx = 1

    while queue or idx < len(procs_sorted):
        if not queue:
            t = procs_sorted[idx]["arrival"]
            queue.append(procs_sorted[idx]["pid"])
            in_queue.add(procs_sorted[idx]["pid"])
            idx += 1

        pid = queue.popleft()
        in_queue.discard(pid)
        if pid not in start_time:
            start_time[pid] = t
        run = min(quantum, remaining[pid])
        schedule.append({"pid": pid, "start": t, "end": t + run})
        t += run
        remaining[pid] -= run

        # Enqueue newly arrived
        while idx < len(procs_sorted) and procs_sorted[idx]["arrival"] <= t:
            p2 = procs_sorted[idx]["pid"]
            if p2 not in in_queue and remaining[p2] > 0:
                queue.append(p2)
                in_queue.add(p2)
            idx += 1

        if remaining[pid] > 0:
            queue.append(pid)
            in_queue.add(pid)
        else:
            finish_time[pid] = t

    results = []
    for p in processes:
        pid = p["pid"]
        ft = finish_time.get(pid, t)
        wt = ft - arrival[pid] - burst_orig[pid]
        results.append({
            "pid": pid, "arrival": arrival[pid], "burst": burst_orig[pid],
            "start": start_time.get(pid, 0), "end": ft,
            "waiting": max(0, wt), "turnaround": ft - arrival[pid]
        })

    avg_wt = sum(r["waiting"] for r in results) / len(results)
    avg_tat = sum(r["turnaround"] for r in results) / len(results)
    return jsonify({"results": results, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2),
                    "quantum": quantum})


@app.route("/api/schedule/priority", methods=["POST"])
def api_priority():
    """Priority Non-Preemptive scheduling (lower number = higher priority)."""
    data = request.get_json(force=True)
    processes = data.get("processes", [])
    if not processes:
        return jsonify({"error": "No processes provided"}), 400

    remaining = [dict(p) for p in processes]
    completed, schedule = [], []
    t = 0
    done = set()
    while len(done) < len(remaining):
        available = [p for p in remaining if p["arrival"] <= t and p["pid"] not in done]
        if not available:
            t += 1
            continue
        p = min(available, key=lambda x: x.get("priority", 0))
        start = t
        end = t + p["burst"]
        completed.append({
            "pid": p["pid"], "arrival": p["arrival"], "burst": p["burst"],
            "priority": p.get("priority", 0),
            "start": start, "end": end,
            "waiting": start - p["arrival"],
            "turnaround": end - p["arrival"],
        })
        schedule.append({"pid": p["pid"], "start": start, "end": end})
        done.add(p["pid"])
        t = end

    avg_wt = sum(r["waiting"] for r in completed) / len(completed)
    avg_tat = sum(r["turnaround"] for r in completed) / len(completed)
    return jsonify({"results": completed, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2)})


# ═══════════════════════════════════════════════════════════════
# MODULE 2 — MEMORY & DEADLOCK
# ═══════════════════════════════════════════════════════════════

@app.route("/api/memory")
def api_memory():
    """Live memory stats + history."""
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    with _lock:
        hist = list(mem_history)
    return jsonify({
        "total_gb": round(vm.total / 1024**3, 2),
        "used_gb": round(vm.used / 1024**3, 2),
        "free_gb": round(vm.available / 1024**3, 2),
        "cached_gb": round(getattr(vm, "cached", 0) / 1024**3, 2),
        "percent": vm.percent,
        "swap_total_gb": round(sm.total / 1024**3, 2),
        "swap_used_gb": round(sm.used / 1024**3, 2),
        "swap_percent": sm.percent,
        "history": hist,
    })


# ── Page Replacement Algorithms ────────────────────────────────

def _page_fifo(pages, frames):
    mem, order, faults, trace = [], [], 0, []
    for pg in pages:
        hit = pg in mem
        if not hit:
            faults += 1
            if len(mem) < frames:
                mem.append(pg)
                order.append(pg)
            else:
                evict = order.pop(0)
                idx = mem.index(evict)
                mem[idx] = pg
                order.append(pg)
        trace.append({"page": pg, "frames": mem[:], "fault": not hit})
    return trace, faults


def _page_lru(pages, frames):
    mem, faults, trace = [], 0, []
    for i, pg in enumerate(pages):
        hit = pg in mem
        if not hit:
            faults += 1
            if len(mem) < frames:
                mem.append(pg)
            else:
                # find least recently used
                lru = min(mem, key=lambda x: max(
                    (j for j in range(i - 1, -1, -1) if pages[j] == x), default=-1))
                mem[mem.index(lru)] = pg
        else:
            pass  # already in memory
        trace.append({"page": pg, "frames": mem[:], "fault": not hit})
    return trace, faults


def _page_optimal(pages, frames):
    mem, faults, trace = [], 0, []
    for i, pg in enumerate(pages):
        hit = pg in mem
        if not hit:
            faults += 1
            if len(mem) < frames:
                mem.append(pg)
            else:
                future = pages[i + 1:]
                def next_use(p):
                    try:
                        return future.index(p)
                    except ValueError:
                        return float("inf")
                evict = max(mem, key=next_use)
                mem[mem.index(evict)] = pg
        trace.append({"page": pg, "frames": mem[:], "fault": not hit})
    return trace, faults


@app.route("/api/page_replacement", methods=["POST"])
def api_page_replacement():
    data = request.get_json(force=True)
    pages = data.get("pages", [])
    frames = int(data.get("frames", 3))
    algo = data.get("algorithm", "fifo").lower()
    if not pages or frames < 1:
        return jsonify({"error": "Invalid input"}), 400

    if algo == "fifo":
        trace, faults = _page_fifo(pages, frames)
    elif algo == "lru":
        trace, faults = _page_lru(pages, frames)
    elif algo == "optimal":
        trace, faults = _page_optimal(pages, frames)
    else:
        return jsonify({"error": "Unknown algorithm"}), 400

    hits = len(pages) - faults
    return jsonify({
        "algorithm": algo.upper(), "frames": frames,
        "total_references": len(pages),
        "page_faults": faults, "page_hits": hits,
        "fault_rate": round(faults / len(pages) * 100, 1),
        "hit_rate": round(hits / len(pages) * 100, 1),
        "trace": trace
    })


# ── Banker's Algorithm ─────────────────────────────────────────

def _bankers(processes, available, allocation, max_need):
    n = len(processes)
    r = len(available)
    need = [[max_need[i][j] - allocation[i][j] for j in range(r)] for i in range(n)]
    work = available[:]
    finish = [False] * n
    safe_seq = []

    for _ in range(n):
        for i in range(n):
            if not finish[i] and all(need[i][j] <= work[j] for j in range(r)):
                for j in range(r):
                    work[j] += allocation[i][j]
                finish[i] = True
                safe_seq.append(processes[i])
                break

    safe = all(finish)
    return safe, safe_seq, need


@app.route("/api/bankers", methods=["POST"])
def api_bankers():
    data = request.get_json(force=True)
    processes = data.get("processes", [f"P{i}" for i in range(5)])
    available = data.get("available", [3, 3, 2])
    allocation = data.get("allocation", [
        [0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]])
    max_need = data.get("max", [
        [7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]])

    try:
        safe, seq, need = _bankers(processes, available, allocation, max_need)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "safe": safe,
        "safe_sequence": seq,
        "need": need,
        "available": available,
        "allocation": allocation,
        "max": max_need,
        "processes": processes,
    })


# ── Deadlock Detection (Resource-Allocation Graph) ─────────────

@app.route("/api/deadlock_detect", methods=["POST"])
def api_deadlock_detect():
    """Cycle detection in a Resource-Allocation Graph via DFS."""
    data = request.get_json(force=True)
    processes = data.get("processes", [])
    resources = data.get("resources", [])
    # edges: list of {from, to, type: "request"|"assignment"}
    edges = data.get("edges", [])

    adj = defaultdict(list)
    for e in edges:
        adj[e["from"]].append(e["to"])

    visited, rec_stack = set(), set()
    cycle_nodes = []

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        for nb in adj[node]:
            if nb not in visited:
                if dfs(nb):
                    return True
            elif nb in rec_stack:
                cycle_nodes.append(nb)
                return True
        rec_stack.discard(node)
        return False

    deadlock = False
    for p in processes:
        if p not in visited:
            if dfs(p):
                deadlock = True
                break

    return jsonify({
        "deadlock": deadlock,
        "cycle_nodes": list(set(cycle_nodes)),
        "processes": processes,
        "resources": resources,
        "edges": edges,
    })


# ═══════════════════════════════════════════════════════════════
# MODULE 3 — IPC, DISK & SYNCHRONISATION
# ═══════════════════════════════════════════════════════════════

@app.route("/api/disk")
def api_disk():
    """Disk partitions + I/O stats + history."""
    partitions = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
            partitions.append({
                "device": p.device, "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "total_gb": round(usage.total / 1024**3, 2),
                "used_gb": round(usage.used / 1024**3, 2),
                "free_gb": round(usage.free / 1024**3, 2),
                "percent": usage.percent,
            })
        except PermissionError:
            pass
    with _lock:
        rh = list(disk_read_history)
        wh = list(disk_write_history)
    return jsonify({"partitions": partitions, "read_history": rh, "write_history": wh})


# ── Disk Scheduling Algorithms ─────────────────────────────────

@app.route("/api/disk_schedule", methods=["POST"])
def api_disk_schedule():
    data = request.get_json(force=True)
    requests_q = data.get("requests", [])
    head = int(data.get("head", 50))
    algo = data.get("algorithm", "fcfs").lower()
    disk_size = int(data.get("disk_size", 200))

    if not requests_q:
        return jsonify({"error": "No disk requests"}), 400

    reqs = [int(x) for x in requests_q]
    sequence, total_movement = [], 0

    if algo == "fcfs":
        sequence = [head] + reqs
    elif algo == "sstf":
        remaining = reqs[:]
        cur = head
        sequence = [cur]
        while remaining:
            closest = min(remaining, key=lambda x: abs(x - cur))
            sequence.append(closest)
            remaining.remove(closest)
            cur = closest
    elif algo == "scan":
        direction = data.get("direction", "up")
        left = sorted([r for r in reqs if r < head], reverse=True)
        right = sorted([r for r in reqs if r >= head])
        if direction == "up":
            sequence = [head] + right + [disk_size - 1] + left
        else:
            sequence = [head] + left + [0] + right
    elif algo == "cscan":
        left = sorted([r for r in reqs if r < head], reverse=True)
        right = sorted([r for r in reqs if r >= head])
        sequence = [head] + right + [disk_size - 1, 0] + sorted(left, reverse=False)
    else:
        return jsonify({"error": "Unknown algorithm"}), 400

    movements = []
    for i in range(1, len(sequence)):
        mv = abs(sequence[i] - sequence[i - 1])
        total_movement += mv
        movements.append(mv)

    return jsonify({
        "algorithm": algo.upper(), "head": head,
        "sequence": sequence, "movements": movements,
        "total_movement": total_movement,
        "requests": reqs,
    })


# ── IPC Monitor (live OS objects) ─────────────────────────────

@app.route("/api/ipc")
def api_ipc():
    """Snapshot of OS IPC objects readable without elevated privileges."""
    connections = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            connections.append({
                "fd": conn.fd,
                "type": "TCP" if conn.type == 1 else "UDP",
                "local": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "—",
                "remote": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "—",
                "status": conn.status,
                "pid": conn.pid,
            })
    except Exception:
        pass

    threads_count = sum(p.num_threads() for p in psutil.process_iter(["num_threads"])
                        if p.info.get("num_threads"))

    return jsonify({
        "connections": connections[:40],
        "total_connections": len(connections),
        "total_threads": threads_count,
        "timestamp": datetime.now().isoformat(),
    })


# ── Producer-Consumer Simulation ──────────────────────────────

@app.route("/api/producer_consumer", methods=["POST"])
def api_producer_consumer():
    data = request.get_json(force=True)
    buffer_size = int(data.get("buffer_size", 5))
    producers = int(data.get("producers", 2))
    consumers = int(data.get("consumers", 2))
    steps = int(data.get("steps", 10))

    import random
    random.seed(42)
    buffer = []
    log = []
    item = 0

    for step in range(steps):
        actor_type = "producer" if random.random() < producers / (producers + consumers) else "consumer"
        if actor_type == "producer":
            actor_id = random.randint(1, producers)
            if len(buffer) < buffer_size:
                item += 1
                buffer.append(item)
                log.append({
                    "step": step + 1, "actor": f"P{actor_id}",
                    "action": f"produced item {item}",
                    "buffer": buffer[:], "state": "ok"
                })
            else:
                log.append({
                    "step": step + 1, "actor": f"P{actor_id}",
                    "action": "blocked — buffer full",
                    "buffer": buffer[:], "state": "blocked"
                })
        else:
            actor_id = random.randint(1, consumers)
            if buffer:
                consumed = buffer.pop(0)
                log.append({
                    "step": step + 1, "actor": f"C{actor_id}",
                    "action": f"consumed item {consumed}",
                    "buffer": buffer[:], "state": "ok"
                })
            else:
                log.append({
                    "step": step + 1, "actor": f"C{actor_id}",
                    "action": "blocked — buffer empty",
                    "buffer": buffer[:], "state": "blocked"
                })

    return jsonify({
        "buffer_size": buffer_size,
        "producers": producers,
        "consumers": consumers,
        "log": log,
    })


# ── Dining Philosophers Simulation ────────────────────────────

@app.route("/api/dining_philosophers", methods=["POST"])
def api_dining():
    data = request.get_json(force=True)
    n = int(data.get("philosophers", 5))
    steps = int(data.get("steps", 15))

    import random
    random.seed(7)
    states = ["thinking"] * n
    forks_held = [None] * n
    log = []

    for step in range(steps):
        i = random.randint(0, n - 1)
        left = i
        right = (i + 1) % n
        state = states[i]

        if state == "thinking":
            states[i] = "hungry"
            log.append({"step": step + 1, "philosopher": i,
                        "action": "became hungry", "states": states[:]})
        elif state == "hungry":
            if forks_held[left] is None and forks_held[right] is None:
                forks_held[left] = i
                forks_held[right] = i
                states[i] = "eating"
                log.append({"step": step + 1, "philosopher": i,
                            "action": f"picked forks {left}&{right}, eating",
                            "states": states[:]})
            else:
                log.append({"step": step + 1, "philosopher": i,
                            "action": "waiting for forks (blocked)",
                            "states": states[:]})
        elif state == "eating":
            forks_held[left] = None
            forks_held[right] = None
            states[i] = "thinking"
            log.append({"step": step + 1, "philosopher": i,
                        "action": f"released forks {left}&{right}, thinking",
                        "states": states[:]})

    return jsonify({"philosophers": n, "log": log})


# ─────────────────────────────────────────────
# Dashboard & Health
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/api/overview")
def api_overview():
    """Single-call system overview for the top cards."""
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    boot = psutil.boot_time()
    uptime_s = int(time.time() - boot)
    hours, rem = divmod(uptime_s, 3600)
    minutes = rem // 60
    return jsonify({
        "cpu_percent": cpu,
        "cpu_cores": psutil.cpu_count(),
        "mem_percent": mem.percent,
        "mem_used_gb": round(mem.used / 1024**3, 1),
        "mem_total_gb": round(mem.total / 1024**3, 1),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "net_sent_mb": round(net.bytes_sent / 1024**2, 1),
        "net_recv_mb": round(net.bytes_recv / 1024**2, 1),
        "uptime": f"{hours}h {minutes}m",
        "process_count": len(psutil.pids()),
        "boot_time": datetime.fromtimestamp(boot).strftime("%Y-%m-%d %H:%M"),
    })


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Starting Real-Time OS Monitor on port {port} | debug={debug}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)