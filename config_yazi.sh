action=$1

# get this file directory even if not cd'd to this directory
file_dir=$(dirname $(realpath $0))

if [ "$action" = "pull" ]; then

    # get the current yazi config
    cp ~/.config/yazi/keymap.toml $file_dir/configs/yazi/keymap.toml
fi

if [ "$action" = "push" ]; then
    # set the yazi config
    mkdir -p ~/.config/yazi
    cp $file_dir/configs/yazi/keymap.toml ~/.config/yazi/keymap.toml
fi
