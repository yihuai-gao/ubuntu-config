#!/bin/bash

# Configure Fish shell with equivalent zsh functionality
# This script sets up Fish shell to match the current zsh configuration

set -e

# Install fisher (Fish plugin manager) if not already installed
fish -c "if not type -q fisher
    curl -sL https://raw.githubusercontent.com/jorgebucaran/fisher/main/functions/fisher.fish | source
    fisher install jorgebucaran/fisher
end"

# Install Fish plugins (equivalents to zsh plugins)
fish -c "
# Syntax highlighting (like zsh-syntax-highlighting)
fisher install jorgebucaran/autopair.fish

# z/zoxide integration (already handled by zoxide init)
# fisher install jethrokuan/z  # Alternative to zoxide

# git plugin functionality
fisher install jorgebucaran/fish-git

# fzf integration
fisher install PatrickF1/fzf.fish

fisher install rafaelrinaldi/pure

fisher install jorgebucaran/fish-getopts
"

# Create Fish config directory if it doesn't exist
mkdir -p ~/.config/fish
mkdir -p ~/.config/fish/functions

# Backup existing config if present
if [ -f ~/.config/fish/config.fish ]; then
    mv ~/.config/fish/config.fish ~/.config/fish/config.fish.bak
fi

# Create the main Fish configuration file
cat > ~/.config/fish/config.fish << 'EOF'
# Fish shell configuration - equivalent to zsh config

# PATH configuration
set -x PATH $PATH $HOME/.local/bin
set -x PATH $HOME/.local/usr/bin $PATH

# Timezone
set -x TZ "America/Los_Angeles"

# Editor
set -x EDITOR "vim"

# Disable welcome message
set fish_greeting

# Initialize zoxide (like zsh)
if type -q zoxide
    zoxide init fish | source
end

# FZF configuration (equivalent to zsh FZF_DEFAULT_OPTS)
set -x FZF_DEFAULT_OPTS "--bind=ctrl-left:backward-word,ctrl-right:forward-word,ctrl-up:prev-history,ctrl-down:next-history,ctrl-a:select-all+accept --multi --reverse --history=$HOME/.fzf_history"

# Source fzf key bindings if available
if type -q fzf
    fzf --fish | source
end

# Load custom functions and aliases
source $HOME/ubuntu-config/fish_functions.fish

# Custom key bindings (Fish equivalents to zsh bindings)
# Ctrl-Backspace to delete word backward
bind \b backward-kill-word
bind \e\[3\;5~ kill-word  # Ctrl-Delete

# Ctrl-Left/Right for word navigation (usually works by default in Fish)
bind \e\[1\;5D backward-word
bind \e\[1\;5C forward-word

# Enable vi mode if preferred (comment out if not needed)
# fish_vi_key_bindings

# Color scheme configuration
set -g fish_color_command green
set -g fish_color_error red
set -g fish_color_param cyan
set -g fish_color_comment brblack
set -g fish_color_quote yellow

## For SLURM systems (uncomment if needed)
# source /etc/profile.d/modules.sh
# module load slurm

EOF

# Copy functions file to Fish config
cp $HOME/ubuntu-config/fish_functions.fish ~/.config/fish/functions.fish 2>/dev/null || true

# echo "Fish shell configuration complete!"
# echo "To start using Fish, run: fish"
# echo "To set Fish as default shell, run: chsh -s $(which fish)"
# echo ""
# echo "Note: Fish has built-in autosuggestions and syntax highlighting."
# echo "Use the up arrow to search history (like zsh-autocomplete)."




# If there is $HOME/.zsh_history, convert it to $HOME/.fish_history
if [ -f $HOME/.zsh_history ]; then
    pip install zsh-history-to-fish
    zsh-history-to-fish
fi