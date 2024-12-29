# Install font. 
# You can update the GNOME terminal font in Preference -> Profiles (usually Unnamed) -> Costom font
# If you are using VSCode remote-ssh to connect to your linux server, you can search "terminal font" in vscode preferences
# and set it to "SauceCodePro Nerd Font"
mkdir -p $HOME/.local/share/fonts
cp -r SourceCodePro $HOME/.local/share/fonts
fc-cache -f -v