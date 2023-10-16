sudo apt-get update
sudo apt update && sudo apt install zsh --yes
sudo apt install curl git python3-pip python vim net-tools htop

# To fix SSL error that may occur
sudo apt install ca-certificates --reinstall

# ranger is a easy-to-use file manager in terminal, see https://github.com/ranger/ranger
# archey is a system tool to display all system information, see https://github.com/HorlogeSkynet/archey4
pip3 install wheel ranger-fm archey4

# Official script to install oh-my-zsh. The file is pre-downloaded as servers in China may not have access to the online script.
./install_oh_my_zsh.sh
sudo apt-get install python-pip

# TODO: Please change to your own user name and email
git config --global user.name "DavidGao"
git config --global user.email "davidgao1013@gmail.com"

# Global gitignore configuration. Feel free to comment out the following lines if you don't need it.
touch ~/.gitignore_global
echo ".DS_Store
.vscode" >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global

# Install fzf, a command line fuzzy finder, see https://github.com/junegunn/fzf
sudo apt-get install fzf ||{
    git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf
    ~/.fzf/install
}