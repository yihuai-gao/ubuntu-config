#!/bin/sh

# Execute this file after all the other configuration steps.
# Use mamba (which is the default version in miniforge3) as a replacement for conda.
# If you want to use mamba, please uninstall your conda environment first.
# `mamba install/create` is much faster than `conda install/create`

arch=$(uname -m)
sys=$(uname -s)

wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$sys-$arch.sh

bash Miniforge3-$sys-$arch.sh -b -p ~/miniforge3
rm Miniforge3-$sys-$arch.sh
$HOME/miniforge3/bin/conda init zsh
$HOME/miniforge3/bin/conda init bash
$HOME/miniforge3/bin/mamba init zsh
$HOME/miniforge3/bin/mamba init bash

$HOME/miniforge3/bin/mamba install -y yazi zoxide fzf ncdu