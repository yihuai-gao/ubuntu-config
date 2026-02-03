# Fish shell functions and aliases
# Equivalent to zsh_functions.sh

# Yazi file manager wrapper with cd on exit
function y
    set tmp (mktemp -t "yazi-cwd.XXXXXX")
    yazi $argv --cwd-file="$tmp"
    if set cwd (cat -- "$tmp"); and [ -n "$cwd" ]; and [ "$cwd" != "$PWD" ]
        cd -- "$cwd"
    end
    rm -f -- "$tmp"
end

# Rsync pull function
function rsync_pull
    # Usage: arg1: server_name, arg2: path_name (optional)
    # Pull the directory if no file name is provided

    if test (count $argv) -eq 0
        echo "Usage: rsync_pull <server_name> [path_name]"
        return 1
    end

    if test (count $argv) -gt 2
        echo "Usage: rsync_pull <server_name> [path_name]"
        return 1
    end

    set server $argv[1]
    set current_dir (basename (pwd))
    set current_dir_full_path (string replace -r "^$HOME/" "" "$PWD")

    if test (count $argv) -eq 2
        set path_name $argv[2]
    else
        set path_name "."
    end

    echo "Pulling from $server:$current_dir_full_path/$path_name"

    # Create the parent directory if it does not exist
    mkdir -p "$path_name"

    echo "Pulling the directory $path_name"
    # Pull the directory
    rsync -rzvP \
        --exclude-from=(git ls-files --others --ignored --exclude-standard --directory | psub) \
        --exclude='third_party' \
        --exclude='prior_works' \
        --exclude='.DS_Store' \
        "$server:$current_dir_full_path/$path_name/" \
        $path_name
end

# SCP pull function
function scp_pull
    # Usage: arg1: server_name, arg2: file_name
    if test (count $argv) -ne 2
        echo "Usage: scp_pull <server_name> <file_path>"
        return 1
    end

    set current_dir_full_path (string replace -r "^$HOME/" "" "$PWD")
    set server $argv[1]
    set file_path $argv[2]
    set parent_dir (dirname "$file_path")

    mkdir -p "$parent_dir"
    set cmd "scp $server:$current_dir_full_path/$file_path $parent_dir"
    echo $cmd
    eval $cmd
end

# Compress function using tar + lz4
function compress
    if test (count $argv) -ne 1
        echo "Usage: compress <data_storage_dir>"
        return 1
    end

    set current_dir (pwd)
    set data_storage_dir $argv[1]
    set cpu_cores (math (nproc) - 1)
    set file_name (basename $data_storage_dir)

    cd (dirname $data_storage_dir)
    tar cf - $file_name | lz4 -c > $file_name.tar.lz4
    cd $current_dir
end

# Decompress function for lz4 + tar
function decompress
    if test (count $argv) -ne 1
        echo "Usage: decompress <file_path>"
        return 1
    end

    set current_dir (pwd)
    set file_path $argv[1]
    set cpu_cores (math (nproc) - 1)
    set file_name (basename $file_path)

    cd (dirname $file_path)
    lz4 -d -c $file_name | tar xf -
    cd $current_dir
end

# Calculate lines of code by suffix
function calc_lines
    if test (count $argv) -ne 1
        echo "Usage: calc_lines <suffix>"
        return 1
    end

    set suffix $argv[1]
    find . -name "*.$suffix" -type f | xargs wc -l
end

# Show processes on a port
function port
    lsof -i :$argv[1]
end

# Kill processes on a port
function port_kill
    lsof -i :$argv[1] | tail -n +2 | awk '{print $2}' | xargs kill -9
end

# Aliases
alias c="cursor"
alias hn="hostname"
alias ze="zoxide edit"
alias ncdu="ncdu -t8"

alias fetch_gpu="\$CONDA_PYTHON_EXE ~/ubuntu-config/fetch_gpu.py"
alias fetch_slurm_gpu="\$CONDA_PYTHON_EXE ~/ubuntu-config/fetch_slurm_gpu.py"

alias cursor_pull="~/ubuntu-config/config_cursor.sh pull"
alias cursor_push="~/ubuntu-config/config_cursor.sh push"

alias vpn="sudo openconnect --useragent=AnyConnect --no-external-auth --authgroup='Stanford' --user=yihuai su-vpn.stanford.edu"
alias ca="conda activate"
alias f="fzf | sort"
alias ls="ls -lah --color=auto"
