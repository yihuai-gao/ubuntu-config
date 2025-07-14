#### SLURM related ####

alias sqe="squeue -u $USER --format='%.18i %.9P %.30j %.8T %.10M %.6D %R'"
alias sq="squeue"
alias sc="scancel"

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
        job_id=$(squeue -u $USER --format='%.18i %.9P %.30j %.8T %.10M %.6D %R' | grep RUNNING | awk '{print $1}')
        if [ -z "$job_id" ]; then
            echo "No running job found"
            return 1
        fi
        # If there are multiple running jobs, print them and ask for the job id
        if [ $(echo "$job_id" | wc -l) -gt 1 ]; then
            echo "Multiple running jobs found:"
            squeue -u $USER --format='%.18i %.9P %.30j %.8T %.10M %.6D %R' | grep RUNNING
            echo "Please enter the job id:"
            read job_id
        fi
    else
        job_id=$1
    fi
    srun --jobid $job_id --pty zsh
}

alias sal="salloc -N 1 -G 8 -A marlowe-m000073 -p preempt --mem=1600G --cpus-per-task=112 --time=12:00:00"
alias salb="salloc -N 1 -G 8 -A marlowe-m000073-pm01 -p batch --mem=1600G --cpus-per-task=112 --time=12:00:00"
alias salb2="salloc -N 1 -G 8 -A marlowe-m000073-pm01 -p batch --mem=1600G --cpus-per-task=112 --time=2:00:00"
alias sr="sreport cluster UserUtilizationByAccount -T gres/gpu Start=2025-05-20T00:00:00 End=now account=Marlowe-m000073-pm01  -t hours"
