#!/bin/sh

# git remote name for public repo
PUBLIC_REMOTE_NAME=pub-github
# git remote name for local "master" repo (tracked upstream repository)
UPSTREAM_REMOTE_NAME=master-repo

for repo_path in *; do [ -d "$repo_path/.git" ] && (
	cd "$repo_path"
	
	no_pub=false
	no_commit=false
	untracked=false
	
	up_head=false
	up_commit=false
	up_tracked=false
	
	if git log --decorate=short -1 | grep HEAD | grep $PUBLIC_REMOTE_NAME > /dev/null
		then no_pub=false; else no_pub=true; fi
	
	if git status --ignore-submodules | grep -E 'Changes (not staged for commit|to be committed):' > /dev/null
		then no_commit=true; else no_commit=false; fi
	
	if git status | grep 'Untracked files:' > /dev/null
		then untracked=true; else untracked=false; fi
	
	upstream_repo_dir=$(git remote -v | grep $UPSTREAM_REMOTE_NAME.*fetch | awk '{print $2}')
	if [ "$upstream_repo_dir" != "" ]; then
		# prepare xgit to run in "master repo"
		gitdir=$(cd "$upstream_repo_dir" && git rev-parse --git-dir)
		worktree=$(cd "$upstream_repo_dir" && git config core.worktree)
		if [ "$worktree" != "" ]; then
			worktree=$(cd "$gitdir"; realpath "$worktree")
		else
			worktree=$(cd "$upstream_repo_dir" && git worktree list | awk '{print $1; exit}')
		fi
		xgit() { git --git-dir="$gitdir" --work-tree="$worktree" "$@"; }
		
		if [ "$(git rev-parse HEAD)" != "$(xgit rev-parse HEAD)" ]
			then up_head=true; else up_head=false; fi
		if xgit status --ignore-submodules | grep -E 'Changes (not staged for commit|to be committed):' > /dev/null
			then up_commit=true; else up_commit=false; fi
		if xgit status | grep 'Untracked files:' > /dev/null
			then up_tracked=true; else up_tracked=false; fi
	fi
	
	if $no_pub || $no_commit || $untracked || $up_head || $up_commit || $up_tracked; then
		echo "$(basename $repo_path)"
		$no_pub     && echo "    → HEAD != $PUBLIC_REMOTE_NAME"
		$no_commit  && echo "    → Not committed changes"
		$untracked  && echo "    → Untracked files"
		$up_head    && echo "    → HEAD != $UPSTREAM_REMOTE_NAME ($upstream_repo_dir)"
		$up_commit  && echo "    → $UPSTREAM_REMOTE_NAME: Not committed changes"
		$up_tracked && echo "    → $UPSTREAM_REMOTE_NAME: Untracked files"
	fi
); done
