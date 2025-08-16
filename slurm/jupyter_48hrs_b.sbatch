#!/bin/bash

#SBATCH --job-name=1N@debug@yihuaig_jupyter_robot_08@p0
#SBATCH --nodes=1
#SBATCH --time=48:00:00
#SBATCH --time-min=48:00:00
#SBATCH --partition=pool0_datahall_b
#SBATCH --ntasks-per-node=8
#SBATCH --account=dir_cosmos_base
#SBATCH --exclusive
#SBATCH --gres=gpu:8
#SBATCH --output=/project/cosmos/yihuaig/jupyter_jobs/%j/job.out
#SBATCH --error=/project/cosmos/yihuaig/jupyter_jobs/%j/job.err
#SBATCH --exclude=pool0-0023,pool0-0006,pool0-0028,pool0-0002
#SBATCH --requeue

# Alternative

# /project/cosmos/
export MASTER_PORT=$(expr 10000 + $(echo -n $SLURM_JOBID | tail -c 4))
export WORLD_SIZE=$(($SLURM_NNODES * $SLURM_NTASKS_PER_NODE))
export MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)
export SLURM_LOG_DIR=/project/cosmos/yihuaig/jupyter_jobs/$SLURM_JOB_ID
export HOST_USER_ID=$(id -u)
echo "Nodelist="$SLURM_JOB_NODELIST
echo "MASTER_PORT="$MASTER_PORT
echo "WORLD_SIZE="$WORLD_SIZE
echo "MASTER_ADDR="$MASTER_ADDR
echo "SLURM_LOG_DIR="$SLURM_LOG_DIR
mkdir -p $SLURM_LOG_DIR/env
env > $SLURM_LOG_DIR/env/sbatch_env.sh

export DOCKER_PATH=nvcr.io/nvidian/imaginaire4:v10.1.0_egl_fix
srun --container-image=${DOCKER_PATH} --container-mounts /project/cosmos:/project/cosmos:rw,/home/yihuaig:/home/yihuaig:rw \
   bash -c 'LOCAL_RANK=$SLURM_LOCALID; env >> ${SLURM_LOG_DIR}/env/${SLURM_PROCID}.sh 2>&1; ulimit -c 0; export LD_LIBRARY_PATH=/opt/amazon/openmpi/lib:/opt/nccl/build/lib:/opt/amazon/efa/lib:/opt/aws-ofi-nccl/install/lib:/usr/local/lib:$LD_LIBRARY_PATH; export WANDB_ENTITY=nvidia-dir; export TORCH_NCCL_ENABLE_MONITORING=0; export TORCH_NCCL_HEARTBEAT_TIMEOUT_SEC=1800; export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True; export IMAGINAIRE_OUTPUT_ROOT=/project/cosmos/yihuaig/imaginaire4-output; export HOST_IP=$(python -c "import socket;print(socket.gethostbyname(socket.gethostname()))"); printf "%-50s %-20s %s\n" "${SLURM_JOB_NAME}" "${SLURM_JOBID}" "$HOST_IP:$MASTER_PORT" >> "${SLURM_LOG_DIR}/jupyter.txt"; printf "%-50s %-20s %s\n" "${SLURM_JOB_NAME}" "${SLURM_JOBID}" "$HOST_IP:$MASTER_PORT" >> "$HOME/jupyter.txt"; jupyter lab --allow-root --ip=0.0.0.0 --port=$MASTER_PORT --no-browser --NotebookApp.token="" --notebook-dir=/project/cosmos/yihuaig --NotebookApp.allow_origin="*" >> ${SLURM_LOG_DIR}/log_${SLURM_PROCID}.txt 2>&1'
