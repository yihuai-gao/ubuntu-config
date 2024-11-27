#!/bin/sh

# Install plugins for oh-my-zsh
git clone https://github.com/marlonrichert/zsh-autocomplete.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autocomplete
git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions 
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/themes/powerlevel10k


# If you do not have https access to github (typically on servers in China), please use the following ssh cloning instead.
# Please upload your ssh key to github first. Use `ssh git@github.com` to check ssh connectivity.
# Or you can setup your https proxy in through `git config` and continue to use https cloning.

# git clone git@github.com:marlonrichert/zsh-autocomplete.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autocomplete
# git clone git@github.com:zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions 
# git clone git@github.com:zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
# git clone git@github.com:skywind3000/z.lua.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/z.lua
# git clone --depth=1 git@github.com:romkatv/powerlevel10k.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/themes/powerlevel10k

# Alternative (requries Nerd Fonts) ZSH_THEME="powerlevel10k/powerlevel10k"

# Create a backup of zshrc. If you have modified it, please remember to copy the modified content to the new zshrc.
mv ~/.zshrc ~/.zshrc_bak
touch ~/.zshrc
echo '
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="eastwood"
plugins=(
  git
  zsh-autosuggestions
  zsh-autocomplete
  zsh-syntax-highlighting
  themes
)
source $ZSH/oh-my-zsh.sh
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
export PATH=$PATH:~/.fzf/bin
export PATH="$HOME/.local/bin:$PATH"

# Costomized zsh-autocomplete settings: please refer to https://github.com/marlonrichert/zsh-autocomplete
#   Make Enter submit the command line straight from the menu
bindkey -M menuselect "\\r" .accept-line
#   In menuselect mode (triggered by up arrow when typing commands) use left and right arrow keys 
#   to move cursor instead of selecting menu items
bindkey -M menuselect \
    "\\e[D" .backward-char \
    "\\eOD" .backward-char \
    "\\e[C" .forward-char \
    "\\eOC" .forward-char \
    "^[[1;5D" .backward-word \
    "^[[1;5C" .forward-word

#   Use Ctrl-Backsbace to kill the word before the cursor
bindkey "^H" backward-kill-word
zstyle ":autocomplete:*" delay 0.2  # seconds (float)
zstyle ":autocomplete:*" min-input 3    # characters
zstyle ":autocomplete:history-search-backward:*" list-lines 100
zstyle ":autocomplete:history-incremental-search-backward:*" list-lines 100
' >> ~/.zshrc

# Copy the configuration file for powerlevel10k. Please remove it if you would like to configure it by yourself.
cp ./p10k.zsh ~/.p10k.zsh

