sudo apt install lua5.3
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
  zsh-autocomplete
  zsh-syntax-highlighting
  themes
)
source $ZSH/oh-my-zsh.sh
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
export PATH=$PATH:~/.fzf/bin
export PATH="$HOME/.local/bin:$PATH"

# zsh-autocomplete settings
bindkey -M menuselect "\r" .accept-line
bindkey -M menuselect -s \
    "^R" "^_^_^R" \
    "^S" "^_^_^S"
bindkey -M menuselect \
    "\\e[D" .backward-char \
    "\\eOD" .backward-char \
    "\\e[C" .forward-char \
    "\\eOC" .forward-char
bindkey '^H' backward-kill-word' >> ~/.zshrc

cp ./p10k.zsh ~/.p10k.zsh

sudo cp 'Sauce Code Pro Nerd Font Complete.ttf' /usr/local/share/fonts
fc-cache -f -v