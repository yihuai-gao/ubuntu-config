FROM ubuntu:22.04

RUN apt-get update &&\
    apt-get install git sudo -y
    
ARG USERNAME=test
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd -g ${USER_GID} ${USERNAME} && \
    useradd ${USERNAME}  -u ${USER_UID} -g ${USER_GID} -m -p "$(openssl passwd -1 real)"
RUN usermod -aG sudo ${USERNAME}
# Give ownership of the user's home directory to the new user
RUN chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}

WORKDIR /home/${USERNAME}


USER ${USERNAME}
RUN git clone https://github.com/yihuai-gao/ubuntu-config.git

USER root
RUN cd ubuntu-config && \
    ./install_system_apps.sh

USER ${USERNAME}
RUN cd ubuntu-config && \
    ./install_oh_my_zsh.sh && \
    ./config_zsh.sh && \
    ./install_conda.sh

SHELL ["/bin/zsh", "-ec"]
CMD ["zsh"]