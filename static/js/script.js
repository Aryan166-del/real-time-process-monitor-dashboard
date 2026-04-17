function fetchData() {
    fetch('/data')
        .then(response => response.json())
        .then(data => {
            document.getElementById("cpu").innerText = data.cpu + "%";
            document.getElementById("memory").innerText = data.memory + "%";
            document.getElementById("processes").innerText = data.processes;
            document.getElementById("status").innerText = data.status;
        });
}

// call once immediately
fetchData();

// then repeat every 2 seconds
setInterval(fetchData, 2000);