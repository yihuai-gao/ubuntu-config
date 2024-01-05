FROM ubuntu:22.04

RUN apt-get update &&\
    apt-get install git -y

ARG USERNAME=test
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN useradd -m ${USERNAME}
# Give ownership of the user's home directory to the new user
RUN chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}
WORKDIR /home/${USERNAME}


USER ${USERNAME}
RUN git clone https://github.com/paladin1013/ubuntu-config.git && \
    cd ubuntu-config && \
    git checkout d6270f472f4b788a46d6d6c123fbdff80dfb1599

USER root
RUN cd ubuntu-config && \
    ./setup_ubuntu.sh

USER ${USERNAME}
RUN cd ubuntu-config && \
    ./config_oh_my_zsh.sh && \
    ./install_conda.sh

SHELL ["/bin/zsh", "-ec"]
CMD ["zsh"]