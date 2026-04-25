const socket = io();

// ==============================
// GRAPH DATA
// ==============================
let cpuData = [];
let memoryData = [];
let labels = [];
const MAX_POINTS = 40;

// ==============================
// CPU CHART
// ==============================
const cpuChart = new Chart(document.getElementById("cpuChart"), {
    type: 'line',
    data: {
        labels: labels,
        datasets: [{
            label: 'CPU Usage (%)',
            data: cpuData,
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34,197,94,0.15)',
            fill: true,
            tension: 0.4,
            pointRadius: 0
        }]
    },
    options: {
        responsive: true,
        animation: false,
        scales: { y: { min: 0, max: 100 } }
    }
});

// ==============================
// MEMORY CHART
// ==============================
const memoryChart = new Chart(document.getElementById("memoryChart"), {
    type: 'line',
    data: {
        labels: labels,
        datasets: [{
            label: 'Memory Usage (%)',
            data: memoryData,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.15)',
            fill: true,
            tension: 0.4,
            pointRadius: 0
        }]
    },
    options: {
        responsive: true,
        animation: false,
        scales: { y: { min: 0, max: 100 } }
    }
});

// ==============================
// SEARCH BAR
// ==============================
let searchValue = "";
document.getElementById("search").addEventListener("input", (e) => {
    searchValue = e.target.value.toLowerCase();
});

// ==============================
// SOCKET DATA
// ==============================
socket.on('stats', data => {

    document.getElementById("cpu").innerText = data.cpu + "%";
    document.getElementById("memory").innerText = data.memory + "%";
    document.getElementById("processes").innerText = data.processes;
    document.getElementById("status").innerText = data.status;

    const statusEl = document.getElementById("status");
    statusEl.style.color =
        data.status === "Healthy" ? "#22c55e" :
        data.status === "Moderate" ? "#f59e0b" :
        "#ef4444";

    const table = document.getElementById("table");
    table.innerHTML = "";

    data.process_list
        .filter(p =>
            p.name.toLowerCase().includes(searchValue) ||
            String(p.pid).includes(searchValue)
        )
        .forEach(p => {

            let cpuColor =
                p.cpu_percent > 50 ? "#ef4444" :
                p.cpu_percent > 20 ? "#f59e0b" :
                "#22c55e";

            let row = document.createElement("tr");

            row.innerHTML = `
                <td>${p.pid}</td>
                <td>${p.name}</td>
                <td>${p.state || "Running"}</td>
                <td>${p.priority || "-"}</td>
                <td style="color:${cpuColor}; font-weight:bold;">
                    ${p.cpu_percent.toFixed(1)}%
                </td>
                <td>${p.memory_percent.toFixed(1)}%</td>
                <td>
                    <button onclick="killProcess(${p.pid})">End</button>
                </td>
            `;

            table.appendChild(row);
        });

    // GRAPH UPDATE
    if (cpuData.length >= MAX_POINTS) {
        cpuData.shift();
        memoryData.shift();
        labels.shift();
    }

    cpuData.push(data.cpu);
    memoryData.push(data.memory);
    labels.push(new Date().toLocaleTimeString());

    cpuChart.update();
    memoryChart.update();
});

// ==============================
// KILL PROCESS
// ==============================
function killProcess(pid) {
    if (!confirm(`Kill PID ${pid}?`)) return;

    fetch('/kill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid })
    })
    .then(res => res.json().then(data => ({
        status: res.status,
        body: data
    })))
    .then(res => {
        showToast(res.body.message, res.status === 200 ? "success" : "error");
    })
    .catch(() => showToast("Network error", "error"));
}

// ==============================
// TOAST
// ==============================
function showToast(message, type) {
    const toast = document.createElement("div");

    toast.innerText = message;
    toast.style.position = "fixed";
    toast.style.bottom = "20px";
    toast.style.right = "20px";
    toast.style.padding = "10px 15px";
    toast.style.borderRadius = "8px";
    toast.style.color = "white";
    toast.style.background = type === "success" ? "#22c55e" : "#ef4444";

    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ==============================
// 🔥 CPU SCHEDULING
// ==============================
let processQueue = [];

// ADD PROCESS
function addProcess() {

    const arrival = parseInt(document.getElementById("arrival").value);
    const burst = parseInt(document.getElementById("burst").value);
    const priority = parseInt(document.getElementById("priority").value);

    if (isNaN(arrival) || isNaN(burst)) {
        showToast("Enter valid values", "error");
        return;
    }

    processQueue.push({
        id: "P" + (processQueue.length + 1),
        arrival,
        burst,
        priority
    });

    showToast("Process Added", "success");
}

// RUN FCFS
function runScheduling() {

    if (processQueue.length === 0) {
        showToast("Add processes first", "error");
        return;
    }

    const algo = document.getElementById("algo").value;

    // 🔥 Call backend (CORRECT LOGIC)
    fetch('/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            processes: processQueue,
            algo: algo,
            quantum: 2   // used only for Round Robin
        })
    })
    .then(res => res.json())
    .then(gantt => {

        if (!Array.isArray(gantt)) {
            showToast("Scheduling error", "error");
            return;
        }

        animateGantt(gantt); // 🔥 draw correct result
    })
    .catch(() => {
        showToast("Server error", "error");
    });
}
// ==============================
// 🔥 ANIMATED GANTT CHART
// ==============================
function animateGantt(gantt) {

    const container = document.getElementById("ganttChart");
    container.innerHTML = "";

    let i = 0;

    function drawStep() {

        if (i >= gantt.length) {
            drawTimeline(gantt); // 🔥 add time scale after animation
            return;
        }

        const g = gantt[i];

        let block = document.createElement("div");
        block.className = "gantt-block";

        // 🔥 WIDTH based on execution time (IMPORTANT)
        let duration = g.end - g.start;
        block.style.width = (duration * 40) + "px"; // scale factor

        block.style.opacity = "0";
        block.style.transform = "translateY(10px)";
        block.style.transition = "0.4s";

        block.innerHTML = `
            <div style="font-weight:bold">${g.id}</div>
            <small>${g.start} - ${g.end}</small>
        `;

        container.appendChild(block);

        // animation effect
        setTimeout(() => {
            block.style.opacity = "1";
            block.style.transform = "translateY(0)";
        }, 50);

        i++;
        setTimeout(drawStep, 500);
    }

    drawStep();
}