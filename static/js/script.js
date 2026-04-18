//  Chart variables
let cpuData = [];
let labels = [];
let chart;

//  Create Chart
function createChart() {
    const ctx = document.getElementById('cpuChart').getContext('2d');

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'CPU Usage (%)',
                data: cpuData,
                borderWidth: 2,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    min: 0,
                    max: 100
                }
            }
        }
    });
}

// 🔥 Fetch Data Function
function fetchData() {
    fetch('/data')
        .then(response => response.json())
        .then(data => {

            // Update dashboard cards
            document.getElementById("cpu").innerText = data.cpu + "%";
            document.getElementById("memory").innerText = data.memory + "%";
            document.getElementById("processes").innerText = data.processes;
            document.getElementById("status").innerText = data.status;

            // 🔥 Update Top Processes Table
            let table = document.getElementById("processTable");
            table.innerHTML = "";

            data.top_processes.forEach(proc => {
                let row = document.createElement("tr");

                row.innerHTML = `
                    <td>${proc.pid}</td>
                    <td>${proc.name}</td>
                    <td>${proc.cpu_percent.toFixed(1)}%</td>
                    <td>${proc.memory_percent.toFixed(1)}%</td>
                `;

                table.appendChild(row);
            });

            // 🔥 Update Graph Data
            if (cpuData.length > 10) {
                cpuData.shift();
                labels.shift();
            }

            cpuData.push(data.cpu);
            labels.push(new Date().toLocaleTimeString());

            chart.update();
        })
        .catch(error => {
            console.error("Error fetching data:", error);
        });
}

// 🔥 Initialize Chart
createChart();

// 🔥 First call
fetchData();

// 🔥 Refresh every 2 seconds
setInterval(fetchData, 2000);