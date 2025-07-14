#!/bin/bash

file_dir=$(dirname $(realpath $0))

mkdir -p $HOME/.local

mkdir -p $file_dir/downloads
cd $file_dir/downloads

apt download fzf
apt download zoxide
apt download neofetch
apt download sysstat
apt download fio
apt download x11-apps
wget https://dev.yorhel.nl/download/ncdu-2.8.1-linux-x86_64.tar.gz
tar -xzf ncdu-2.8.1-linux-x86_64.tar.gz -C $HOME/.local/usr/bin

dpkg-deb -x fzf* $HOME/.local
dpkg-deb -x zoxide* $HOME/.local
dpkg-deb -x neofetch* $HOME/.local
dpkg-deb -x sysstat* $HOME/.local
dpkg-deb -x fio* $HOME/.local
dpkg-deb -x x11-apps* $HOME/.local
cd $file_dir


$HOME/miniforge3/bin/mamba install -y yazi
$HOME/miniforge3/bin/mamba install -y nvitop

mkdir -p $HOME/.local/usr/bin
ln -s $HOME/miniforge3/bin/yazi $HOME/.local/usr/bin/yazi
ln -s $HOME/miniforge3/bin/nvitop $HOME/.local/usr/bin/nvitop
