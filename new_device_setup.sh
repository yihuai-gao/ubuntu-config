ssh-keygen -t ed25519
touch ~/.ssh/authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIK7guJTbrJLZuyeJ7oNDVGmE+NU92J/Uu2I9uNj96Lz 1522948489@qq.com" >> ~/.ssh/authorized_keys
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config

apt update && apt install zsh --yes

sh -c "$(wget -O- https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
apt install lua5.3
git clone https://github.com/marlonrichert/zsh-autocomplete.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autocomplete
git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions 
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
git clone https://github.com/skywind3000/z.lua.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/z.lua
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/themes/powerlevel10k

mv ~/.zshrc ~/.zshrc_bak
touch ~/.zshrc
echo '
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="powerlevel10k/powerlevel10k"
plugins=(
  git
  zsh-autosuggestions
#   zsh-autocomplete
  zsh-syntax-highlighting
  themes
)
source $ZSH/oh-my-zsh.sh' >> ~/.zshrc

source ~/.zshrc

