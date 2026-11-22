#! /bin/bash
action=$1

# get this file directory even if not cd'd to this directory
file_dir=$(dirname $(realpath $0))

mpv_user_dir=${HOME}/.config/mpv

if [ "$action" = "pull" ]; then
    # get the current mpv config
    cp $mpv_user_dir/mpv.conf $file_dir/configs/mpv/mpv.conf
fi

if [ "$action" = "push" ] || [ -z "$action" ]; then
    # set the mpv config (back up existing file first)
    mkdir -p $mpv_user_dir
    [ -f $mpv_user_dir/mpv.conf ] && cp $mpv_user_dir/mpv.conf $mpv_user_dir/mpv.conf.bak
    cp $file_dir/configs/mpv/mpv.conf $mpv_user_dir/mpv.conf
fi
