FROM ubuntu:22.04

RUN apt-get update \
    && apt-get install git -y


RUN git clone https://github.com/paladin1013/ubuntu-configs.git

RUN cd ubuntu-configs \
    && ./setup_ubuntu.sh \
    && ./config_oh_my_zsh.sh \
    && ./install_mamba.sh

SHELL ["/bin/zsh", "-ec"]
CMD ["zsh"]