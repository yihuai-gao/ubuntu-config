FROM ubuntu:22.04

RUN apt-get update &&\
    apt-get install git zsh curl git vim net-tools wget htop x11-apps neofetch -y

RUN apt-get install ca-certificates --reinstall -y

ARG USERNAME=test
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN useradd -m ${USERNAME}
# Give ownership of the user's home directory to the new user
RUN chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}

USER ${USERNAME}
ARG HOME=/home/${USERNAME}
WORKDIR ${HOME}

RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

RUN git clone https://github.com/marlonrichert/zsh-autocomplete.git \
    ${ZSH_CUSTOM:-/home/${USERNAME}/.oh-my-zsh/custom}/plugins/zsh-autocomplete && \
    git clone https://github.com/zsh-users/zsh-autosuggestions \
    ${ZSH_CUSTOM:-/home/${USERNAME}/.oh-my-zsh/custom}/plugins/zsh-autosuggestions && \
    git clone https://github.com/zsh-users/zsh-syntax-highlighting.git \
    ${ZSH_CUSTOM:-/home/${USERNAME}/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting && \
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git \
    ${ZSH_CUSTOM:-/home/${USERNAME}/.oh-my-zsh/custom}/themes/powerlevel10k

RUN mv ${HOME}/.zshrc ${HOME}/.zshrc.bak && \
    echo 'export ZSH="$HOME/.oh-my-zsh"\nplugins=(\n  git\n  zsh-autosuggestions\n  zsh-autocomplete\n  zsh-syntax-highlighting\n  themes\n)\n' >> ${HOME}/.zshrc && \
    echo 'ZSH_THEME="eastwood"\nsource $ZSH/oh-my-zsh.sh' >> ${HOME}/.zshrc && \
    echo 'bindkey -M menuselect "\\r" .accept-line' >> ${HOME}/.zshrc && \
    echo 'bindkey -M menuselect -s "^R" "^_^_^R" "^S" "^_^_^S"' >> ${HOME}/.zshrc && \
    echo 'bindkey -M menuselect "\\e[D" .backward-char "\\eOD" .backward-char "\\e[C" .forward-char "\\eOC" .forward-char' >> ${HOME}/.zshrc && \
    echo 'bindkey '^H' backward-kill-word' >> ${HOME}/.zshrc


RUN ARCH=$(uname -m) && SYS=$(uname -s) && \
    wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${SYS}-${ARCH}.sh && \
    bash Miniforge3-${SYS}-${ARCH}.sh -b -p ${HOME}/miniforge3 && \
    rm Miniforge3-${SYS}-${ARCH}.sh && \
    ${HOME}/miniforge3/bin/conda init zsh && \
    ${HOME}/miniforge3/bin/conda init bash && \
    ${HOME}/miniforge3/bin/mamba init zsh && \
    ${HOME}/miniforge3/bin/mamba init bash

SHELL ["/bin/zsh", "-ec"]
CMD ["zsh"]