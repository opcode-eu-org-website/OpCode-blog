#!/bin/bash

set -e
REPO_PATH=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename $REPO_PATH)
REPO_GIT=$(git rev-parse --git-dir)

PASS_FILE="/sciezka/do/hasla/do/szyfrowania/restic"
REMOTES="
# można używać bezpośrednio sftp
sftp:user@host:/path/
# ale jeżli mamy dostęp ssh i możliwość uruchomia restic-rest-server po stronie zdalnej) to dużo szybciej będzie działać poprzez rest 
rest-tunnel user@host 8008 /path/
"

# read PASS_FILE and REMOTES from per repo config file
. "$REPO_GIT/git2restic.conf"

SSH_CTL_SOCK="/tmp/ssh-restic-$$.sock"
cleanup() {
	ssh -S "$SSH_CTL_SOCK" "$REMOTE_HOST" "kill $REMOTE_PID" 2>/dev/null || true
	ssh -S "$SSH_CTL_SOCK" -O exit "$REMOTE_HOST" 2>/dev/null || true
	rm -f "$SSH_CTL_SOCK"
}
trap cleanup EXIT

cd $REPO_PATH

while read REMOTE HOST LOCAL_PORT BASE_PATH REMOTE_PORT; do
	case "$REMOTE" in
		"" | \#*)
			continue
			;;
		"rest-tunnel")
			REMOTE_PORT=${REMOTE_PORT:-$LOCAL_PORT}
			ssh -f -N -M -S "$SSH_CTL_SOCK" -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "$HOST"
			REMOTE_PID=$(ssh -S "$SSH_CTL_SOCK" "$HOST" "nohup restic-rest-server --path '$BASE_PATH/$REPO_NAME' --listen 127.0.0.1:${REMOTE_PORT} --no-auth >/dev/null 2>&1 & echo \$!")
			REMOTE_HOST=$HOST
			
			for i in $(seq 1 50); do
				if bash -c "exec 3<>/dev/tcp/127.0.0.1/${LOCAL_PORT}" 2>/dev/null; then
					break
				fi
				if [ $i -eq 50 ]; then
					echo; echo "ERROR: SSH tunnel (to $HOST) not created"; exit 1
				fi
				sleep 0.1
			done
			
			REMOTE="rest:http://127.0.0.1:${LOCAL_PORT}"
			;;
		*)
			REMOTE=$REMOTE/$REPO_NAME
	esac
	
	case "${1:-backup}" in
		"init")
			restic --password-file "$PASS_FILE" --repo "$REMOTE" init
			;;
		"backup")
			restic --password-file "$PASS_FILE" --repo "$REMOTE" backup --host "$REPO_NAME" --skip-if-unchanged .
			;;
		"mount")
			restic --password-file "$PASS_FILE" --repo "$REMOTE" mount $2
			;;
		"clean")
			restic --password-file "$PASS_FILE" --repo "$REMOTE" forget --keep-last ${2:-1} --prune
			;;
	esac
done <<< "$REMOTES"
