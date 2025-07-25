# Debug in vscode using tunnel in the terminal of interactive node

mkdir -p /run/user/$HOST_USER_ID # Create the run directory so that cursor socket can be created

# Run in the enroot environment
wget  https://api2.cursor.sh/updates/download-latest?os=cli-alpine-x64 -O /tmp/cursor.tar.gz;

tar -xzvf /tmp/cursor.tar.gz -C /tmp;

/tmp/cursor tunnel --verbose --cli-data-dir ../../submit/.cursor;