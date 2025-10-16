file_dir=$(dirname $(realpath $0))

alias sdbg4="sbatch $file_dir/jupyter_4hrs.sbatch"
alias sdbg="sbatch $file_dir/jupyter_48hrs.sbatch"

alias sqe="squeue -u $USER --format='%.15i %.20P %.70j %.8T %.10M %.6D %R'"
alias sq="squeue  --format='%.15i %.20P %.100j %.10u %.8T %.10M %.6D %R'"
alias sc="scancel --signal=KILL"
alias srq="scontrol requeue"

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

# For imitation_learning_policies
alias sim_train="sbatch slurm_scripts/slurm_training_sim.sbatch"
alias real_train="sbatch slurm_scripts/slurm_training_real.sbatch"
alias seval="sbatch slurm_scripts/slurm_eval.sbatch"

init_container() {

    # Install system dependencies
    apt update
    apt install libnl-genl-3-200 -y
    apt install lsof -y
    apt install rclone fuse3 -y
    apt install lz4 -y
    apt-get install libxmu6 -y
    
    cp $i4/projects/cosmos/vla/experiments/robot/libero/10_nvidia.json /usr/share/glvnd/egl_vendor.d/10_nvidia.json

    pip install -e /project/cosmos/yihuaig/projects/LIBERO
    pip install -r /project/cosmos/yihuaig/projects/imaginaire4/projects/cosmos/vla/experiments/robot/libero/libero_requirements.txt
    pip install robotmq

    # For UMI dataset
    pip install imagecodecs

    # For mujoco-env
    apt install libspnav-dev -y 
    mkdir /tmp/rollout_policy_online

    # Remove jax import: comment out line 17-26
    sed -i '17,26s/^/#/' /usr/local/lib/python3.12/dist-packages/transformer_engine/__init__.py

    cd $HOME
    rclone mount s3: s3

}
