# ssh-keygen -t ed25519
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIK7guJTbrJLZuyeJ7oNDVGmE+NU92J/Uu2I9uNj96Lz davidgao1013@gmail.com" >> ~/.ssh/authorized_keys
# echo "PermitRootLogin yes" >> /etc/ssh/sshd_config

sudo apt-get update
sudo apt update && sudo apt install zsh --yes
sudo apt install curl git python3-pip python vim net-tools
sudo apt install ca-certificates --reinstall
pip3 install wheel ranger-fm archey4
sudo apt-get install fzf ||{
    git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf
    ~/.fzf/install
}
sh -c "$(wget -O- https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
sudo apt-get install python-pip
git config --global user.name "DavidGao"
git config --global user.email "davidgao1013@gmail.com"
touch ~/.gitignore_global
echo ".DS_Store
.vscode" >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global