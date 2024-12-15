# Install font. 
# You can update the GNOME terminal font in Preference -> Profiles (usually Unnamed) -> Costom font
# If you are using VSCode remote-ssh to connect to your linux server, you can search "terminal font" in vscode preferences
# and set it to "SauceCodePro Nerd Font"
sudo cp 'Sauce Code Pro Nerd Font Complete.ttf' /usr/local/share/fonts
fc-cache -f -v