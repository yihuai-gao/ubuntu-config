#!/bin/sh

# Execute this file after all the other configuration steps.
# Use mamba (which is the default version in miniforge3) as a replacement for conda.
# If you want to use mamba, please uninstall your conda environment first.
# `mamba install/create` is much faster than `conda install/create`

arch=$(uname -m)
system=$(uname -s)
# Convert from Darwin to MaxOSX
if [ "$system" = "Darwin" ]; then
    system="MacOSX"
fi

wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(system)-$(arch).sh

bash Miniforge3-$(system)-$(arch).sh -b -p ~/miniforge3
rm Miniforge3-$(system)-$(arch).sh
~/miniforge3/bin/conda init zsh
~/miniforge3/bin/conda init bash
~/miniforge3/bin/mamba init zsh
~/miniforge3/bin/mamba init bash