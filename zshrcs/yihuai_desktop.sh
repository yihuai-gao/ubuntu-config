
export TZ="America/Los_Angeles"

export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="eastwood"

# setopt HIST_IGNORE_DUPS

# To suppress some warning messages
zle -N insert-unambiguous-or-complete 
zle -N menu-search
zle -N recent-paths

plugins=(
  git
  zsh-autocomplete
  zsh-autosuggestions
  zsh-syntax-highlighting
  themes
)
source $ZSH/oh-my-zsh.sh

export PATH="$HOME/.local/usr/bin:$PATH"
# export EDITOR="vim"
# export EDITOR="cursor --wait"
export EDITOR='f() { if [ $# -gt 0 ]; then code --wait "$@"; else code; fi }; f'

# Costomized zsh-autocomplete settings: please refer to https://github.com/marlonrichert/zsh-autocomplete
#   Make Enter submit the command line straight from the menu
bindkey -M menuselect "\r" .accept-line
#   In menuselect mode (triggered by up arrow when typing commands) use left and right arrow keys 
#   to move cursor instead of selecting menu items
bindkey -M menuselect \
    "\e[D" .backward-char \
    "\eOD" .backward-char \
    "\e[C" .forward-char \
    "\eOC" .forward-char \
    "^[[1;5D" .backward-word \
    "^[[1;5C" .forward-word \
    "[H" .beginning-of-line \
    "OH" .beginning-of-line \
    "[F" .end-of-line \
    "OF" .end-of-line

#   Use Ctrl-Backsbace to kill the word before the cursor
bindkey "^H" backward-kill-word
zstyle ":autocomplete:*" delay 0.2  # seconds (float)
zstyle ":autocomplete:*" min-input 3    # characters
zstyle ":autocomplete:history-search-backward:*" list-lines 3000
zstyle ":autocomplete:history-incremental-search-backward:*" list-lines 3000
zstyle -e ':autocomplete:*:*' list-lines 'reply=( $(( LINES / 3 )) )'
zstyle ":completion:*" completions 3000


eval "$(zoxide init zsh)"

source $HOME/ubuntu-config/zsh_functions.sh
# export FZF_DEFAULT_OPTS="--bind=ctrl-left:backward-word,ctrl-right:forward-word --layout=reverse"
export FZF_DEFAULT_OPTS="--bind=ctrl-left:backward-word,ctrl-right:forward-word,ctrl-up:prev-history,ctrl-down:next-history,ctrl-a:select-all+accept --multi --reverse --history=$HOME/.fzf_history"

source <(fzf --zsh)

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/data/yihuai/miniforge3/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/data/yihuai/miniforge3/etc/profile.d/conda.sh" ]; then
        . "/data/yihuai/miniforge3/etc/profile.d/conda.sh"
    else
        export PATH="/data/yihuai/miniforge3/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<


. "$HOME/.local/bin/env"
export PATH="$PATH:/home/yihuai/Applications/ngccli_linux/ngc-cli"

# export HF_TOKEN=??? # Gmail
export HF_TOKEN=??? # NVIDIA
export HF_HOME=/data/yihuai/huggingface

export ENROOT_CONFIG_PATH="$HOME/.config/enroot/"

export WANDB_API_KEY=???
export WANDB_ENTITY=nvidia-dir

alias ccx="claude --dangerously-skip-permissions"


# Skip loading
sl () {
    # Find the line number of "self.checkpointer.load"
    line_number=$(grep -n "self.checkpointer.load" imaginaire/trainer.py | cut -d: -f1)
    if [ -z "$line_number" ]; then
        echo "No line number found for 'self.checkpointer.load' in imaginaire/trainer.py"
        return
    fi
    # Modify this line of imaginaire/trainer.py to 'iteration = 0 # HACK & DEBUG (yihuai) skip model loading for faster debugging'
    cmd="${line_number}s/.*/        iteration = 0 # HACK \& DEBUG (yihuai) skip model loading for faster debugging\n        log.error('HACK \& DEBUG (yihuai) skip model loading for faster debugging')/"
    sed -i "$cmd" imaginaire/trainer.py
}

# Enable loading
el () {
    line_number=$(grep -n "iteration = 0" imaginaire/trainer.py | cut -d: -f1)
    if [ -z "$line_number" ]; then
        echo "No line number found for 'iteration = 0' in imaginaire/trainer.py"
        return
    fi
    # Modify this line of imaginaire/trainer.py to 'iteration = self.checkpointer.load(model, optimizer, scheduler, grad_scaler)'
    cmd="${line_number}s/.*/        iteration = self.checkpointer.load(model, optimizer, scheduler, grad_scaler)/"
    sed -i "$cmd" imaginaire/trainer.py
    # Remove all lines with ''
    # pattern="log.error('HACK & DEBUG (yihuai) skip model loading for faster debugging')"
    sed -i "/HACK & DEBUG (yihuai)/d" imaginaire/trainer.py
}

alias gcs="s5cmd --profile gcs --endpoint-url https://storage.googleapis.com --log debug --stat"

export IMAGINAIRE_OUTPUT_ROOT=/home/yihuai/video-gen/repositories/imaginaire4-output
export IMAGINAIRE_CACHE_DIR=/home/yihuai/video-gen/repositories/imaginaire4-cache
export CREDENTIALS_DIR=/home/yihuai/.ssh/credentials

source ~/ubuntu-config/slurm/zsh_functions.sh

alias s="~/miniforge3/bin/python ~/video-gen/repositories/imaginaire4-cam-uva-0628/projects/cosmos3/cam_uva/scripts/train/check_job.py"

submit () {
    /data/yihuai/miniforge3/bin/python ~/video-gen/repositories/imaginaire4-cam-uva-0628/projects/cosmos3/cam_uva/scripts/train/submit_job_$1.py "${@:2}"
}


alias ls_remote="/data/yihuai/miniforge3/bin/python /home/yihuai/video-gen/repositories/imaginaire4-cam-uva-0628/projects/cosmos3/cam_uva/scripts/checkpoint/check_remote_storage.py -i"
alias sync_file="/data/yihuai/miniforge3/bin/python /home/yihuai/video-gen/repositories/imaginaire4-cam-uva-0628/projects/cosmos3/cam_uva/scripts/dataset/sync_file.py"

# Inside an enroot container (unprivileged user namespace: /proc owned by nobody),
# use a minimal git-branch prompt; on the host keep the oh-my-zsh theme prompt.
if [[ "$(stat -c %U /proc 2> /dev/null)" == "nobody" ]]; then
    setopt PROMPT_SUBST
    parse_git_branch() {
        local branch=$(git branch --show-current 2> /dev/null)
        if [[ -n $branch ]]; then
            echo "%F{green}$branch%f"
        fi
    }
    export PROMPT='$(parse_git_branch) %F{cyan}%~ %F{reset}%# '
fi