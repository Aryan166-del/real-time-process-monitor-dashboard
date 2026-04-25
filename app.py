from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import psutil
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


@app.route('/')
def index():
    return render_template('index.html')


# =========================================================
# 🔥 BACKGROUND SYSTEM MONITOR
# =========================================================
def send_stats():
    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory().percent
            processes_count = len(psutil.pids())

            # STATUS
            if cpu < 50:
                status = "Healthy"
            elif cpu < 80:
                status = "Moderate"
            else:
                status = "Critical"

            process_list = []

            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc.cpu_percent(interval=None)
                    time.sleep(0.003)
                    cpu_percent = proc.cpu_percent(interval=None)

                    process_list.append({
                        "pid": proc.pid,
                        "name": proc.name(),
                        "cpu_percent": round(cpu_percent, 1),
                        "memory_percent": round(proc.memory_percent(), 1),
                        "state": proc.status(),
                        "priority": proc.nice()
                    })

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            process_list.sort(key=lambda x: x['cpu_percent'], reverse=True)
            process_list = process_list[:200]

            socketio.emit('stats', {
                "cpu": cpu,
                "memory": memory,
                "processes": processes_count,
                "status": status,
                "process_list": process_list
            })

        except Exception as e:
            print("Error:", e)

        socketio.sleep(2)


@socketio.on('connect')
def start_background():
    if not hasattr(app, "thread"):
        app.thread = socketio.start_background_task(send_stats)


# =========================================================
# 🔥 KILL PROCESS
# =========================================================
@app.route('/kill', methods=['POST'])
def kill_process():
    data = request.get_json()
    pid = int(data.get("pid"))

    try:
        parent = psutil.Process(pid)

        for child in parent.children(recursive=True):
            try:
                child.kill()
            except:
                pass

        parent.kill()

        return jsonify({"message": f"✅ Process {pid} killed"}), 200

    except psutil.NoSuchProcess:
        return jsonify({"message": "⚠️ Process already closed"}), 404

    except psutil.AccessDenied:
        return jsonify({"message": "❌ Run as Administrator"}), 403

    except Exception as e:
        return jsonify({"message": str(e)}), 500


# =========================================================
# 🔥 SCHEDULING API
# =========================================================
@app.route('/schedule', methods=['POST'])
def schedule():
    data = request.get_json()
    processes = data.get("processes")
    algo = data.get("algo")
    quantum = data.get("quantum", 2)

    if algo == "FCFS":
        result = fcfs(processes)
    elif algo == "SJF":
        result = sjf(processes)
    elif algo == "Priority":
        result = priority_sched(processes)
    elif algo == "RR":
        result = round_robin(processes, quantum)
    else:
        return jsonify({"error": "Invalid algorithm"})

    return jsonify(result)


# =========================================================
# 🔥 FCFS
# =========================================================
def fcfs(processes):
    processes = sorted(processes, key=lambda x: x['arrival'])
    time_now = 0
    result = []

    for p in processes:
        if time_now < p['arrival']:
            time_now = p['arrival']

        result.append({
            "id": p['id'],
            "start": time_now,
            "end": time_now + p['burst']
        })

        time_now += p['burst']

    return result


# =========================================================
# 🔥 SJF (Correct - Ready Queue Based)
# =========================================================
def sjf(processes):
    processes = sorted(processes, key=lambda x: x['arrival'])
    ready = []
    result = []
    time_now = 0
    i = 0

    while i < len(processes) or ready:

        while i < len(processes) and processes[i]['arrival'] <= time_now:
            ready.append(processes[i])
            i += 1

        if not ready:
            time_now = processes[i]['arrival']
            continue

        ready.sort(key=lambda x: x['burst'])
        p = ready.pop(0)

        result.append({
            "id": p['id'],
            "start": time_now,
            "end": time_now + p['burst']
        })

        time_now += p['burst']

    return result


# =========================================================
# 🔥 PRIORITY (Correct)
# =========================================================
def priority_sched(processes):
    processes = sorted(processes, key=lambda x: x['arrival'])
    ready = []
    result = []
    time_now = 0
    i = 0

    while i < len(processes) or ready:

        while i < len(processes) and processes[i]['arrival'] <= time_now:
            ready.append(processes[i])
            i += 1

        if not ready:
            time_now = processes[i]['arrival']
            continue

        ready.sort(key=lambda x: x['priority'])
        p = ready.pop(0)

        result.append({
            "id": p['id'],
            "start": time_now,
            "end": time_now + p['burst']
        })

        time_now += p['burst']

    return result


# =========================================================
# 🔥 ROUND ROBIN (Correct)
# =========================================================
def round_robin(processes, quantum):
    processes = sorted(processes, key=lambda x: x['arrival'])
    queue = []
    result = []
    time_now = 0
    i = 0

    while i < len(processes) or queue:

        while i < len(processes) and processes[i]['arrival'] <= time_now:
            queue.append(processes[i].copy())
            i += 1

        if not queue:
            time_now = processes[i]['arrival']
            continue

        p = queue.pop(0)

        exec_time = min(p['burst'], quantum)

        result.append({
            "id": p['id'],
            "start": time_now,
            "end": time_now + exec_time
        })

        time_now += exec_time
        p['burst'] -= exec_time

        # Add newly arrived processes
        while i < len(processes) and processes[i]['arrival'] <= time_now:
            queue.append(processes[i].copy())
            i += 1

        if p['burst'] > 0:
            queue.append(p)

    return result


# =========================================================

if __name__ == "__main__":
    socketio.run(app, debug=True)