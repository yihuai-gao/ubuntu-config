# One-shot configuration for Ubuntu systems

## Usage


### Install oh-my-zsh with basic plugins (without sudo)
```sh
./install_oh_my_zsh.sh
```

Plugins include `zsh-autocomplete`, `zsh-autosuggestions`, `zsh-syntax-highlighting` (theme).

`zsh` will source `~/.zshrc` every time it starts. If you are using `bash` and would like to switch to `zsh`, 
please migrate your environment variables from `~/.bashrc` or `~/.bash_profile` to `~/.zshrc`. It is also recommended to copy `~/.bash_history` to `~/.zsh_history` so that the history commands can be autocompleted.

Use `source ~/.zshrc` to apply the changes, or you can also open a new `zsh` terminal.


### Install conda for python virtual environments

```sh
./install_conda.sh
```

### Install User Apps

```sh
./install_user_apps.sh
```

Helpful apps:
- `fzf`: fuzzy finder; `ctrl-R` to search for history commands
- `ncdu`: multi-thread disk space scanning
- `yazi`: terminal file navigation

### Update zsh configuration

```sh
./config_zsh.sh
~/miniforge3/bin/conda init zsh
```

### Install Nerd Fonts
If you have not installed nerd fonts, the icons may not display correctly. You can either use another theme without icons (e.g. `ZSH_THEME="simple"` in `~/.zshrc`) or install `SauceCodePro Nerd Font` with the ttf file provided in the repository. 

To install Nerd Fonts, double click the ttf file and follow the system instructions. After installation, set your terminal font either in GNOME (preference -> Profiles, usually the `Unnamed` profile -> Custom Font) or VSCode (search `Terminal Fonts` in settings) to `SauceCodePro Nerd Font`.

If you are using remote ssh to connect to a server and set up a zsh environment there, you should install the font in the **local machine** instead of the server! 

### Set up an ubuntu server from scratch (with sudo)

```sh
./setup_ubuntu.sh # this includes install_oh_my_zsh.sh and font installation
./config_zsh.sh
```
This will install some necessary or useful packages for a brand-new ubuntu server/pc.




