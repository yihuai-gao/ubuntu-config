#!/bin/sh

# Specify whether the script is running as root
if [ "$(id -u)" -ne 0 ]; then
  CMD_PREFIX="sudo"
else
  CMD_PREFIX=""
fi


$CMD_PREFIX apt-get update
$CMD_PREFIX apt-get install zsh fontconfig curl git vim net-tools wget htop -y

# To fix SSL error that may occur
$CMD_PREFIX apt-get install ca-certificates --reinstall -y

# Official script to install oh-my-zsh. The file is pre-downloaded as servers in China may not have access to the online script.
./install_oh_my_zsh.sh

# Global gitignore configuration. Feel free to comment out the following lines if you don't need it.
touch ~/.gitignore_global
echo ".DS_Store
.vscode" >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global

# Install fzf, a command line fuzzy finder, see https://github.com/junegunn/fzf
$CMD_PREFIX apt-get install fzf -y ||{
    git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf
    ~/.fzf/install
}


