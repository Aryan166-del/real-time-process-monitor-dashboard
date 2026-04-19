const socket = io();

// Data arrays
let cpuData = [];
let memoryData = [];
let labels = [];

// Max graph points
const MAX_POINTS = 40;

// CPU Chart
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
        plugins: {
            legend: { display: true }
        },
        scales: {
            x: { display: false },
            y: { min: 0, max: 100 }
        }
    }
});

// MEMORY Chart
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
        plugins: {
            legend: { display: true }
        },
        scales: {
            x: { display: false },
            y: { min: 0, max: 100 }
        }
    }
});

// Socket connected
socket.on('connect', () => {
    console.log("✅ Connected to server");
});

// MAIN DATA EVENT
socket.on('stats', data => {

    // 🔹 Update stats
    document.getElementById("cpu").innerText = data.cpu + "%";
    document.getElementById("memory").innerText = data.memory + "%";
    document.getElementById("processes").innerText = data.processes;
    document.getElementById("status").innerText = data.status;

    // 🔹 Status color (realistic)
    const statusEl = document.getElementById("status");
    if (data.status === "Healthy") {
        statusEl.style.color = "#22c55e";
    } else if (data.status === "Moderate") {
        statusEl.style.color = "#f59e0b";
    } else {
        statusEl.style.color = "#ef4444";
    }

    // 🔹 Update process table
    const table = document.getElementById("table");
    table.innerHTML = "";

    data.process_list.forEach(p => {

        let row = document.createElement("tr");

        // 🔥 Dynamic CPU color
        let cpuColor =
            p.cpu_percent > 50 ? "#ef4444" :
            p.cpu_percent > 20 ? "#f59e0b" :
            "#22c55e";

        row.innerHTML = `
            <td>${p.pid}</td>
            <td>${p.name}</td>
            <td style="color:${cpuColor}; font-weight:bold;">
                ${p.cpu_percent.toFixed(1)}%
            </td>
            <td>${p.memory_percent.toFixed(1)}%</td>
            <td>
                <button onclick="killProcess(${p.pid})">
                    End
                </button>
            </td>
        `;

        table.appendChild(row);
    });

    // 🔥 Graph update (smooth + limited)
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


// 🔥 Kill process (improved UX)
function killProcess(pid) {

    if (!confirm(`Are you sure you want to kill PID ${pid}?`)) return;

    fetch('/kill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pid })
    })
    .then(res => res.json().then(data => ({
        status: res.status,
        body: data
    })))
    .then(res => {

        if (res.status === 200) {
            showToast(res.body.message, "success");
        } else {
            showToast(res.body.message, "error");
        }

    })
    .catch(() => {
        showToast("❌ Network error", "error");
    });
}


// 🔥 Professional Toast Notification
function showToast(message, type = "success") {

    const toast = document.createElement("div");

    toast.innerText = message;

    toast.style.position = "fixed";
    toast.style.bottom = "20px";
    toast.style.right = "20px";
    toast.style.padding = "12px 20px";
    toast.style.borderRadius = "10px";
    toast.style.color = "white";
    toast.style.fontSize = "14px";
    toast.style.zIndex = "9999";
    toast.style.opacity = "0";
    toast.style.transition = "0.3s";

    // 🔥 Colors
    if (type === "success") {
        toast.style.background = "#22c55e";
    } else {
        toast.style.background = "#ef4444";
    }

    document.body.appendChild(toast);

    // Animate
    setTimeout(() => {
        toast.style.opacity = "1";
        toast.style.transform = "translateY(-10px)";
    }, 100);

    // Remove
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}