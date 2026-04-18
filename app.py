from flask import Flask, render_template, jsonify
import psutil

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/data')
def data():
    #  System stats
    cpu = psutil.cpu_percent(interval=1)   # accurate CPU usage
    memory = psutil.virtual_memory().percent
    processes_count = len(psutil.pids())

    #  Dynamic system status
    if cpu < 50:
        status = "Healthy"
    elif cpu < 80:
        status = "Moderate"
    else:
        status = "Critical"

    #  Process list
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
        try:
            processes.append({
                "pid": proc.pid,
                "name": proc.name(),
                "cpu_percent": proc.cpu_percent(interval=None),
                "memory_percent": proc.memory_percent()
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    #  Sort top processes by CPU usage
    top_processes = sorted(
        processes,
        key=lambda x: x['cpu_percent'],
        reverse=True
    )[:5]

    #  Final response
    return jsonify({
        "cpu": cpu,
        "memory": memory,
        "processes": processes_count,
        "status": status,
        "top_processes": top_processes
    })


#  Run server
if __name__ == "__main__":
    app.run(debug=True)