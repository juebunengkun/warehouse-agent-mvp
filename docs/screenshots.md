# Screenshots

README 中优先展示复杂渠道经营日报测试截图：

- `docs/screenshots/complex-modeling-strategy.png`
- `docs/screenshots/complex-sql-style-review.png`

`home.svg` 和 `generated-report.svg` 是可直接提交到 GitHub 的轻量界面预览图。

如果需要生成真实 PNG 截图，可以先启动应用：

```powershell
.\run_app.ps1
```

然后在普通 Windows 终端中使用 Edge headless：

```powershell
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
& $edge --headless=new --disable-gpu --window-size=1440,1200 --virtual-time-budget=8000 --screenshot=docs\home.png http://127.0.0.1:8501/
```

Streamlit 使用 WebSocket 渲染，部分 headless 浏览器会截到加载空白页。如果遇到这种情况，建议直接用浏览器打开页面，点击“跳过确认，直接生成”或完成“解析需求 -> 确认并生成方案”，再使用浏览器自带截图或开发者工具保存页面。
