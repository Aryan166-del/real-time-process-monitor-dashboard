# Real-Time OS Monitoring System
**CSE316 — Operating Systems | CA2 Project**

A production-grade, web-based dashboard that monitors live OS metrics and simulates core OS algorithms — all in one sleek cyberpunk interface.

---

## Features

### Module 1 — Process & CPU Monitor
- Live process table: PID, name, state, CPU%, MEM%, threads
- Per-core CPU load bars + 60-second history chart
- CPU Scheduling Simulator: **FCFS, SJF, Round-Robin, Priority**
- Animated Gantt chart + waiting/turnaround statistics
- Process lifecycle state diagram (New → Ready → Running → Waiting → Terminated)

### Module 2 — Memory & Deadlock Analyser
- Live RAM/swap usage with history chart
- Page Replacement Simulator: **FIFO, LRU, Optimal** with step-by-step trace
- Banker's Algorithm — safe-state checker with full need/allocation matrix
- Deadlock Detection via Resource-Allocation Graph (cycle detection)

### Module 3 — IPC, Disk & Synchronisation
- Live disk partition usage + I/O read/write rate history
- Disk Scheduling Simulator: **FCFS, SSTF, SCAN, C-SCAN** with head-movement chart
- IPC / Network connection monitor
- Producer-Consumer simulation (configurable buffer/producers/consumers)
- Dining Philosophers simulation

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.x + Flask |
| System Data | psutil |
| Frontend | Vanilla JS + Chart.js |
| Styling | Custom CSS (cyberpunk dark theme) |
| Fonts | Share Tech Mono + Exo 2 (Google Fonts) |

---

## Setup & Run

### 1. Clone / enter project directory
```bash
cd real_time_process_management_system
```

### 2. Create virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the server
```bash
python app.py
```

### 5. Open in browser
```
http://localhost:5000
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Server port |
| `FLASK_DEBUG` | `false` | Enable debug mode |
| `SECRET_KEY` | built-in | Flask secret key |

---

## Project Structure

```
real_time_process_management_system/
├── app.py                  # Flask backend — all APIs
├── requirements.txt        # Python dependencies
├── README.md
├── .gitignore
├── static/
│   ├── css/style.css       # Full dark-theme styling
│   └── js/script.js        # All frontend logic + Chart.js
└── templates/
    └── index.html          # Single-page dashboard
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/overview` | System summary (CPU, MEM, DISK, NET) |
| GET | `/api/cpu` | CPU details + history |
| GET | `/api/processes` | Live process list |
| GET | `/api/memory` | Memory + history |
| GET | `/api/disk` | Disk partitions + I/O history |
| GET | `/api/ipc` | Network connections |
| POST | `/api/schedule/fcfs` | FCFS scheduling |
| POST | `/api/schedule/sjf` | SJF scheduling |
| POST | `/api/schedule/rr` | Round-Robin scheduling |
| POST | `/api/schedule/priority` | Priority scheduling |
| POST | `/api/page_replacement` | FIFO/LRU/Optimal |
| POST | `/api/bankers` | Banker's Algorithm |
| POST | `/api/deadlock_detect` | RAG deadlock detection |
| POST | `/api/disk_schedule` | FCFS/SSTF/SCAN/C-SCAN |
| POST | `/api/producer_consumer` | Producer-Consumer sim |
| POST | `/api/dining_philosophers` | Dining Philosophers sim |

---

## References
- Silberschatz, Galvin, Gagne — *Operating System Concepts* (10th ed.)
- psutil documentation: https://psutil.readthedocs.io/
- Flask documentation: https://flask.palletsprojects.com/