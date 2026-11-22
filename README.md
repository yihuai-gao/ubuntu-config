# ubuntu-config

Shell, editor and tool configuration for Ubuntu machines, installable without sudo where possible.

```sh
git clone https://github.com/yihuai-gao/ubuntu-config.git ~/ubuntu-config
cd ~/ubuntu-config
./setup_all.sh   # oh-my-zsh + plugins, ~/.zshrc, conda, user apps, git config
```

`config_zsh.sh` writes `~/.zshrc` to source `~/ubuntu-config/zsh_functions.sh`, so keep the clone at `~/ubuntu-config`.
`config_git.sh` reads `GIT_NAME` / `GIT_EMAIL` from the environment, or asks.

## Scripts

| Script | What it does |
|---|---|
| `install_oh_my_zsh.sh` | oh-my-zsh with `zsh-autocomplete`, `zsh-autosuggestions`, `zsh-syntax-highlighting` (no sudo) |
| `install_zsh.sh` | builds ncurses and zsh from source into `~/.local` (no sudo) |
| `config_zsh.sh` | writes `~/.zshrc` (a backup goes to `~/.zshrc_bak`) |
| `install_fish.sh`, `config_fish.sh` | fish with the same functions (`fish_functions.fish`) |
| `install_conda.sh` | Miniforge |
| `install_user_apps.sh` | `fzf`, `ncdu`, `yazi`, `zoxide` and others into `~/.local` |
| `install_system_apps.sh` | apt packages (sudo) |
| `install_fonts.sh` | SauceCodePro Nerd Font from `SourceCodePro/` |
| `install_claude.sh` | Claude Code CLI |
| `config_git.sh`, `config_mpv.sh`, `config_yazi.sh`, `config_sogoupinyin.sh` | configs from `configs/` |
| `config_vscode.sh`, `config_cursor.sh`, `config_*_server.sh` | VS Code / Cursor settings, keybindings, extensions |
| `fetch_slurm_gpu.py` | free GPUs per node on a Slurm cluster |
| `traffic_monitor/`, `hdd_io_monitor/` | per-process network and disk I/O monitors (see their READMEs) |
| `docker/` | Dockerfiles that test the setup in a clean Ubuntu image |

## Fonts

Themes with icons need a Nerd Font. Run `./install_fonts.sh` (or open the ttf in `SourceCodePro/`), then set the
terminal font to `SauceCodePro Nerd Font`. Over remote SSH, install the font on the **local** machine.
