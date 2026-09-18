# blackboard-git

**Your courses, versioned.** Clone Blackboard course materials. Pull updates. Keep their history.

[中文说明](README.zh-CN.md)

```sh
git clone 'blackboard::https://learn.intl.zju.edu.cn/webapps/blackboard/execute/modulepage/view?course_id=_1234_1' MyCourse
cd MyCourse
git pull --ff-only
```

Replace the example course ID with one you can access. blackboard-git turns a course URL into a **read-only Git remote on your machine**. It fetches materials using your signed-in WebKit session, builds a local snapshot repository, and serves it through Git's remote-helper protocol. No server deployment is needed.

> Experimental cross-platform tool. Live school SSO has been validated on macOS; Windows/Linux support is implemented with automated synthetic-browser tests in CI. Currently supports only `learn.intl.zju.edu.cn` (ZJU International Campus), not all Blackboard installations.

## What works

- Preserve the course content hierarchy and display names in ordinary folders.
- Download attachments, archive content descriptions and the currently visible announcements page.
- Commit additions, changes and deletions; skip commits when content is unchanged.
- Keep old versions available through normal Git history.
- Sign in through a native window and reuse the persistent local WebKit session.
- Protect conflicting local edits through normal Git behavior; the course remote rejects pushes.

## Install

Requirements: Python 3.10+ and Git 2.28+. On Windows install Git for Windows. The default macOS backend additionally needs macOS 12+ and Xcode Command Line Tools with a compatible Swift compiler and SDK. Windows/Linux use Playwright with an existing desktop browser; Linux needs a graphical session for interactive SSO.

```sh
git clone https://github.com/THEzsc/blackboard-git.git
cd blackboard-git
python3 setup.py
export PATH="$HOME/.local/bin:$PATH"
```

On Windows use `python setup.py` and add `$HOME\.local\bin` to your user PATH (or use `$env:Path = "$HOME\.local\bin;" + $env:Path` for the current PowerShell session).

Setup detects the platform and creates a local `.venv`. It builds WebKit on macOS, or installs the Playwright Python dependency on Windows/Linux. **Setup does not download a browser.** Keep the source directory in place: the launcher references it and its Python environment. Add the PATH line to your shell profile if needed. An existing helper from another installation is preserved unless you explicitly use `python3 setup.py --replace-helper`.

### Browser selection and shared downloads

| Platform | Default backend | Browser selection |
| --- | --- | --- |
| macOS | System WebKit | No additional browser download |
| Windows | Chromium | Installed Chrome, Edge or Chromium first |
| Linux | Chromium | Installed Chrome, Edge or Chromium first |

If no installed browser is found, the Chromium backend checks Playwright's standard **user-level shared cache**. It downloads the required version only when missing; browser binaries are not bundled into each project. Tools using the same cache and browser revision can share them, while different revisions may coexist.

Cache locations are `%LOCALAPPDATA%\ms-playwright` on Windows, `~/.cache/ms-playwright` on Linux and `~/Library/Caches/ms-playwright` on macOS. `PLAYWRIGHT_BROWSERS_PATH` can select another shared cache (do not use `0` for shared storage). The app's login profile stays separate from your everyday browser profile.

An installed browser that cannot launch produces an error instead of silently downloading another copy. Managed browser policies or incompatible versions may require choosing a different binary. Linux may need system packages; run `python -m playwright install-deps chromium` using the project environment if required (this may request administrator privileges).

Optional settings:

- `BLACKBOARD_BACKEND=auto|webkit|chromium`: default `auto`. WebKit is macOS-only. To opt into Chromium on macOS, set this variable before running setup and when running Git.
- `BLACKBOARD_BROWSER_PATH`: explicitly choose a Chrome/Edge/Chromium executable.
- `PLAYWRIGHT_BROWSERS_PATH`: share a specific browser-binary cache across tools.

For example: `BLACKBOARD_BACKEND=chromium python3 setup.py`, then `BLACKBOARD_BACKEND=chromium git pull --ff-only`.

Installation creates `~/.local/bin/git-remote-blackboard` and adds a **host-specific global Git URL rewrite** for `https://learn.intl.zju.edu.cn/`. Once installed, an ordinary copied course URL also works:

```sh
git clone 'https://learn.intl.zju.edu.cn/webapps/blackboard/execute/modulepage/view?course_id=_1234_1' MyCourse
```

Quote URLs containing `&`. Clone into a new or empty directory. A content-page URL selects the whole course via `course_id`, not only the displayed subfolder. Other Git hosts are unaffected.

## Sign in and pull

The first clone opens a WebKit window or an app-owned Chromium browser window. Complete your school's login there. This app has a separate session from Chrome. Later pulls reuse the stored session; school session expiry or MFA can require another login.

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

- Authentication uses persistent WebKit storage on macOS, or a dedicated `chromium-profile` under the app data directory. Browser sessions are managed by the browser; no custom password storage is implemented.
- Credentials and browser session data are not added to course repositories.
- Local Git caches live under `<app-data>/<course_id>/repository`: `~/Library/Application Support/BlackboardGit` on macOS, `%LOCALAPPDATA%/BlackboardGit` on Windows, and `${XDG_DATA_HOME:-~/.local/share}/blackboard-git` on Linux. Do not edit these caches directly.
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
    → platform detection → WebKit or shared Chromium + same-origin exporter
    → validated snapshot + local Git history
    → git upload-pack
    → your course directory
```

The export bridge runs in an isolated WebKit content world or Chromium isolated execution context, separate from the page’s own JavaScript. The helper accepts only the supported HTTPS host and a course ID; unrelated query parameters are discarded. The server remains a Blackboard server, not a Git server.

## Development

```sh
python3 -m unittest discover -v
BLACKBOARD_BROWSER_TESTS=1 .venv/bin/python -m unittest test_chromium_integration -v
python3 native/build.py  # macOS WebKit build
```

Tests use synthetic fixtures and isolated caches; no login or real course data is needed. They exercise actual Git clone/pull, HTTPS rewriting, no-op updates, file history, deletion, local-edit protection and rejection of pushes. A real Chromium integration test uses synthetic intercepted responses to exercise exporting and session persistence, without contacting the school. Live school SSO and downloading have been separately tested on macOS; Windows/Linux school SSO still needs device-level verification.

`BLACKBOARD_OFFLINE_SNAPSHOT` selects an explicitly logged offline fixture for development. Do not set it for normal online pulls. `BLACKBOARD_CACHE_DIR` overrides the cache directory for isolated tests.

`blackboard_git.py pull SNAPSHOT DESTINATION` imports an already exported snapshot locally. `export-course.js` is also available as a manual browser exporter. Do not mix direct snapshot imports with an existing remote-backed checkout; use its Git remote for routine updates.

## Remove the HTTPS rewrite

```sh
git config --global --unset-all 'url.blackboard::https://learn.intl.zju.edu.cn/.insteadOf' '^https://learn\.intl\.zju\.edu\.cn/$'
```

This leaves your course files and history intact. Explicit `blackboard::https://…` URLs still use the helper while it is installed. To fully uninstall the helper, remove its launcher from `~/.local/bin`.

blackboard-git is an independent project, not affiliated with Blackboard, Anthology or Zhejiang University.

## Troubleshooting

- **Incomplete export:** the terminal reports the failing stage, item ID and reason. Recognized empty announcement views are valid; login, permission errors, unknown layouts and failed attachments still block incomplete commits.
- **Not a Git repository:** `git clone URL` creates a child directory by default. Specify the destination (`git clone 'COURSE_URL' MyCourse`), then enter it before pulling. `git clone 'COURSE_URL' .` requires an empty current directory; preserve any existing personal materials.
