#! /bin/bash
file_dir=$(dirname $(realpath $0))
mkdir -p ${HOME}/.vscode-server/data/Machine
cp $file_dir/configs/vscode/server_settings.json ${HOME}/.vscode-server/data/Machine/settings.json
