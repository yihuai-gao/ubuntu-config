wget https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh
bash Mambaforge-Linux-x86_64.sh -b -p ~/mambaforge
rm Mambaforge-Linux-x86_64.sh
~/mambaforge/bin/conda init zsh
~/mambaforge/bin/conda init bash