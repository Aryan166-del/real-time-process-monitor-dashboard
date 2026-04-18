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

//  Fetch Data Function
function fetchData() {
    fetch('/data')
        .then(response => response.json())
        .then(data => {

            //  Update cards
            document.getElementById("cpu").innerText = data.cpu + "%";
            document.getElementById("memory").innerText = data.memory + "%";
            document.getElementById("processes").innerText = data.processes;
            document.getElementById("status").innerText = data.status;

            //  Progress bars
            document.getElementById("cpu-bar").style.width = data.cpu + "%";
            document.getElementById("memory-bar").style.width = data.memory + "%";

            //  Dynamic color for bars
            let cpuBar = document.getElementById("cpu-bar");
            cpuBar.className = "progress-fill";

            if (data.cpu < 50) {
                cpuBar.classList.add("green");
            } else if (data.cpu < 80) {
                cpuBar.classList.add("orange");
            } else {
                cpuBar.classList.add("red");
            }

            //  Status color
            let statusEl = document.getElementById("status");

            if (data.status === "Healthy") {
                statusEl.style.color = "green";
            } else if (data.status === "Moderate") {
                statusEl.style.color = "orange";
            } else {
                statusEl.style.color = "red";
            }

            //  Update Table
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

                //  Highlight heavy processes
                if (proc.cpu_percent > 20) {
                    row.style.color = "red";
                    row.style.fontWeight = "bold";
                }

                table.appendChild(row);
            });

            //  Update Graph
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

//  Initialize Chart
createChart();

//  First call
fetchData();

//  Refresh every 2 seconds
setInterval(fetchData, 2000);