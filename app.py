from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import psutil

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


@app.route('/')
def index():
    return render_template('index.html')


# 🔥 BACKGROUND SYSTEM MONITOR
def send_stats():
    while True:
        try:
            # ---- SYSTEM STATS ----
            cpu = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory().percent
            processes_count = len(psutil.pids())

            # ---- STATUS LOGIC ----
            if cpu < 50:
                status = "Healthy"
            elif cpu < 80:
                status = "Moderate"
            else:
                status = "Critical"

            # ---- PROCESS LIST ----
            process_list = []

            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    process_list.append({
                        "pid": proc.pid,
                        "name": proc.name(),
                        "cpu_percent": proc.cpu_percent(interval=None),
                        "memory_percent": round(proc.memory_percent(), 1)
                    })

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # 🔥 SORT ALL PROCESSES (NO LIMIT)
            process_list.sort(key=lambda x: x['cpu_percent'], reverse=True)

            # 🔥 OPTIONAL LIMIT (for performance)
            LIMIT = 200   # 👈 change this (or remove completely)

            if LIMIT:
                process_list = process_list[:LIMIT]

            # ---- EMIT DATA ----
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


# 🔥 START BACKGROUND THREAD ONLY ONCE
@socketio.on('connect')
def start_background():
    print("Client connected")

    if not hasattr(app, "thread"):
        app.thread = socketio.start_background_task(send_stats)


# 🔥 IMPROVED KILL FUNCTION
@app.route('/kill', methods=['POST'])
def kill_process():
    data = request.get_json()
    pid = int(data.get("pid"))

    try:
        parent = psutil.Process(pid)

        # Kill children first
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
        return jsonify({"message": "❌ Access Denied (Run as Administrator)"}), 403

    except Exception as e:
        return jsonify({"message": str(e)}), 500


if __name__ == "__main__":
    socketio.run(app, debug=True)