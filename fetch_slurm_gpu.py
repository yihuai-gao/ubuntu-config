import subprocess
import re
from tabulate import tabulate

def parse_scontrol_output(output):
    node_info = {}
    node_lines = output.splitlines()

    # Initialize values in case some fields are missing
    node_info['AllocatedGPU'] = 0  
    node_info['TotalGPU'] = 0

    for line in node_lines:
        if "NodeName=" in line:
            node_info['NodeName'] = re.search(r"NodeName=(\S+)", line).group(1)
        if "CPUTot=" in line:
            node_info['TotalCPU'] = int(re.search(r"CPUTot=(\d+)", line).group(1))
        if "CPUAlloc=" in line:
            node_info['AllocatedCPU'] = int(re.search(r"CPUAlloc=(\d+)", line).group(1))
        if "RealMemory=" in line:
            node_info['TotalMemory'] = int(re.search(r"RealMemory=(\d+)", line).group(1)) // 1024  # Convert to GB
        if "AllocMem=" in line:
            node_info['AllocatedMemory'] = int(re.search(r"AllocMem=(\d+)", line).group(1)) // 1024  # Convert to GB
        if "FreeMem=" in line:
            node_info['FreeMemory'] = int(re.search(r"FreeMem=(\d+)", line).group(1)) // 1024  # Convert to GB
        if "Gres=gpu:" in line:
            gpu_match = re.search(r"Gres=gpu:(\d+)", line)
            if gpu_match:
                node_info['TotalGPU'] = int(gpu_match.group(1))
        if "AllocTRES=" in line:
            alloc_gpu_match = re.search(r"gres/gpu=(\d+)", line)
            if alloc_gpu_match:
                node_info['AllocatedGPU'] = int(alloc_gpu_match.group(1))

    # Calculate available resources
    node_info['AvailableCPU'] = node_info['TotalCPU'] - node_info['AllocatedCPU']
    node_info['AvailableMemory'] = node_info['TotalMemory'] - node_info['AllocatedMemory']
    node_info['AvailableGPU'] = node_info['TotalGPU'] - node_info['AllocatedGPU']

    return node_info

def get_node_status(node_name):
    # Run scontrol to get node details
    cmd = ["scontrol", "show", "node", node_name]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return parse_scontrol_output(result.stdout)

def fetch_all_nodes():
    # Fetch all nodes from sinfo
    cmd = ["sinfo", "--noheader", "-N", "-o", "%N"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip().split("\n")

def display_node_resources():
    nodes = fetch_all_nodes()
    node_data = [get_node_status(node) for node in nodes]

    # Prepare tabulated data
    table_data = [
        {
            "Node": node['NodeName'],
            "Total/Avail CPU": f"{node['TotalCPU']}/{node['AvailableCPU']}",
            "Total/Avail Memory (GB)": f"{node['TotalMemory']}/{node['AvailableMemory']}",
            "Total/Avail GPUs": f"{node['TotalGPU']}/{node['AvailableGPU']}"
        }
        for node in node_data
    ]

    # Display the collected data
    print(tabulate(
        table_data,
        headers={"Node": "Node", "Total/Avail CPU": "Total/Avail CPU", 
                 "Total/Avail Memory (GB)": "Total/Avail Memory (GB)", "Total/Avail GPUs": "Total/Avail GPUs"},
        tablefmt="pretty"
    ))

if __name__ == "__main__":
    display_node_resources()