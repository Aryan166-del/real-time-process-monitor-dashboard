function fetchData() {
    fetch('/data')
        .then(response => response.json())
        .then(data => {

            //  Update dashboard cards
            document.getElementById("cpu").innerText = data.cpu + "%";
            document.getElementById("memory").innerText = data.memory + "%";
            document.getElementById("processes").innerText = data.processes;
            document.getElementById("status").innerText = data.status;

            // 🔥 Update Top Processes Table
            let table = document.getElementById("processTable");
            table.innerHTML = ""; // clear old data

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

        })
        .catch(error => {
            console.error("Error fetching data:", error);
        });
}

//Call once immediately
fetchData();

// Refresh every 2 seconds
setInterval(fetchData, 2000);