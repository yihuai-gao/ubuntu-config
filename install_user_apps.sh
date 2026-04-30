#!/bin/bash

file_dir=$(dirname $(realpath $0))

mkdir -p $HOME/.local

mkdir -p $file_dir/downloads
cd $file_dir/downloads

# apt download fzf
arch=$(uname -m)
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

    wget https://github.com/sharkdp/fd/releases/download/v10.4.2/fd-musl_10.4.2_amd64.deb
    dpkg-deb -x fd-musl_10.4.2_amd64.deb $HOME/.local


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

    wget https://github.com/sharkdp/fd/releases/download/v10.4.2/fd-musl_10.4.2_arm64.deb
    dpkg-deb -x fd-musl_10.4.2_arm64.deb $HOME/.local

fi

apt download zoxide
apt download neofetch
apt download x11-apps
apt download htop
apt download gifsicle

dpkg-deb -x zoxide* $HOME/.local
dpkg-deb -x neofetch* $HOME/.local
dpkg-deb -x x11-apps* $HOME/.local
dpkg-deb -x gifsicle* $HOME/.local
cd $file_dir


ln -s $CONDA_PREFIX/bin/nvitop $HOME/.local/usr/bin/nvitop

# wget https://github.com/peak/s5cmd/releases/download/v2.3.0/s5cmd_2.3.0_linux_amd64.deb
# dpkg-deb -x s5cmd_2.3.0_linux_amd64.deb $HOME/.local
