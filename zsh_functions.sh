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
alias ze="zoxide edit"
alias ncdu="ncdu -t8"


alias fetch_gpu="$CONDA_PYTHON_EXE ~/ubuntu-config/fetch_gpu.py"
alias fetch_slurm_gpu="$CONDA_PYTHON_EXE ~/ubuntu-config/fetch_slurm_gpu.py"

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






function calc_lines() {
    if [ $# -ne 1 ]; then
        echo "Usage: calc_lines <suffix>"
        return 1
    fi
    suffix=$1
    find . -name "*.${suffix}" -type f | xargs wc -l
}


function port() {
    lsof -i :$1
}

function port_kill() {
    lsof -i :$1 | tail -n +2 | awk '{print $2}' | xargs kill -9
}

alias cursor_pull="~/ubuntu-config/config_cursor.sh pull"
alias cursor_push="~/ubuntu-config/config_cursor.sh push"

alias vpn="sudo openconnect --useragent=AnyConnect --no-external-auth --authgroup='Stanford' --user=yihuai su-vpn.stanford.edu"
alias ca="conda activate"
alias f="fzf --reverse"