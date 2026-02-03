#!/bin/bash

# Install fish
cd $HOME/ubuntu-config/downloads
wget https://github.com/fish-shell/fish-shell/releases/download/4.4.0/fish-4.4.0-linux-aarch64.tar.xz

tar -xf fish-4.4.0-linux-aarch64.tar.xz -C ~/.local/usr/bin
