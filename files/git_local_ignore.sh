#!/bin/sh

# ignorowanie zmian w kopii roboczej tylko dla określonej wersji pliku
# (w odróżnieniu od `git update-index --skip-worktree` plik automatycznie
# przestanie być ignorowany po wprowadzeniu nowych zmian lub nowej wersji w repo)

# UŻYCIE:
#   git config filter.my_ignore.clean "git_local_ignore.sh clean '%f'"
#   git config filter.my_ignore.smudge "git_local_ignore.sh smudge '%f'
#
#   echo "PLIK_DO_IGNOROWANIA filter=my_ignore" >> "$(git rev-parse --git-dir)/info/attributes"
#   git show HEAD:PLIK_DO_IGNOROWANIA > "$(git rev-parse --git-dir)/ignored/repo/PLIK_DO_IGNOROWANIA"
#   cp PLIK_DO_IGNOROWANIA "$(git rev-parse --git-dir)/ignored/local/PLIK_DO_IGNOROWANIA"

mode=$1
repo_path=$2
base_path="$(git rev-parse --git-dir)/ignored"
temp=$(mktemp)

cat > "$temp"
temp_sum=$(md5sum "$temp" | awk '{print $1}')

case $mode in
	clean) # to repo version
		sum=$(md5sum "$base_path/local/$repo_path" | awk '{print $1}')
		if [ "$sum" = "$temp_sum" ]; then
			cat "$base_path/repo/$repo_path"
		else
			cat "$temp"
		fi
		;;
	smudge) # to workdir version
		sum=$(md5sum "$base_path/repo/$repo_path" | awk '{print $1}')
		if [ "$sum" = "$temp_sum" ]; then
			cat "$base_path/local/$repo_path"
		else
			cat "$temp"
		fi
		;;
esac
rm -fr "$temp"
