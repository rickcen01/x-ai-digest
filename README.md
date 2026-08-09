# X 每日 AI 情报

独立、无界面的 X 个性化资讯任务。它使用自己的持久会话，调用 X 网页端 `HomeTimeline` 获取“为你推荐”，筛选 AI 内容并生成带原帖和外链的中文日报。运行过程不依赖 Browser AI Studio。

## 当前设计

- 账号：默认使用独立 Chromium 档案，只在首次登录时显示窗口；每日任务为 headless。另保留 `twscrape 0.20.0` 代码访问模式。
- 推荐流：读取账号对应的 `HomeTimeline`，不是公开搜索结果。
- 兼容性：操作 ID 失效时会尝试从当前 X 网页脚本重新发现。
- 筛选：按 AI 关键词、时间、互动量排序，并使用 `state/seen.json` 避免每天重复。
- 总结：默认生成结构化中文摘要；配置 OpenAI 兼容模型后可生成更深入的综合总结。
- 发送：始终保存本地 Markdown；可选飞书、Telegram，或由 Codex 定时任务把日报发到当前任务。

## 初始化

```powershell
cd D:\codexbushu\x-ai-digest
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\import-account.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\doctor.ps1
```

`import-account.ps1` 默认从旧 `twscrape-main` 的账号库复制一份独立数据库，并清除复制品中的旧队列锁。源数据库不会被修改。

如果诊断显示本地账号为 active，但实际请求提示会话已退出，可尝试用账号库中已有的登录资料刷新新数据库：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\refresh-account.ps1
```

如 X 要求邮箱验证码，改用 `-Manual` 并在终端输入。刷新只修改本项目的 `data/accounts.db`。

默认抓取源是独立持久浏览器。首次运行前登录一次：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\login.ps1
```

登录成功后窗口自动关闭，之后 `run.ps1` 始终以无界面模式使用 `data/browser-profile`。该档案与 Browser AI Studio 完全分离。

如果云电脑没有可查看的桌面、只能通过手机终端控制，可使用无头终端登录：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\login-headless.ps1
```

账号、密码和验证码只在云电脑终端交互输入，密码不会写入项目文件；成功后仅保留浏览器会话档案。网页登录会话失效时，需要再次由用户完成一次授权，不会自动反复尝试密码。

## 跨云电脑迁移登录会话

登录完成后，由你在本机终端运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export-session.ps1
```

命令会要求输入至少 12 个字符的加密密码，并生成 `data/x-session.xsession`。文件中不保存明文 Cookie，但仍应按密码文件保护。把项目和该文件复制到云电脑，完成 `setup.ps1` 后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\import-session.ps1 -Source .\data\x-session.xsession
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Preview
```

导出/导入命令不会打印 Cookie 值。跨设备、跨 IP 使用可能触发 X 的安全验证；加密会话包无法绕过 X 主动撤销会话。

本项目可以公开发布代码，但不要把 `data/x-session.xsession`、`data/browser-profile/`、`data/*.db`、`.env` 或报告中的私人内容上传到公开仓库。会话包即使加密，也应放在私有存储中，通过安全方式复制到云电脑。

## 从 GitHub 部署到云电脑

公开代码仓库地址：`https://github.com/rickcen01/x-ai-digest`

在云电脑执行：

```powershell
git clone https://github.com/rickcen01/x-ai-digest.git
cd x-ai-digest
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

再通过私密文件传输把本机的 `data/x-session.xsession` 放到云电脑的同一路径，运行导入和预览命令。会话包不在公开仓库中。

## 运行

预览测试，不发送、不记录已读：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 --preview
```

正式运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

最新结果固定写入 `reports/latest.md`，历史报告按日期保存。

## 深度 AI 总结与发送渠道

复制 `.env.example` 为 `.env`，填入需要的密钥；不要把 `.env` 提交到 Git。然后修改 `config.json`：

- 深度总结：设置 `llm.enabled=true`、`llm.model`，并配置兼容的 `base_url`。
- 飞书：在 `delivery.channels` 增加 `feishu`。
- Telegram：在 `delivery.channels` 增加 `telegram`。

## Windows 定时任务

下面命令会创建每天 09:00、网络可用时运行的任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-task.ps1 -DailyAt 09:00
```

网页登录 Cookie 无法保证永久有效：X 主动撤销会话、修改密码或触发验证时仍需重新登录并重新导入一次。每天正常读取通常能及早发现失效，任务会明确报告会话问题，不会自动反复尝试密码登录。
