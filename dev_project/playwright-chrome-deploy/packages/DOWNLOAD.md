# 离线包下载说明

将以下文件下载后放入本目录。

## 必需

### chromium-linux.zip (~150MB)

Chromium revision 1205，对应 @playwright/mcp@0.0.55。

主 CDN：
```
https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1205/chromium-linux.zip
```

备用 CDN：
```
https://playwright.download.prss.microsoft.com/dbazure/download/playwright/builds/chromium/1205/chromium-linux.zip
```

直接下载：
```
https://cdn.playwright.dev/builds/chromium/1205/chromium-linux.zip
```

### chromium-headless-shell-linux.zip (~50MB)

Playwright `--headless` 模式优先使用的轻量 headless shell，同 revision 1205。

主 CDN：
```
https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1205/chromium-headless-shell-linux.zip
```

备用 CDN：
```
https://playwright.download.prss.microsoft.com/dbazure/download/playwright/builds/chromium/1205/chromium-headless-shell-linux.zip
```

## 可选

### remote-browser-viewer-0.1.0.vsix

在 macOS 上构建：
```bash
cd dev_project/vscode-remote-viewer
npm run package
cp remote-browser-viewer-*.vsix ../playwright-chrome-deploy/packages/
```
