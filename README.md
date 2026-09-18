# blackboard-git

**Your courses, versioned.** Clone Blackboard course materials. Pull updates. Keep their history.

[中文说明](README.zh-CN.md)

```sh
git clone 'blackboard::https://learn.intl.zju.edu.cn/webapps/blackboard/execute/modulepage/view?course_id=_1234_1' MyCourse
cd MyCourse
git pull --ff-only
```

Replace the example course ID with one you can access. blackboard-git turns a course URL into a **read-only Git remote on your machine**. It fetches materials using your signed-in WebKit session, builds a local snapshot repository, and serves it through Git's remote-helper protocol. No server deployment is needed.

> Experimental macOS tool. Currently validated only against `learn.intl.zju.edu.cn` (ZJU International Campus), not all Blackboard installations.

## What works

- Preserve the course content hierarchy and display names in ordinary folders.
- Download attachments, archive content descriptions and the currently visible announcements page.
- Commit additions, changes and deletions; skip commits when content is unchanged.
- Keep old versions available through normal Git history.
- Sign in through a native window and reuse the persistent local WebKit session.
- Protect conflicting local edits through normal Git behavior; the course remote rejects pushes.

## Install

Requirements: macOS 12+, Python 3.10+, Git 2.28+, and Xcode Command Line Tools with a compatible Swift compiler and macOS SDK. The Python code uses only the standard library.

```sh
git clone https://github.com/THEzsc/blackboard-git.git
cd blackboard-git
python3 native/build.py
python3 install_git_helper.py
export PATH="$HOME/.local/bin:$PATH"
```

Keep this source directory in place: the installed helper links to it. Add the PATH line to your shell profile if needed. The installer refuses to replace an existing helper from another location.

Installation creates `~/.local/bin/git-remote-blackboard` and adds a **host-specific global Git URL rewrite** for `https://learn.intl.zju.edu.cn/`. Once installed, an ordinary copied course URL also works:

```sh
git clone 'https://learn.intl.zju.edu.cn/webapps/blackboard/execute/modulepage/view?course_id=_1234_1' MyCourse
```

Quote URLs containing `&`. Clone into a new or empty directory. A content-page URL selects the whole course via `course_id`, not only the displayed subfolder. Other Git hosts are unaffected.

## Sign in and pull

The first clone opens a native SSO window. Complete your school's login there. This app has a separate session from Chrome. Later pulls reuse the stored session; school session expiry or MFA can require another login.

```sh
cd MyCourse
git pull --ff-only
git log --oneline
git diff --stat HEAD~1 HEAD  # requires at least two commits
```

To recover a historical file without overwriting your working copy:

```sh
git show 'COMMIT:Content/Syllabus.pdf' > /tmp/old-syllabus.pdf
```

PDFs and Office documents retain their historical bytes; Git does not provide meaningful line-by-line diffs inside those formats. Local notes are not automatically committed. If you create local commits, `--ff-only` may require you to resolve the divergent history yourself.

## Session and storage

- Authentication uses the application's persistent `WKWebsiteDataStore.default()` on this Mac. No cookie extraction or custom password storage is implemented.
- Credentials and WebKit session data are not added to course repositories.
- Private local Git caches live under `~/Library/Application Support/BlackboardGit/<course_id>/repository`. Do not edit these caches directly.
- Requests use the logged-in same-origin session. This tool does not submit assignments, answer surveys, or enroll in courses.
- The published source repository contains no real course materials or authentication data. Course clones contain your downloaded materials; choose where you share those separately.

## Current limits

Each pull currently downloads a complete snapshot, with a 300 MB attachment budget. There is no background scheduler, webhook, or incremental network download yet. The login/progress window is displayed on each fetch. Incomplete exports do not publish a new snapshot commit.

External tools, survey/questionnaire engines, submission records and discussions are outside the mirror scope. Announcements cover the current visible page, not guaranteed historical coverage. Empty directories are represented in the manifest but Git itself does not track empty folders. Large binary histories can grow substantially; Git LFS is not integrated.

Course cache histories are local to a machine. Moving an existing checkout to another Mac does not automatically transfer its backing cache history. Fresh clones on independent machines may therefore have unrelated histories.

## How it works

```text
Git clone / pull
    → git-remote-blackboard
    → native WebKit SSO + same-origin course exporter
    → validated snapshot + local Git history
    → git upload-pack
    → your course directory
```

The native export bridge runs in an isolated WebKit content world. The helper accepts only the supported HTTPS host and a course ID; unrelated query parameters are discarded. The server remains a Blackboard server, not a Git server.

## Development

```sh
python3 -m unittest discover -v
python3 native/build.py  # macOS only
```

Tests use synthetic fixtures and isolated caches; no login or real course data is needed. They exercise actual Git clone/pull, HTTPS rewriting, no-op updates, file history, deletion, local-edit protection and rejection of pushes. Live SSO and downloading were separately tested on the supported instance.

`BLACKBOARD_OFFLINE_SNAPSHOT` selects an explicitly logged offline fixture for development. Do not set it for normal online pulls. `BLACKBOARD_CACHE_DIR` overrides the cache directory for isolated tests.

`blackboard_git.py pull SNAPSHOT DESTINATION` imports an already exported snapshot locally. `export-course.js` is also available as a manual browser exporter. Do not mix direct snapshot imports with an existing remote-backed checkout; use its Git remote for routine updates.

## Remove the HTTPS rewrite

```sh
git config --global --unset-all 'url.blackboard::https://learn.intl.zju.edu.cn/.insteadOf' '^https://learn\.intl\.zju\.edu\.cn/$'
```

This leaves your course files and history intact. Explicit `blackboard::https://…` URLs still use the helper while it is installed. To fully uninstall the helper, remove its symlink from `~/.local/bin`.

blackboard-git is an independent project, not affiliated with Blackboard, Anthology or Zhejiang University.
