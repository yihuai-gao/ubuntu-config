# One-shot configuration for Ubuntu systems

## Usage
```
./setup_ubuntu.sh
./config_oh_my_zsh.sh
./install_mamba.sh
```
Then go to terminal -> preference -> Profiles (usually the `Unnamed`) -> Custom Font -> Search `SauceCodePro Nerd Font`.

Finally restart the terminal.

Mamba is an alternative to conda with much faster create/install speed. (Use `mamba create/install` instead of `conda create/install`; the other usages are the same.)

## Docker test

To try out the environment, please use `docker build -t zsh-test .` and then `docker run -it zsh-test`. 

If you have not installed nerd fonts, the icons may not display correctly. Please install `Sauce Code Pro Nerd Font` with the ttf file in the repository and set your terminal font either in GNOME (preference -> Profiles, usually the `Unnamed` profile -> Custom Font) or VSCode (search `Terminal Fonts` in settings) to `SauceCodePro Nerd Font`.
