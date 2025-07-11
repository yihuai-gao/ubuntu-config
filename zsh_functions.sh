function y() {
	local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
	yazi "$@" --cwd-file="$tmp"
	if cwd="$(command cat -- "$tmp")" && [ -n "$cwd" ] && [ "$cwd" != "$PWD" ]; then
		builtin cd -- "$cwd"
	fi
	rm -f -- "$tmp"
}
function rsync_pull() {
    # Usage: arg1: server_name, arg2: path_name (optional)
    # Pull the directory if no file name is provided

    if [ $# -eq 0 ]; then
        echo "Usage: rsync_pull <server_name> [path_name]"
        return 1
    fi

    if [ $# -gt 2 ]; then
        echo "Usage: rsync_pull <server_name> [path_name]"
        return 1
    fi
    

    local server="$1"
    local current_dir=$(basename "$(pwd)")
    local current_dir_full_path="${PWD#$HOME/}"


    if [ $# -eq 2 ]; then
        local path_name="$2"
    else
        local path_name="."
    fi


    echo "Pulling from ${server}:${current_dir_full_path}/${path_name}"

    # Create the parent directory if it does not exist
    mkdir -p "$path_name"

    echo "Pulling the directory ${path_name}"
    # Pull the directory
    rsync -rzvP \
    --exclude-from=<(git ls-files --others --ignored --exclude-standard --directory) \
    --exclude='third_party' \
    --exclude='prior_works' \
    --exclude='.DS_Store' \
    "${server}:${current_dir_full_path}/${path_name}/" \
    $path_name
}

function scp_pull() {
    # Usage: arg1: server_name, arg2: file_name
    if [ $# -ne 2 ]; then
        echo "Usage: scp_pull <server_name> <file_path>"
        return 1
    fi
    local current_dir_full_path="${PWD#$HOME/}"

    local server="$1"
    local file_path="$2"

    local parent_dir=$(dirname "$file_path")
    mkdir -p "$parent_dir"
    cmd="scp ${server}:${current_dir_full_path}/${file_path} $parent_dir"
    echo $cmd
    eval $cmd
}


alias c="cursor"
alias hn="hostname"

alias fetch_gpu="~/miniforge3/bin/python ~/ubuntu-config/fetch_gpu.py"
alias fetch_slurm_gpu="~/miniforge3/bin/python ~/ubuntu-config/fetch_slurm_gpu.py"

function compress() {
    if [ $# -ne 1 ]; then
        echo "Usage: compress <data_storage_dir>"
        return 1
    fi
    current_dir=$(pwd)
    data_storage_dir=$1
    cpu_cores=$(($(nproc) - 1))
    file_name=$(basename $data_storage_dir)
    cd $(dirname $data_storage_dir)
    tar cf - ${file_name} | lz4 -c > ${file_name}.tar.lz4
    cd $current_dir
}

function decompress() {
    if [ $# -ne 1 ]; then
        echo "Usage: decompress <file_path>"
        return 1
    fi
    current_dir=$(pwd)
    file_path=$1
    cpu_cores=$(($(nproc) - 1))
    file_name=$(basename $file_path)
    cd $(dirname $file_path)
    lz4 -d -c ${file_name} | tar xf -
    cd $current_dir
}




#### SLURM related ####


# get gpu_num gpus
function sdbg() {
    if [ $# -eq 0 ]; then
        gpu_num=1
        node_name="-N 1"
    elif [ $# -eq 1 ]; then
        gpu_num=$1
        node_name="-N 1"
    elif [ $# -eq 2 ]; then
        gpu_num=$1
        node_name="--nodelist=$2"
    fi
    cpu_num=$((($gpu_num)*14))
    cpu_num=$(($cpu_num > 112 ? 112 : $cpu_num))
    cpu_num=$(($cpu_num < 16 ? 16 : $cpu_num))
    mem_num=$((($gpu_num)*200))
    mem_num=$(($mem_num > 1800 ? 1800 : $mem_num))
    mem_num=$(($mem_num < 100 ? 100 : $mem_num))
    command="salloc $node_name -G $gpu_num -A marlowe-m000073 -p preempt --mem=${mem_num}G --cpus-per-task=$cpu_num --time=02:00:00"
    echo $command
    eval $command
}

function sdbg1() {
    if [ $# -eq 0 ]; then
        gpu_num=1
        node_name="-N 1"
    elif [ $# -eq 1 ]; then
        gpu_num=$1
        node_name="-N 1"
    elif [ $# -eq 2 ]; then
        gpu_num=$1
        node_name="--nodelist=$2"
    fi
    cpu_num=$((($gpu_num)*14))
    cpu_num=$(($cpu_num > 112 ? 112 : $cpu_num))
    cpu_num=$(($cpu_num < 16 ? 16 : $cpu_num))
    mem_num=$((($gpu_num)*200))
    mem_num=$(($mem_num > 1800 ? 1800 : $mem_num))
    mem_num=$(($mem_num < 100 ? 100 : $mem_num))
    command="salloc $node_name -G $gpu_num -A marlowe-m000073 -p preempt --mem=${mem_num}G --cpus-per-task=$cpu_num --time=01:00:00"
    echo $command
    eval $command
}


function sa() {
    if [ $# -ne 1 ]; then
        job_id=$(squeue -u yihuai --format='%.18i %.9P %.30j %.8T %.10M %.6D %R' | grep RUNNING | awk '{print $1}')
        if [ -z "$job_id" ]; then
            echo "No running job found"
            return 1
        fi
        # If there are multiple running jobs, print them and ask for the job id
        if [ $(echo "$job_id" | wc -l) -gt 1 ]; then
            echo "Multiple running jobs found:"
            squeue -u yihuai --format='%.18i %.9P %.30j %.8T %.10M %.6D %R' | grep RUNNING
            echo "Please enter the job id:"
            read job_id
        fi
    else
        job_id=$1
    fi
    srun --jobid $job_id --pty zsh
}

alias sqe="squeue -u yihuai --format='%.18i %.9P %.30j %.8T %.10M %.6D %R'"
alias sq="squeue"
alias sc="scancel"

function calc_lines() {
    if [ $# -ne 1 ]; then
        echo "Usage: calc_lines <suffix>"
        return 1
    fi
    suffix=$1
    find . -name "*.${suffix}" -type f -exec cat {} + | wc -l
}

alias sal="salloc -N 1 -G 8 -A marlowe-m000073 -p preempt --mem=1600G --cpus-per-task=112 --time=12:00:00"
alias salb="salloc -N 1 -G 8 -A marlowe-m000073-pm01 -p batch --mem=1600G --cpus-per-task=112 --time=12:00:00"
alias salb2="salloc -N 1 -G 8 -A marlowe-m000073-pm01 -p batch --mem=1600G --cpus-per-task=112 --time=2:00:00"
alias sr="sreport cluster UserUtilizationByAccount -T gres/gpu Start=2025-05-20T00:00:00 End=now account=Marlowe-m000073-pm01  -t hours"

function port() {
    lsof -i :$1
}

function port_kill() {
    lsof -i :$1 | tail -n +2 | awk '{print $2}' | xargs kill -9
}