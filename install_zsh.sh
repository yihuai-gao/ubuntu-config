#!/bin/bash

# For Marlowe server

set -e
# export HOME="/scratch/m000073/$USER" 
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

# OPTIONAL: install oh-my-zsh
# export PATH=$PATH:/scratch/m000073/$USER/.local/bin
# echo "export PATH=$PATH:/scratch/m000073/$USER/.local/bin" >> /home/$USER/.bashrc
# export PATH=$PATH:${install_dir}/bin
# sh -c "$(wget https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"

# TODO: copy the following lines in $HOME/.zshrc, where $HOME should be /scratch/m000073/$USER
# export HOME="/scratch/m000073/$USER" 
# export FPATH="$HOME/.local/share/zsh/5.9/functions:$FPATH"
# export PATH=$PATH:/scratch/m000073/$USER/.local/bin