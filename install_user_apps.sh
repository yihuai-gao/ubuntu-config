#!/bin/bash

file_dir=$(dirname $(realpath $0))

mkdir -p $HOME/.local

mkdir -p $file_dir/downloads
cd $file_dir/downloads

apt download fzf zoxide ncdu neofetch
dpkg-deb -x fzf* $HOME/.local
dpkg-deb -x zoxide* $HOME/.local
dpkg-deb -x ncdu* $HOME/.local
dpkg-deb -x neofetch* $HOME/.local
cd $file_dir


$HOME/miniforge3/bin/mamba install -y yazi
ln -s $HOME/miniforge3/bin/yazi $HOME/.local/usr/bin/yazi

