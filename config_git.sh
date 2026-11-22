# Global gitignore configuration. Feel free to comment out the following lines if you don't need it.
touch ~/.gitignore_global
echo ".DS_Store
.vscode" >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global

# Git identity: taken from GIT_NAME / GIT_EMAIL, else asked for; left unchanged when empty.
if [ -z "$GIT_NAME" ]; then
    read -p "git user.name (empty to skip): " GIT_NAME
fi
if [ -z "$GIT_EMAIL" ]; then
    read -p "git user.email (empty to skip): " GIT_EMAIL
fi
if [ -n "$GIT_NAME" ]; then
    git config --global user.name "$GIT_NAME"
fi
if [ -n "$GIT_EMAIL" ]; then
    git config --global user.email "$GIT_EMAIL"
fi
