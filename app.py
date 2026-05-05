"""
Real-Time OS Monitoring System — app.py
CSE316 Operating Systems | CA2 Project
Full Flask backend: live metrics, algorithm simulations, IPC monitoring
"""

import os
import signal
import time
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
cpu_history        = deque(maxlen=HISTORY_LEN)
per_core_history   = deque(maxlen=HISTORY_LEN)   # list of per-core % per sample
mem_history        = deque(maxlen=HISTORY_LEN)
disk_read_history  = deque(maxlen=HISTORY_LEN)
disk_write_history = deque(maxlen=HISTORY_LEN)
net_sent_history   = deque(maxlen=HISTORY_LEN)
net_recv_history   = deque(maxlen=HISTORY_LEN)

_prev_disk = None
_prev_net  = None
_lock = threading.Lock()

# ── Prime psutil CPU counters ─────────────────
# The very first call to cpu_percent always returns 0.0 because there is no
# previous measurement to diff against. We prime it at import time so the
# background sampler's first real reading (after 1 s) is accurate.
psutil.cpu_percent(interval=None)
psutil.cpu_percent(percpu=True, interval=None)
# Also initialise the network baseline so the first delta is valid.
_prev_net = psutil.net_io_counters()
try:
    _prev_disk = psutil.disk_io_counters()
except Exception:
    pass


def _sample_metrics():
    """
    Background sampler.
    cpu_percent(interval=1) blocks for exactly 1 second and returns an
    accurate system-wide CPU reading. All other stats are collected right
    after, so the disk/net deltas are measured over the same 1-second window.
    """
    global _prev_disk, _prev_net
    while True:
        try:
            # Blocks 1 s → gives real CPU % for both overall AND per-core
            # We call percpu=True here so both measurements share the same
            # 1-second measurement window. The overall is just their average.
            per_core_vals = psutil.cpu_percent(percpu=True, interval=1)
            cpu = sum(per_core_vals) / len(per_core_vals) if per_core_vals else 0.0
            ts  = datetime.now().strftime("%H:%M:%S")

            mem     = psutil.virtual_memory().percent
            disk_io = psutil.disk_io_counters()
            net_io  = psutil.net_io_counters()

            # Disk I/O rates (MB/s)
            read_rate = write_rate = 0.0
            if _prev_disk and disk_io:
                read_rate  = max(0, (disk_io.read_bytes  - _prev_disk.read_bytes)  / 1024 / 1024)
                write_rate = max(0, (disk_io.write_bytes - _prev_disk.write_bytes) / 1024 / 1024)
            _prev_disk = disk_io

            # Network I/O rates (KB/s)
            net_sent_rate = net_recv_rate = 0.0
            if _prev_net and net_io:
                net_sent_rate = max(0, (net_io.bytes_sent - _prev_net.bytes_sent) / 1024)
                net_recv_rate = max(0, (net_io.bytes_recv - _prev_net.bytes_recv) / 1024)
            _prev_net = net_io

            with _lock:
                cpu_history.append({"t": ts, "v": round(cpu, 1)})
                per_core_history.append({"t": ts, "v": [round(c, 1) for c in per_core_vals]})
                mem_history.append({"t": ts, "v": round(mem, 1)})
                disk_read_history.append({"t": ts, "v": round(read_rate, 3)})
                disk_write_history.append({"t": ts, "v": round(write_rate, 3)})
                net_sent_history.append({"t": ts, "v": round(net_sent_rate, 2)})
                net_recv_history.append({"t": ts, "v": round(net_recv_rate, 2)})

        except Exception as e:
            logger.warning(f"Metric sample error: {e}")
            time.sleep(1)   # avoid spin-loop on error


_sampler = threading.Thread(target=_sample_metrics, daemon=True, name="metric-sampler")
_sampler.start()


# ═══════════════════════════════════════════════════════════════
# MODULE 1 — PROCESS & CPU
# ═══════════════════════════════════════════════════════════════

@app.route("/api/processes")
def api_processes():
    """
    Live process table.
    cpu_percent() per-process also needs priming; we call it twice with a
    short sleep so the values are non-zero.  To keep response time fast we
    use process_iter which caches the first call internally.
    """
    snap = []
    # First pass — prime each process's CPU counter
    procs_obj = []
    for p in psutil.process_iter(["pid", "name", "status", "cpu_percent",
                                   "memory_percent", "nice", "num_threads", "create_time"]):
        try:
            p.cpu_percent()   # prime — returns 0 but sets baseline
            procs_obj.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(0.15)   # short measurement window

    # Second pass — real readings
    for p in procs_obj:
        try:
            info = p.as_dict(attrs=["pid", "name", "status", "cpu_percent",
                                     "memory_percent", "nice", "num_threads", "create_time"])
            snap.append({
                "pid":      info["pid"],
                "name":     info["name"] or "—",
                "status":   info["status"],
                "cpu":      round(info["cpu_percent"] or 0, 2),
                "mem":      round(info["memory_percent"] or 0, 2),
                "priority": info["nice"],
                "threads":  info["num_threads"],
                "started":  datetime.fromtimestamp(info["create_time"]).strftime("%H:%M:%S")
                            if info["create_time"] else "—",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    snap.sort(key=lambda x: x["cpu"], reverse=True)
    return jsonify({"processes": snap[:100], "total": len(snap)})


@app.route("/api/kill_process", methods=["POST"])
def api_kill_process():
    """Terminate a process by PID."""
    data = request.get_json(force=True)
    pid  = data.get("pid")
    if pid is None:
        return jsonify({"error": "pid required"}), 400
    try:
        pid  = int(pid)
        p    = psutil.Process(pid)
        name = p.name()

        # Step 1: Kill all children first (prevents zombie children)
        try:
            children = p.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Step 2: Try SIGTERM first (graceful shutdown)
        try:
            p.terminate()
            p.wait(timeout=2)
        except psutil.TimeoutExpired:
            # Step 3: Force SIGKILL if SIGTERM was ignored
            try:
                p.kill()
                p.wait(timeout=2)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                pass
        except psutil.NoSuchProcess:
            pass   # already gone — that's fine

        # Step 4: Try killing the entire process group (catches GUI app workers)
        try:
            import os
            pgid = os.getpgid(pid)
            if pgid > 1:   # never kill init's group
                os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass   # group already dead or no permission

        logger.info(f"Killed PID {pid} ({name})")
        return jsonify({"success": True, "pid": pid, "name": name})

    except psutil.NoSuchProcess:
        return jsonify({"error": f"PID {pid} not found"}), 404
    except psutil.AccessDenied:
        return jsonify({"error": f"Access denied — cannot kill PID {pid}. Try running as admin/root."}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cpu")
def api_cpu():
    """
    CPU overview.
    We read overall CPU from the ring buffer (filled by the background sampler
    with interval=1) to avoid returning 0 from a bare cpu_percent() call.
    """
    with _lock:
        hist          = list(cpu_history)
        pc_hist       = list(per_core_history)
        overall = hist[-1]["v"] if hist else 0.0

    # per-core: read from ring buffer (sampled with interval=1 in background thread)
    # DO NOT call cpu_percent(percpu=True, interval=None) here — the sampler
    # already consumed the kernel counters, so interval=None returns near-zero.
    per_core = pc_hist[-1]["v"] if pc_hist else []

    freq = psutil.cpu_freq()
    try:
        load = [round(x / psutil.cpu_count() * 100, 1) for x in psutil.getloadavg()]
    except AttributeError:
        load = [0, 0, 0]

    return jsonify({
        "overall":   overall,
        "per_core":  per_core,
        "count":     psutil.cpu_count(),
        "freq_mhz":  round(freq.current, 0) if freq else 0,
        "freq_max":  round(freq.max, 0)     if freq else 0,
        "load_avg":  load,
        "history":   hist,
    })


# ── CPU Scheduling Algorithms ─────────────────────────────────

@app.route("/api/schedule/fcfs", methods=["POST"])
def api_fcfs():
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
        end   = t + p["burst"]
        results.append({"pid": p["pid"], "arrival": p["arrival"], "burst": p["burst"],
                         "start": start, "end": end,
                         "waiting": start - p["arrival"],
                         "turnaround": end - p["arrival"]})
        schedule.append({"pid": p["pid"], "start": start, "end": end})
        t = end

    avg_wt  = sum(r["waiting"]    for r in results) / len(results)
    avg_tat = sum(r["turnaround"] for r in results) / len(results)
    return jsonify({"results": results, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2)})


@app.route("/api/schedule/sjf", methods=["POST"])
def api_sjf():
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
        p     = min(available, key=lambda x: x["burst"])
        start = t
        end   = t + p["burst"]
        completed.append({"pid": p["pid"], "arrival": p["arrival"], "burst": p["burst"],
                           "start": start, "end": end,
                           "waiting": start - p["arrival"],
                           "turnaround": end - p["arrival"]})
        schedule.append({"pid": p["pid"], "start": start, "end": end})
        done.add(p["pid"])
        t = end

    avg_wt  = sum(r["waiting"]    for r in completed) / len(completed)
    avg_tat = sum(r["turnaround"] for r in completed) / len(completed)
    return jsonify({"results": completed, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2)})


@app.route("/api/schedule/rr", methods=["POST"])
def api_rr():
    data = request.get_json(force=True)
    processes = data.get("processes", [])
    quantum   = int(data.get("quantum", 2))
    if not processes:
        return jsonify({"error": "No processes provided"}), 400

    remaining   = {p["pid"]: p["burst"]   for p in processes}
    arrival     = {p["pid"]: p["arrival"] for p in processes}
    burst_orig  = {p["pid"]: p["burst"]   for p in processes}
    start_time  = {}
    finish_time = {}

    queue    = deque()
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
        ft  = finish_time.get(pid, t)
        wt  = ft - arrival[pid] - burst_orig[pid]
        results.append({"pid": pid, "arrival": arrival[pid], "burst": burst_orig[pid],
                         "start": start_time.get(pid, 0), "end": ft,
                         "waiting": max(0, wt), "turnaround": ft - arrival[pid]})

    avg_wt  = sum(r["waiting"]    for r in results) / len(results)
    avg_tat = sum(r["turnaround"] for r in results) / len(results)
    return jsonify({"results": results, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2),
                    "quantum": quantum})


@app.route("/api/schedule/priority", methods=["POST"])
def api_priority():
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
        p     = min(available, key=lambda x: x.get("priority", 0))
        start = t
        end   = t + p["burst"]
        completed.append({"pid": p["pid"], "arrival": p["arrival"], "burst": p["burst"],
                           "priority": p.get("priority", 0),
                           "start": start, "end": end,
                           "waiting": start - p["arrival"],
                           "turnaround": end - p["arrival"]})
        schedule.append({"pid": p["pid"], "start": start, "end": end})
        done.add(p["pid"])
        t = end

    avg_wt  = sum(r["waiting"]    for r in completed) / len(completed)
    avg_tat = sum(r["turnaround"] for r in completed) / len(completed)
    return jsonify({"results": completed, "gantt": schedule,
                    "avg_waiting": round(avg_wt, 2), "avg_turnaround": round(avg_tat, 2)})


# ═══════════════════════════════════════════════════════════════
# MODULE 2 — MEMORY & DEADLOCK
# ═══════════════════════════════════════════════════════════════

@app.route("/api/memory")
def api_memory():
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    with _lock:
        hist = list(mem_history)
    return jsonify({
        "total_gb":      round(vm.total    / 1024**3, 2),
        "used_gb":       round(vm.used     / 1024**3, 2),
        "free_gb":       round(vm.available/ 1024**3, 2),
        "cached_gb":     round(getattr(vm, "cached", 0) / 1024**3, 2),
        "percent":       vm.percent,
        "swap_total_gb": round(sm.total / 1024**3, 2),
        "swap_used_gb":  round(sm.used  / 1024**3, 2),
        "swap_percent":  sm.percent,
        "history":       hist,
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
                idx   = mem.index(evict)
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
                lru = min(mem, key=lambda x: max(
                    (j for j in range(i - 1, -1, -1) if pages[j] == x), default=-1))
                mem[mem.index(lru)] = pg
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
                    try:    return future.index(p)
                    except: return float("inf")
                evict = max(mem, key=next_use)
                mem[mem.index(evict)] = pg
        trace.append({"page": pg, "frames": mem[:], "fault": not hit})
    return trace, faults


@app.route("/api/page_replacement", methods=["POST"])
def api_page_replacement():
    data   = request.get_json(force=True)
    pages  = data.get("pages", [])
    frames = int(data.get("frames", 3))
    algo   = data.get("algorithm", "fifo").lower()
    if not pages or frames < 1:
        return jsonify({"error": "Invalid input"}), 400

    if   algo == "fifo":    trace, faults = _page_fifo(pages, frames)
    elif algo == "lru":     trace, faults = _page_lru(pages, frames)
    elif algo == "optimal": trace, faults = _page_optimal(pages, frames)
    else: return jsonify({"error": "Unknown algorithm"}), 400

    hits = len(pages) - faults
    return jsonify({
        "algorithm": algo.upper(), "frames": frames,
        "total_references": len(pages),
        "page_faults": faults, "page_hits": hits,
        "fault_rate": round(faults / len(pages) * 100, 1),
        "hit_rate":   round(hits   / len(pages) * 100, 1),
        "trace": trace,
    })


# ── Banker's Algorithm ─────────────────────────────────────────

def _bankers(processes, available, allocation, max_need):
    n    = len(processes)
    r    = len(available)
    need = [[max_need[i][j] - allocation[i][j] for j in range(r)] for i in range(n)]
    work = available[:]
    finish, safe_seq = [False] * n, []

    for _ in range(n):
        for i in range(n):
            if not finish[i] and all(need[i][j] <= work[j] for j in range(r)):
                for j in range(r):
                    work[j] += allocation[i][j]
                finish[i] = True
                safe_seq.append(processes[i])
                break

    return all(finish), safe_seq, need


@app.route("/api/bankers", methods=["POST"])
def api_bankers():
    data       = request.get_json(force=True)
    processes  = data.get("processes", [f"P{i}" for i in range(5)])
    available  = data.get("available",  [3, 3, 2])
    allocation = data.get("allocation", [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]])
    max_need   = data.get("max",        [[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]])

    try:
        safe, seq, need = _bankers(processes, available, allocation, max_need)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"safe": safe, "safe_sequence": seq, "need": need,
                    "available": available, "allocation": allocation,
                    "max": max_need, "processes": processes})


# ── Deadlock Detection ─────────────────────────────────────────

@app.route("/api/deadlock_detect", methods=["POST"])
def api_deadlock_detect():
    data      = request.get_json(force=True)
    processes = data.get("processes", [])
    resources = data.get("resources", [])
    edges     = data.get("edges", [])

    adj = defaultdict(list)
    for e in edges:
        adj[e["from"]].append(e["to"])

    visited, rec_stack, cycle_nodes = set(), set(), []

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

    deadlock = any(dfs(p) for p in processes if p not in visited)
    return jsonify({"deadlock": deadlock, "cycle_nodes": list(set(cycle_nodes)),
                    "processes": processes, "resources": resources, "edges": edges})


# ═══════════════════════════════════════════════════════════════
# MODULE 3 — IPC, DISK & SYNCHRONISATION
# ═══════════════════════════════════════════════════════════════

@app.route("/api/disk")
def api_disk():
    """Disk partitions + live I/O rate history."""
    partitions = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
            partitions.append({
                "device":    p.device,
                "mountpoint": p.mountpoint,
                "fstype":    p.fstype,
                "total_gb":  round(usage.total / 1024**3, 2),
                "used_gb":   round(usage.used  / 1024**3, 2),
                "free_gb":   round(usage.free  / 1024**3, 2),
                "percent":   usage.percent,
            })
        except (PermissionError, FileNotFoundError):
            pass

    with _lock:
        rh = list(disk_read_history)
        wh = list(disk_write_history)

    return jsonify({"partitions": partitions, "read_history": rh, "write_history": wh})


# ── Disk Scheduling Algorithms ─────────────────────────────────

@app.route("/api/disk_schedule", methods=["POST"])
def api_disk_schedule():
    data      = request.get_json(force=True)
    requests_q= data.get("requests", [])
    head      = int(data.get("head", 50))
    algo      = data.get("algorithm", "fcfs").lower()
    disk_size = int(data.get("disk_size", 200))
    if not requests_q:
        return jsonify({"error": "No disk requests"}), 400

    reqs     = [int(x) for x in requests_q]
    sequence = []

    if algo == "fcfs":
        sequence = [head] + reqs
    elif algo == "sstf":
        remaining, cur = reqs[:], head
        sequence = [cur]
        while remaining:
            closest = min(remaining, key=lambda x: abs(x - cur))
            sequence.append(closest)
            remaining.remove(closest)
            cur = closest
    elif algo == "scan":
        direction = data.get("direction", "up")
        left  = sorted([r for r in reqs if r < head], reverse=True)
        right = sorted([r for r in reqs if r >= head])
        sequence = ([head] + right + [disk_size - 1] + left if direction == "up"
                    else [head] + left + [0] + right)
    elif algo == "cscan":
        left  = sorted([r for r in reqs if r < head])
        right = sorted([r for r in reqs if r >= head])
        sequence = [head] + right + [disk_size - 1, 0] + left
    else:
        return jsonify({"error": "Unknown algorithm"}), 400

    total_movement = sum(abs(sequence[i] - sequence[i-1]) for i in range(1, len(sequence)))
    movements      = [abs(sequence[i] - sequence[i-1]) for i in range(1, len(sequence))]

    return jsonify({"algorithm": algo.upper(), "head": head,
                    "sequence": sequence, "movements": movements,
                    "total_movement": total_movement, "requests": reqs})


# ── IPC Monitor ────────────────────────────────────────────────

@app.route("/api/ipc")
def api_ipc():
    connections = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            connections.append({
                "fd":     conn.fd,
                "type":   "TCP" if conn.type == 1 else "UDP",
                "local":  f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "—",
                "remote": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "—",
                "status": conn.status,
                "pid":    conn.pid,
            })
    except Exception:
        pass

    threads_count = 0
    try:
        threads_count = sum(
            p.num_threads() for p in psutil.process_iter(["num_threads"])
            if p.info.get("num_threads")
        )
    except Exception:
        pass

    with _lock:
        sh = list(net_sent_history)
        rh = list(net_recv_history)

    return jsonify({
        "connections":       connections[:40],
        "total_connections": len(connections),
        "total_threads":     threads_count,
        "sent_history":      sh,
        "recv_history":      rh,
        "timestamp":         datetime.now().isoformat(),
    })


# ── Producer-Consumer Simulation ──────────────────────────────

@app.route("/api/producer_consumer", methods=["POST"])
def api_producer_consumer():
    data        = request.get_json(force=True)
    buffer_size = int(data.get("buffer_size", 5))
    producers   = int(data.get("producers",  2))
    consumers   = int(data.get("consumers",  2))
    steps       = int(data.get("steps",      10))

    import random
    random.seed(42)
    buffer, log, item = [], [], 0

    for step in range(steps):
        is_producer = random.random() < producers / (producers + consumers)
        if is_producer:
            actor_id = random.randint(1, producers)
            if len(buffer) < buffer_size:
                item += 1
                buffer.append(item)
                log.append({"step": step+1, "actor": f"P{actor_id}",
                             "action": f"produced item {item}",
                             "buffer": buffer[:], "state": "ok"})
            else:
                log.append({"step": step+1, "actor": f"P{actor_id}",
                             "action": "blocked — buffer full",
                             "buffer": buffer[:], "state": "blocked"})
        else:
            actor_id = random.randint(1, consumers)
            if buffer:
                consumed = buffer.pop(0)
                log.append({"step": step+1, "actor": f"C{actor_id}",
                             "action": f"consumed item {consumed}",
                             "buffer": buffer[:], "state": "ok"})
            else:
                log.append({"step": step+1, "actor": f"C{actor_id}",
                             "action": "blocked — buffer empty",
                             "buffer": buffer[:], "state": "blocked"})

    return jsonify({"buffer_size": buffer_size, "producers": producers,
                    "consumers": consumers, "log": log})


# ── Dining Philosophers Simulation ────────────────────────────

@app.route("/api/dining_philosophers", methods=["POST"])
def api_dining():
    data   = request.get_json(force=True)
    n      = int(data.get("philosophers", 5))
    steps  = int(data.get("steps", 15))

    import random
    random.seed(7)
    states, forks_held, log = ["thinking"] * n, [None] * n, []

    for step in range(steps):
        i     = random.randint(0, n - 1)
        left  = i
        right = (i + 1) % n
        state = states[i]

        if state == "thinking":
            states[i] = "hungry"
            log.append({"step": step+1, "philosopher": i,
                         "action": "became hungry", "states": states[:]})
        elif state == "hungry":
            if forks_held[left] is None and forks_held[right] is None:
                forks_held[left] = forks_held[right] = i
                states[i] = "eating"
                log.append({"step": step+1, "philosopher": i,
                             "action": f"picked forks {left}&{right}, eating",
                             "states": states[:]})
            else:
                log.append({"step": step+1, "philosopher": i,
                             "action": "waiting for forks (blocked)",
                             "states": states[:]})
        elif state == "eating":
            forks_held[left] = forks_held[right] = None
            states[i] = "thinking"
            log.append({"step": step+1, "philosopher": i,
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
    """
    Single-call system overview for header KPI cards.
    CPU: read from ring buffer (accurate, non-zero).
    Network: show current KB/s rates, NOT cumulative totals.
    Disk: use first readable partition as primary.
    """
    # CPU from ring buffer
    with _lock:
        cpu_hist = list(cpu_history)
        sh = list(net_sent_history)
        rh = list(net_recv_history)

    cpu_pct = cpu_hist[-1]["v"] if cpu_hist else 0.0

    # Memory
    mem  = psutil.virtual_memory()

    # Disk — use the root / home partition (skip tmpfs etc.)
    disk_pct = disk_used = disk_total = 0
    for part in psutil.disk_partitions(all=False):
        try:
            if part.fstype in ("tmpfs", "devtmpfs", "squashfs", "overlay"):
                continue
            du = psutil.disk_usage(part.mountpoint)
            if du.total > disk_total:          # pick the largest real partition
                disk_total = du.total
                disk_used  = du.used
                disk_pct   = du.percent
        except (PermissionError, FileNotFoundError):
            pass

    # Network rates (KB/s from last sample)
    net_sent_rate = sh[-1]["v"] if sh else 0.0
    net_recv_rate = rh[-1]["v"] if rh else 0.0

    boot     = psutil.boot_time()
    uptime_s = int(time.time() - boot)
    hours, rem = divmod(uptime_s, 3600)
    minutes  = rem // 60

    return jsonify({
        "cpu_percent":   cpu_pct,
        "cpu_cores":     psutil.cpu_count(),
        "mem_percent":   mem.percent,
        "mem_used_gb":   round(mem.used  / 1024**3, 1),
        "mem_total_gb":  round(mem.total / 1024**3, 1),
        "disk_percent":  disk_pct,
        "disk_used_gb":  round(disk_used  / 1024**3, 1),
        "disk_total_gb": round(disk_total / 1024**3, 1),
        "net_sent_kbps": net_sent_rate,
        "net_recv_kbps": net_recv_rate,
        "uptime":        f"{hours}h {minutes}m",
        "process_count": len(psutil.pids()),
        "boot_time":     datetime.fromtimestamp(boot).strftime("%Y-%m-%d %H:%M"),
    })


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Starting Real-Time OS Monitor on port {port} | debug={debug}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)