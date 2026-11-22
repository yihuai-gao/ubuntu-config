#!/bin/bash

# Build ncurses and zsh from source into ~/.local (no sudo needed).

set -e
install_dir=${HOME}/.local
mkdir -p ${install_dir}

file_dir=$(dirname $(realpath $0))

mkdir -p $file_dir/downloads
cd $file_dir/downloads


# OPTIONAL: zsh will not install without ncurses. IF your machine doesn't have ncurses, you need to install it first.
export CXXFLAGS=" -fPIC" CFLAGS=" -fPIC" CPPFLAGS="-I${install_dir}/include" LDFLAGS="-L${install_dir}/lib"
wget https://ftp.gnu.org/pub/gnu/ncurses/ncurses-6.2.tar.gz
tar -xzvf ncurses-6.2.tar.gz
cd ncurses-6.2
./configure --prefix=${install_dir} --enable-shared
make -j
make install
cd .. && rm ncurses-6.2.tar.gz && rm -r ncurses-6.2

# install zsh itself
wget -O zsh.tar.xz https://sourceforge.net/projects/zsh/files/latest/download
mkdir zsh && unxz zsh.tar.xz && tar -xvf zsh.tar -C zsh --strip-components 1
cd zsh
./configure --prefix=${install_dir}
make -j
make install
cd .. && rm zsh.tar && rm -r zsh

echo "zsh installed to ${install_dir}/bin/zsh. Add ${install_dir}/bin to PATH (e.g. in ~/.bashrc),"
echo "then run ./install_oh_my_zsh.sh and ./config_zsh.sh."
