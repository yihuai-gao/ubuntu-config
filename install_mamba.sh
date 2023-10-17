#!/bin/sh

# Execute this file after all the other configuration steps.
# Use mamba (which is the default version in miniforge3) as a replacement for conda.
# If you want to use mamba, please uninstall your conda environment first.
# `mamba install/create` is much faster than `conda install/create`
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
rm Miniforge3-Linux-x86_64.sh
~/miniforge3/bin/conda init zsh
~/miniforge3/bin/conda init bash
~/miniforge3/bin/mamba init zsh
~/miniforge3/bin/mamba init bash