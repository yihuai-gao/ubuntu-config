#!/bin/bash

# Install fish
cd $HOME/ubuntu-config/downloads


arch=$(uname -m)
wget https://github.com/fish-shell/fish-shell/releases/download/4.4.0/fish-4.4.0-linux-$arch.tar.xz
tar -xf fish-4.4.0-linux-$arch.tar.xz -C $HOME/.local/usr/bin
