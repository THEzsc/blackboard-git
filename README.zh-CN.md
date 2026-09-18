# blackboard-git

**像管理代码一样管理课程资料。** `git clone` 下载整门课，`git pull` 更新资料，Git 保存每次变化。

[English](README.md)

目前为实验版本：支持 macOS、Windows、Linux 的自动后端选择，目标站点为浙大国际校区 `learn.intl.zju.edu.cn`。学校真实 SSO 已在 macOS 验证；Windows/Linux 仍需实机登录验证，不能把自动测试当作学校 SSO 的验证。

## 安装

需要 Python 3.10+ 和 Git 2.28+；Windows 使用 Git for Windows。macOS 默认后端还需要 macOS 12+ 和包含兼容 Swift 编译器及 SDK 的 Xcode Command Line Tools。Windows/Linux 使用 Playwright，Linux 需要桌面环境完成 SSO。

```sh
git clone https://github.com/THEzsc/blackboard-git.git
cd blackboard-git
python3 setup.py
export PATH="$HOME/.local/bin:$PATH"
```

Windows 使用 `python setup.py`，将 `$HOME\.local\bin` 加入用户 PATH。当前 PowerShell 可执行：

```powershell
$env:Path = "$HOME\.local\bin;" + $env:Path
```

安装器自动识别系统，创建项目 `.venv`，在 macOS 编译 WebKit 后端，在 Windows/Linux 安装 Playwright Python 依赖。**安装时不下载浏览器**。启动器放在 `~/.local/bin` 并引用项目及其 Python 环境，请保留源码目录。更新旧安装时可显式使用 `python3 setup.py --replace-helper`。

## 浏览器怎么复用

- **macOS**：默认使用系统 WebKit，不额外下载浏览器。
- **Windows/Linux**：先查找已有 Chrome、Edge、Chromium。
- **没找到**：查找 Playwright 用户级共享缓存；需要的版本不存在才自动下载。

不同软件使用相同缓存及相同版本时可以共享浏览器程序，不会在每个项目中都放一份。同一缓存也可能保留多个版本。已有浏览器启动失败时会报错，不会默默再下载一份。

默认共享缓存：Windows `%LOCALAPPDATA%\ms-playwright`、Linux `~/.cache/ms-playwright`、macOS `~/Library/Caches/ms-playwright`。可用 `PLAYWRIGHT_BROWSERS_PATH` 指向另一个共享位置，不要设为 `0`。浏览器程序共享，登录配置使用应用独立目录，不占用日常浏览器配置。

可选环境变量：

- `BLACKBOARD_BACKEND=auto|webkit|chromium`：默认自动选择；macOS 也可选 Chromium，Windows/Linux 不支持 WebKit。
- `BLACKBOARD_BROWSER_PATH`：手动指定浏览器可执行文件。
- `PLAYWRIGHT_BROWSERS_PATH`：指定共享浏览器缓存。

macOS 切到 Chromium 时，在安装和使用时都设置，例如 `BLACKBOARD_BACKEND=chromium python3 setup.py`，之后 `BLACKBOARD_BACKEND=chromium git pull --ff-only`。

Linux 若缺系统库，可使用项目环境执行 `python -m playwright install-deps chromium` 安装所需依赖，可能需要管理员权限。

安装时会添加只针对 `https://learn.intl.zju.edu.cn/` 的 Git 全局 URL 转换规则，其他主机不受影响。

## 使用

从浏览器复制带 `course_id` 的课程链接，克隆到新目录或空目录。下面的课程 ID 是示例，需要换成你有权访问的课程：

```sh
git clone 'https://learn.intl.zju.edu.cn/webapps/blackboard/execute/modulepage/view?course_id=_1234_1' MyCourse
cd MyCourse
git pull --ff-only
```

首次会弹出独立登录窗口，在里面完成学校 SSO 登录。登录态与 Chrome 独立，之后会尝试复用本机保存的会话；学校会话过期或要求 MFA 时需重新认证。

课程内容按 Blackboard 显示名称与目录层级落盘，问卷和作业只保存说明，公告保存当前可见页面。新增、修改、删除形成 Git 提交；内容没有变化就不生成提交。你自己的笔记不自动提交，冲突的本地修改由 Git 保护。建议使用 `--ff-only`；自己创建本地提交后可能需要手动处理分叉。

```sh
git log --oneline
git diff --stat HEAD~1 HEAD  # 至少需要两次提交
git show '版本号:Content/Syllabus.pdf' > /tmp/old-syllabus.pdf
```

PDF、Office 文档能取回历史版本，但暂不支持内部逐行差异。链接中的 `course_id` 决定整门课程，子目录参数不会把同步范围限制为单个文件夹。

## 登录与数据

- 登录会话保存在 WebKit 数据仓库或应用独立的 Chromium profile 中，由浏览器管理，不另外保存密码。
- 登录数据不进入课程 Git 仓库；源码仓库不包含真实课程资料。
- 本地数据目录：macOS 为 `~/Library/Application Support/BlackboardGit`，Windows 为 `%LOCALAPPDATA%/BlackboardGit`，Linux 为 `${XDG_DATA_HOME:-~/.local/share}/blackboard-git`。课程缓存位于其中的 `<course_id>/repository`，Chromium 登录配置位于 `chromium-profile`，请勿手动编辑缓存。
- 学校服务器无需部署任何东西。工具用已有网页会话读取课程，通过本地 Git 适配器提供只读远端，不支持 `git push`。
- 不会提交作业、填写问卷或选课。课程克隆包含你下载的资料，请自行决定资料的分享范围。

## 当前边界

每次 pull 仍会完整下载，附件预算为 300 MB；尚无网络增量下载、后台定时同步或服务器推送。每次拉取都会显示窗口。下载失败或快照不完整时，不发布新提交。

不覆盖外部教学工具、问卷作答引擎、提交记录与讨论；公告仅覆盖当前可见页面。Git 不存储空文件夹，目录记录保存在清单中。大文件历史会增加磁盘占用，目前未集成 Git LFS。

缓存历史保存在当前电脑。换电脑时直接搬课程工作目录不会自动搬走缓存历史；不同电脑首次生成的课程仓库可能具有不相干的历史。

## 测试与卸载

```sh
python3 -m unittest discover -v
python3 native/build.py
```

自动测试使用合成资料，不要求登录，覆盖真实 Git clone/pull、HTTPS 链接转换、重复同步、修改历史、删除、本地修改保护及拒绝推送。增加了真实 Chromium 浏览器测试，用合成响应验证导出与会话持久化，不访问学校站点。线上 SSO、会话复用和拉取已在 macOS 单独验证；Windows/Linux 学校登录仍待实机验证。

移除 HTTPS 转换规则：

```sh
git config --global --unset-all 'url.blackboard::https://learn.intl.zju.edu.cn/.insteadOf' '^https://learn\.intl\.zju\.edu\.cn/$'
```

这不会删除课程资料或 Git 历史。移除规则后仍可使用 `blackboard::https://…` 格式；完整卸载 helper 时删除 `~/.local/bin/git-remote-blackboard` 启动器。开发环境变量及组件说明见英文文档。

blackboard-git 是独立项目，与 Blackboard、Anthology 或浙江大学无隶属关系。
