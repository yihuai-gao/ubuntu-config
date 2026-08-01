#! /bin/bash
action=$1

# get this file directory even if not cd'd to this directory
file_dir=$(dirname $(realpath $0))

vscode_user_dir=${HOME}/.config/Code/User

if [ "$action" = "pull" ]; then
    # get the current vscode config
    cp $vscode_user_dir/keybindings.json $file_dir/configs/vscode/keybindings.json
    cp $vscode_user_dir/settings.json $file_dir/configs/vscode/settings.json
fi

if [ "$action" = "push" ]; then
    # set the vscode config (back up existing files first)
    mkdir -p $vscode_user_dir
    for f in keybindings.json settings.json; do
        [ -f $vscode_user_dir/$f ] && cp $vscode_user_dir/$f $vscode_user_dir/$f.bak
    done
    cp $file_dir/configs/vscode/keybindings.json $vscode_user_dir/keybindings.json
    cp $file_dir/configs/vscode/settings.json $vscode_user_dir/settings.json
fi

if [ "$action" = "extensions" ]; then
    # install all extensions
    while read -r ext; do
        code --install-extension "$ext"
    done < $file_dir/configs/vscode/extensions.txt
fi
