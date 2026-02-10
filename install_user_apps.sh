#!/bin/bash

file_dir=$(dirname $(realpath $0))

mkdir -p $HOME/.local

mkdir -p $file_dir/downloads
cd $file_dir/downloads

# apt download fzf
$arch=$(uname -m)
mkdir -p $HOME/.local/usr/bin

if [ $arch == "x86_64" ]; then
    wget https://dev.yorhel.nl/download/ncdu-2.8.1-linux-x86_64.tar.gz
    tar -xzf ncdu-2.8.1-linux-x86_64.tar.gz -C $HOME/.local/usr/bin

    wget https://github.com/junegunn/fzf/releases/download/v0.67.0/fzf-0.67.0-linux_amd64.tar.gz
    tar -xzf fzf-0.67.0-linux_amd64.tar.gz -C $HOME/.local/usr/bin

    wget https://github.com/sxyazi/yazi/releases/download/v26.1.4/yazi-x86_64-unknown-linux-gnu.deb
    dpkg-deb -x yazi-x86_64-unknown-linux-gnu.deb $HOME/.local

    # Install fish
    wget https://github.com/fish-shell/fish-shell/releases/download/4.4.0/fish-4.4.0-linux-x86_64.tar.xz
    tar -xf fish-4.4.0-linux-x86_64.tar.xz -C $HOME/.local/usr/bin


elif [ $arch == "aarch64" ]; then

    # Install fish
    wget https://github.com/fish-shell/fish-shell/releases/download/4.4.0/fish-4.4.0-linux-aarch64.tar.xz
    tar -xf fish-4.4.0-linux-aarch64.tar.xz -C $HOME/.local/usr/bin


    wget https://dev.yorhel.nl/download/ncdu-2.8.1-linux-aarch64.tar.gz
    tar -xzf ncdu-2.8.1-linux-aarch64.tar.gz -C $HOME/.local/usr/bin

    wget https://github.com/junegunn/fzf/releases/download/v0.67.0/fzf-0.67.0-linux_arm64.tar.gz
    tar -xzf fzf-0.67.0-linux_arm64.tar.gz -C $HOME/.local/usr/bin

    wget https://github.com/sxyazi/yazi/releases/download/v26.1.4/yazi-aarch64-unknown-linux-gnu.deb
    dpkg-deb -x yazi-aarch64-unknown-linux-gnu.deb $HOME/.local

fi

apt download zoxide
apt download neofetch
apt download x11-apps
apt download htop

dpkg-deb -x zoxide* $HOME/.local
dpkg-deb -x neofetch* $HOME/.local
dpkg-deb -x x11-apps* $HOME/.local
cd $file_dir


# $HOME/miniforge3/bin/mamba install -y yazi
# $HOME/miniforge3/bin/mamba install -y nvitop

# ln -s $CONDA_PREFIX/bin/nvitop $HOME/.local/usr/bin/nvitop
