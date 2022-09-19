# ssh-keygen -t ed25519
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIK7guJTbrJLZuyeJ7oNDVGmE+NU92J/Uu2I9uNj96Lz davidgao1013@gmail.com" >> ~/.ssh/authorized_keys
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config

sudo apt update && apt install zsh --yes
pip3 install ranger-fm archey4
sudo apt-get update
sudo apt-get install fzf
sh -c "$(wget -O- https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
