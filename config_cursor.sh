action=$1

# get this file directory even if not cd'd to this directory
file_dir=$(dirname $(realpath $0))

if [ "$action" = "pull" ]; then

    # get the current cursor config
    cp ~/.config/Cursor/User/keybindings.json $file_dir/configs/cursor/keybindings.json
    cp ~/.config/Cursor/User/settings.json $file_dir/configs/cursor/settings.json
fi

if [ "$action" = "push" ]; then
    # set the cursor config
    cp $file_dir/configs/cursor/keybindings.json ~/.config/Cursor/User/keybindings.json
    cp $file_dir/configs/cursor/settings.json ~/.config/Cursor/User/settings.json
fi