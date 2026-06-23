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
alias ncdu="ncdu -t32 -1x"

function cncdu() {
    target_dir=$1
    if [ -z "$target_dir" ]; then
        target_dir=.
    fi
    # Get absolute path
    target_dir=$(realpath $target_dir)
    # Replace / with _
    cache_name=$(echo $target_dir | sed 's/\//_/g')
    cache_name="${cache_name}_ncdu_cache.gz"
    thread_num=$2
    nohup_file=$HOME/.cache/ncdu/$cache_name.nohup

    if [ -z "$thread_num" ]; then
        thread_num=8
    fi
    if [ ! -d "$HOME/.cache/ncdu" ]; then
        mkdir -p $HOME/.cache/ncdu
    fi
    nohup /home/$USER/.local/usr/bin/ncdu -t$thread_num -1xo $HOME/.cache/ncdu/$cache_name $target_dir > $nohup_file 2>&1 &
}

function lncdu() {
    target_dir=$1
    if [ -z "$target_dir" ]; then
        target_dir=.
    fi
    # Get absolute path
    target_dir=$(realpath $target_dir)
    # Replace / with _
    cache_name=$(echo $target_dir | sed 's/\//_/g')
    cache_name="${cache_name}_ncdu_cache.gz"
    cache_bak_name="${cache_name}.bak"
    cp $HOME/.cache/ncdu/$cache_name $HOME/.cache/ncdu/$cache_bak_name
    /home/$USER/.local/usr/bin/ncdu -f $HOME/.cache/ncdu/$cache_bak_name
}


alias fetch_gpu="$CONDA_PYTHON_EXE ~/ubuntu-config/fetch_gpu.py"
alias fetch_slurm_gpu="$CONDA_PYTHON_EXE ~/ubuntu-config/fetch_slurm_gpu.py"

function compress() {
    # Check if we have at least 1 and no more than 2 arguments
    if [ $# -lt 1 ] || [ $# -gt 2 ]; then
        echo "Usage: compress <data_storage_dir> [target_dir]"
        return 1
    fi

    local current_dir=$(pwd)
    local data_storage_dir=$1
    local file_name=$(basename "$data_storage_dir")
    local source_parent_dir=$(dirname "$data_storage_dir")
    
    # Determine the target directory
    # If $2 is provided, use it; otherwise, use the current directory
    local target_dir=${2:-.}

    # Create the target directory if it doesn't exist
    # -p ensures no error if it exists and creates parent paths if needed
    if [ ! -d "$target_dir" ]; then
        echo "Creating target directory: $target_dir"
        mkdir -p "$target_dir"
    fi

    # Navigate to the source's parent directory
    cd "$source_parent_dir" || return 1
    
    # Run compression and output to the target directory
    tar cf - "$file_name" | lz4 -c > "${target_dir}/${file_name}.tar.lz4"
    
    # Return to the original directory
    cd "$current_dir"
}

function compress_zip() {
    if [ $# -ne 1 ]; then
        echo "Usage: compress_zip <directory>"
        return 1
    fi
    current_dir=$(pwd)
    directory=$1
    cd $(dirname $directory)
    file_name=$(basename $directory)
    zip -r ${file_name}.zip ${file_name}
    cd $current_dir
    echo "Compressed ${file_name} to ${file_name}.zip"
    return 0
}

# function decompress_zip() {
#     if [ $# -ne 1 ]; then
#         echo "Usage: decompress_zip <file_path>"
#         return 1
#     fi
#     current_dir=$(pwd)
# }
function compress_all() {
    if [ $# -lt 1 ] || [ $# -gt 2 ]; then
        echo "Usage: compress <data_storage_dir> [target_dir]"
        return 1
    fi
    directory=$1
    target_dir=${2:-$directory}
    for file in $(find $directory -maxdepth 1 -type d); do
        if [[ $file != . ]]; then
            # Check if the file ends with .zarr
            echo "Compressing $file"
            compress $file $target_dir &
        else
            echo "Skipping $file"
        fi
    done
    wait
}


function decompress() {
    if [ $# -lt 1 ] || [ $# -gt 2 ]; then
        echo "Usage: decompress <file_path> [target_dir]"
        return 1
    fi
    current_dir=$(pwd)
    file_path=$1
    file_dir=$(dirname $file_path)
    cpu_cores=$(($(nproc) - 1))
    file_name=$(basename $file_path)
    cd $file_dir
    target_dir=${2:-$file_dir}
    lz4 -d -c ${file_name} | tar xf - -C $target_dir
    cd $current_dir
    echo "Decompressed ${file_name} to ${target_dir}"
    return 0
}

function decompress_all() {
    if [ $# -ne 1 ]; then
        echo "Usage: decompress_all <directory>"
        return 1
    fi
    directory=$1
    # Run the following command in parallel. Only 1 level deep.
    for file in $(find $directory -maxdepth 1 -name "*.tar.lz4" -type f); do
        echo "Decompressing $file"
        decompress $file &
    done
    wait
}

function calc_lines() {
    if [ $# -ne 1 ]; then
        echo "Usage: calc_lines <suffix>"
        return 1
    fi
    suffix=$1
    find . -name "*.${suffix}" -type f | xargs wc -l
}

function count() {
    if [ $# -lt 1 ] || [ $# -gt 2 ]; then
        echo "Usage: count_files <pattern> [directory]"
        return 1
    fi
    local pattern=$1
    local directory=${2:-.}
    find "$directory" -type f -name "*$pattern*" | wc -l
}


function port() {
    lsof -i :$1
}

function port_kill() {
    lsof -i :$1 | tail -n +2 | awk '{print $2}' | xargs kill -9
}

alias cursor_pull="~/ubuntu-config/config_cursor.sh pull"
alias cursor_push="~/ubuntu-config/config_cursor.sh push"

alias ca="conda activate"
# alias f="fzf | sort"
alias ls="ls -lah --color=auto"
alias l="ls -lah --color=auto"

f() {
    process_num=$(($(nproc) - 1)) # max 64
    process_num=$(($process_num > 64 ? 64 : $process_num))
    if [[ -z "$1" ]]; then
        fd -j$process_num . | fzf | sort
    else
        fd -j$process_num --max-depth $1 | fzf | sort
    fi
}
alias gcs="s5cmd --profile gcs --endpoint-url https://storage.googleapis.com --log debug --stat"
alias gcsd="s5cmd --profile gcs --endpoint-url https://storage.googleapis.com --dry-run --log debug --stat"
alias ytdl="yt-dlp --cookies-from-browser chrome --js-runtime node -k"

gif() {
    if [ -z "$1" ]; then
        echo "Error: No input file provided."
        return 1
    fi

    local input="$1"
    # if input is a directory, then convert all videos in the directory to gif
    if [ -d "$input" ]; then
        for file in "$input"/*.mp4; do
            if [ -f "$file" ]; then
                gif "$file"
            fi
        done
        return 0
    fi

    local output="${input%.*}.gif"

    echo "Optimizing $input for a smaller file size..."

    # Optimization 1: Max colors limited to 128 (down from 256)
    # Optimization 2: Use 'stats_mode=diff' to only update moving pixels
    ffmpeg -i "$input" -vf \
    "fps=10,scale=240:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=1" \
    -y "$output"
    # gifsicle -O3 --lossy=30 --colors 128 $output -o $output

    echo "Done! Check $output"
}


function branch() {
    git for-each-ref --sort=committerdate --format='%(committerdate:relative)%09%(refname:short)' refs/heads/ refs/remotes/ | grep "$1" | column -t -s $'\t'
}

tar_copy() {
    local src="${1%/}" # Remove trailing slash
    local dest="$2"

    if [ ! -d "$src" ]; then
        echo "Error: Source $src is not a directory."
        return 1
    fi

    # Extract the folder name (e.g., "debug_jobs")
    local folder_name=$(basename "$src")
    local full_dest="$dest/$folder_name"

    mkdir -p "$full_dest"
    
    echo "Streaming $src to $full_dest..."
    tar -cf - -C "$src" . | tar -xf - -C "$full_dest"
}

hfdl () {
    if [ $# -lt 1 ] || [ $# -gt 2 ]; then
        echo "Usage: hfdl <bucket_path> [local_dest]"
        return 1
    fi

    local bucket_root="hf://buckets/nvidia/camera-cross-embodiment"
    local src="$bucket_root/$1"
    local dir_name=$(basename "$1")

    local dest
    if [ $# -eq 2 ]; then
        dest="${2%/}" # Remove trailing slash
    else
        dest="."
    fi

    # Imitate `cp -r remote dest`. If dest already exists and is non-empty,
    # download into dest/<dirname> so the file levels stay aligned.
    local target="$dest"
    if [ -d "$dest" ] && [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then
        target="$dest/$dir_name"
        echo "Local dest '$dest' already exists and is non-empty -> downloading into '$target'"
    else
        echo "Local dest '$dest' is empty or missing -> downloading into '$target'"
    fi

    echo ""
    echo "=== Already existing entries under $dest ==="
    if [ -d "$dest" ] && [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then
        ls -1 "$dest"
    else
        echo "(none)"
    fi

    echo ""
    echo "=== Expected new entries under $target ==="
    hf buckets ls "$src" -q 2>/dev/null | sed "s|^$1/|$target/|"

    echo ""
    local command="hf buckets sync $src $target"
    echo "running command: $command"
    printf "Proceed? [y/N] "
    local reply
    read reply
    if [ "$reply" = "y" ] || [ "$reply" = "Y" ]; then
        eval $command
    else
        echo "Aborted."
        return 1
    fi
}

hful () {
    if [ $# -ne 2 ]; then
        echo "Usage: hful <file_path> <bucket_path>"
        return 1
    fi

    local src="${1%/}" # Remove trailing slash
    local bucket_root="hf://buckets/nvidia/camera-cross-embodiment"
    local dest="$bucket_root/$2"

    # Single file: plain copy, like `cp file dest`
    if [ -f "$src" ]; then
        local command="hf buckets cp $src $dest"
        echo "running command: $command"
        eval $command
        return $?
    fi

    if [ ! -d "$src" ]; then
        echo "Error: $src is neither a file nor a directory."
        return 1
    fi

    # Directory: imitate `cp -r dir dest`. If dest already exists and is
    # non-empty, copy into dest/<dirname> so the file levels stay aligned.
    local dir_name=$(basename "$src")
    local existing
    existing=$(hf buckets ls "$dest" -q 2>/dev/null)
    local target="$dest"
    if [ -n "$existing" ]; then
        target="$dest/$dir_name"
        echo "Destination '$2' already exists and is non-empty -> syncing into '$2/$dir_name'"
    else
        echo "Destination '$2' is empty or missing -> syncing into '$2'"
    fi

    echo ""
    echo "=== Already existing entries under $dest ==="
    if [ -n "$existing" ]; then
        hf buckets ls "$dest" -h 2>/dev/null
    else
        echo "(none)"
    fi

    echo ""
    echo "=== Expected new entries under $target ==="
    local target_rel="${target#$bucket_root/}"
    (cd "$src" && find . -mindepth 1 -maxdepth 1 | sed "s|^\./|$target_rel/|")

    echo ""
    local command="hf buckets sync $src $target"
    echo "running command: $command"
    printf "Proceed? [y/N] "
    local reply
    read reply
    if [ "$reply" = "y" ] || [ "$reply" = "Y" ]; then
        eval $command
    else
        echo "Aborted."
        return 1
    fi
}

hfrm () {
    if [ $# -ne 1 ]; then
        echo "Usage: hfrm <bucket_path>"
        return 1
    fi

    local bucket_root="hf://buckets/nvidia/camera-cross-embodiment"
    local target="$bucket_root/$1"

    local existing
    existing=$(hf buckets ls "$target" -q 2>/dev/null)
    if [ -z "$existing" ]; then
        echo "Nothing to remove: '$1' is empty or does not exist."
        return 1
    fi

    echo "=== Entries to be removed under $target ==="
    hf buckets ls "$target" -h 2>/dev/null

    echo ""
    local command="hf buckets rm $target -R -y"
    echo "running command: $command"
    printf "Recursively remove everything under '$1'? [y/N] "
    local reply
    read reply
    if [ "$reply" = "y" ] || [ "$reply" = "Y" ]; then
        eval $command
    else
        echo "Aborted."
        return 1
    fi
}