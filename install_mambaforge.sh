wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
rm Miniforge3-Linux-x86_64.sh
~/miniforge/bin/conda init zsh
~/miniforge/bin/conda init bash