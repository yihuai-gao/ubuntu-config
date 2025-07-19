file_dir=$(dirname $(realpath $0))

alias sdbg4="sbatch $file_dir/jupyter_4hrs.sbatch"
# alias sdbg48="sbatch $file_dir/jupyter_48hrs.sbatch"
alias sdbga="sbatch $file_dir/jupyter_48hrs_a.sbatch"
alias sdbgb="sbatch $file_dir/jupyter_48hrs_b.sbatch"

alias sqe="squeue -u $USER --format='%.15i %.20P %.30j %.8T %.10M %.6D %R'"
alias sq="squeue  --format='%.15i %.20P %.30j %.10u %.8T %.10M %.6D %R'"
alias sc="scancel --signal=KILL"

jupyter_addr() {
    # Find the 3 largest number
        find /project/cosmos/yihuaig/jupyter_jobs -maxdepth 1 -type d -printf "%f\n" \
        | grep -E '^[0-9]+$' | sort -n | tail -n 5 | while read -r num; do
            file="/project/cosmos/yihuaig/jupyter_jobs/$num/jupyter.txt"
            if [ -f "$file" ]; then
                head -n 1 "$file"
            else
                echo "No jupyter.txt found for $num"
            fi
    done
}


alias start_tunneling="$file_dir/start_tunneling.sh"

init_container() {
    cp $i4/projects/cosmos/vla/experiments/robot/libero/10_nvidia.json /usr/share/glvnd/egl_vendor.d/10_nvidia.json

    pip install -e /project/cosmos/yihuaig/projects/LIBERO
    pip install -r /project/cosmos/yihuaig/projects/imaginaire4/projects/cosmos/vla/experiments/robot/libero/libero_requirements.txt


    # Remove jax import: comment out line 17-26
    sed -i '17,26s/^/#/' /usr/local/lib/python3.12/dist-packages/transformer_engine/__init__.py

}
