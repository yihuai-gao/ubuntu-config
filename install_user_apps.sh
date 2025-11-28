#!/bin/bash

file_dir=$(dirname $(realpath $0))

mkdir -p $HOME/.local

mkdir -p $file_dir/downloads
cd $file_dir/downloads

# apt download fzf
apt download zoxide
apt download neofetch
apt download x11-apps
wget https://dev.yorhel.nl/download/ncdu-2.8.1-linux-x86_64.tar.gz
wget https://github.com/junegunn/fzf/releases/download/v0.67.0/fzf-0.67.0-linux_amd64.tar.gz

mkdir -p $HOME/.local/usr/bin
tar -xzf ncdu-2.8.1-linux-x86_64.tar.gz -C $HOME/.local/usr/bin
tar -xzf fzf-0.67.0-linux_amd64.tar.gz -C $HOME/.local/usr/bin

dpkg-deb -x zoxide* $HOME/.local
dpkg-deb -x neofetch* $HOME/.local
dpkg-deb -x x11-apps* $HOME/.local
cd $file_dir


$HOME/miniforge3/bin/mamba install -y yazi
$HOME/miniforge3/bin/mamba install -y nvitop

ln -s $CONDA_PREFIX/bin/nvitop $HOME/.local/usr/bin/nvitop
