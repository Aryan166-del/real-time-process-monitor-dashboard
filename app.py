from flask import Flask, render_template, jsonify
import psutil

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/data')
def data():
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    processes = len(psutil.pids())

    return jsonify({
        "cpu": cpu,
        "memory": memory,
        "processes": processes,
        "status": "Running"
    })

if __name__ == "__main__":
    app.run(debug=True)