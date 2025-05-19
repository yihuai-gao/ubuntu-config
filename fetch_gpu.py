import paramiko
import json
import time
from rich.console import Console
from rich.table import Table
from concurrent.futures import ThreadPoolExecutor, as_completed

# Define your server details
SERVERS = ["real002", "real003", "real004", "real005", "real006", "real007"]

OWNERS = {
    "real002": [
        "Chuer", "Chuer", "Chuer/Hojung", "Chuer/Hojung", "Max", "Max", "Zhanyi", "Zhanyi"
    ],
    "real003": [
        "", "", "Austin", "Austin", "John/Eric", "John/Eric", "John", "John"
    ],
    "real004": [
        "Mengda", "Mengda", "Mengda", "Mengda"
    ],
    "real005": [
        "Zeyi", "Zeyi", "Zeyi", "Zeyi"
    ],
    "real006": [
        "Xiaomeng/Haoyu", "Xiaomeng/Haoyu", "Xiaomeng/Haoyu", "Huy/Mengda", "Huy/Mengda", "Huy/Mengda", "Huy/Mengda"
    ],
    "real007": [
        "Mandi", "Mandi", "", "", "", "", "Hojung", "Hojung"
    ]
}
USERNAME = "yihuai"  # Change to your SSH username
PASSWORD = None  # Set if using password authentication; use None for key-based auth
GPUSTAT_CMD = "gpustat --json"

console = Console()

def fetch_gpustat(server):
    """SSH into the server and fetch GPU stats using gpustat"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if not server.endswith(".stanford.edu"):
            server = server + ".stanford.edu"
        
        if PASSWORD:
            client.connect(server, username=USERNAME, password=PASSWORD, timeout=5)
        else:
            client.connect(server, username=USERNAME, timeout=5)  # Assumes key-based auth
        
        stdin, stdout, stderr = client.exec_command(GPUSTAT_CMD)
        output = stdout.read().decode("utf-8")
        client.close()
        
        return json.loads(output) if output else None
    except Exception as e:
        return {"error": str(e)}

def display_stats():
    """Fetch and display GPU stats from all servers in real-time"""
    while True:
        table = Table(title="GPU Usage Across Servers", show_lines=True)
        table.add_column("Server", style="bold cyan")
        # table.add_column("GPUs", style="bold magenta")
        table.add_column("Usage", style="bold yellow")
        table.add_column("Memory", style="bold green")
        table.add_column("Owners", style="bold cyan")
        table.add_column("Users", style="bold blue")

        results = {}

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=len(SERVERS)) as executor:
            future_to_server = {executor.submit(fetch_gpustat, server): server for server in SERVERS}
            for future in as_completed(future_to_server):
                server = future_to_server[future]
                try:
                    data = future.result()
                except Exception as e:
                    data = {"error": str(e)}

                results[server] = data
        
        end_time = time.time()
        elapsed_time = end_time - start_time


        for server in SERVERS:
            data = results.get(server, {"error": "No data"})


            if data is None:
                table.add_row(server, "Error", "-", "-", "-")
            elif "error" in data:
                table.add_row(server, "Error", "-", "-", data["error"])
                continue

            gpu_ids = []
            utilizations = []
            memories = []
            users_list = []
            users_dict = {}

            for gpu in data["gpus"]:
                gpu_ids.append(str(gpu["index"]))
                
                utilization = gpu["utilization.gpu"]
                utilization_color = "green" if utilization < 50 else "yellow" if utilization <= 80 else "red"
                utilizations.append(f'[{utilization_color}]{utilization}%[/{utilization_color}]')
                
                memory_used = gpu["memory.used"] / 1024.0
                memory_total = gpu["memory.total"] / 1024.0
                memory_percentage = (memory_used / memory_total) * 100
                memory_color = "green" if memory_percentage < 50 else "yellow" if memory_percentage <= 80 else "red"
                memories.append(f'[{memory_color}]{memory_used:.1f}/{memory_total:.1f}G[/{memory_color}]')
                
                users_dict = {}
                if "processes" in gpu:
                    for proc in gpu["processes"]:
                        username = proc["username"]
                        proc_memory = proc.get("gpu_memory_usage", 0)  # Assuming 'gpu_memory_usage' is in MB
                        if username in users_dict:
                            users_dict[username] += proc_memory
                        else:
                            users_dict[username] = proc_memory
                users_list.append(", ".join([f"{user}({mem/1024:.1f}G)" for user, mem in users_dict.items()]))

            # Merge users and sum their memory usage
            owners = OWNERS[server] if server in OWNERS else []
            table.add_row(
                server,
                # ", ".join(gpu_ids),
                "\n".join(utilizations),
                "\n".join(memories),
                "\n".join(owners),
                "\n".join(users_list)
            )

        console.clear()
        console.print(table)
        # time.sleep(5)  # Refresh every 5 seconds
        # print(f"Time taken to fetch and display stats: {elapsed_time:.2f} seconds")

        break # You can remove this line to keep the stats updating

if __name__ == "__main__":
    display_stats()