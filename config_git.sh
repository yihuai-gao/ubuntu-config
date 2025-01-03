
# Global gitignore configuration. Feel free to comment out the following lines if you don't need it.
touch ~/.gitignore_global
echo ".DS_Store
.vscode" >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global

# Prompt whether to install personal names (default is yes)
read -p "Do you want to install user names (Yihuai Gao)? (Y/n): " install_personal_names
if [ "$install_personal_names" = "y" -o "$install_personal_names" = "Y" -o "$install_personal_names" = "" ]; then
    git config --global user.name "Yihuai Gao"
    git config --global user.email "yihuai@stanford.edu"
    echo "User names installed."
fi
