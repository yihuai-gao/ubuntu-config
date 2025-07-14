file_dir=$(dirname $(realpath $0))

alias sdbg4="sbatch $file_dir/jupyter_4hrs.sbatch"
alias sdbg48="sbatch $file_dir/jupyter_48hrs.sbatch"

alias sqe="squeue -u $USER --format='%.18i %.9P %.30j %.8T %.10M %.6D %R'"
alias sq="squeue"
alias sc="scancel --signal=KILL"