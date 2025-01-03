
# Global gitignore configuration. Feel free to comment out the following lines if you don't need it.
touch ~/.gitignore_global
echo ".DS_Store
.vscode" >> ~/.gitignore_global
git config --global core.excludesfile ~/.gitignore_global

git config --global user.name "Yihuai Gao"
git config --global user.email "yihuai@stanford.edu"