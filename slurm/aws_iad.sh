file_dir=$(dirname $(realpath $0))

alias sdbg4="sbatch $file_dir/jupyter_4hrs.sbatch"
alias sdbg48="sbatch $file_dir/jupyter_48hrs.sbatch"

alias sqe="squeue -u $USER --format='%.15i %.20P %.30j %.8T %.10M %.6D %R'"
alias sq="squeue  --format='%.15i %.20P %.30j %.8T %.10M %.6D %R'"
alias sc="scancel --signal=KILL"

jupyter_addr() {
    # Find the 3 largest number
        find /project/cosmos/yihuaig/jupyter_jobs -maxdepth 1 -type d -printf "%f\n" \
        | grep -E '^[0-9]+$' | sort -n | tail -n 3 | while read -r num; do
            file="/project/cosmos/yihuaig/jupyter_jobs/$num/jupyter.txt"
            if [ -f "$file" ]; then
                head -n 1 "$file"
            else
                echo "No jupyter.txt found for $num"
            fi
    done
}


alias start_tunneling="$file_dir/start_tunneling.sh"