# APTV 直播源

## 使用说明

APTV 订阅地址：

```text
https://raw.githubusercontent.com/liao-zc/aptv-live/main/APTV_ALL.m3u
```

在 APTV 中选择“远程订阅”或“通过 URL 添加”，粘贴上述地址并保存。建议开启“启动时刷新”或“自动刷新订阅”。

请勿下载 M3U 后作为本地文件导入，否则无法自动获得后续更新。直播源受地区、运营商和网络环境影响，个别频道可能存在播放差异。

## 维护说明

### 添加频道

进入仓库的 **Issues → New issue → 提交新的直播源**，填写频道名称和公开的 HTTP/HTTPS 直播地址。

维护者也可以编辑 `sources/manual.m3u`：

```m3u
#EXTINF:-1 tvg-name="频道名称" group-title="自有频道",频道名称
https://example.com/live/index.m3u8
```

`sources/` 目录中的所有 `.m3u` 文件都会作为长期候选库参与检测。历史备份频道保存在 `sources/legacy-20260817.m3u`；失效频道不会显示在播放器中，但会保留为注释并持续复测。

### 报告问题

进入 **Issues → New issue → 报告失效或错误频道**，填写频道名称、直播地址、问题类型以及所在地区和网络运营商。

### 手动更新

进入 **Actions → Update APTV playlist → Run workflow**，选择 `main` 分支并运行。

仓库的 **Settings → Actions → General → Workflow permissions** 必须设置为 **Read and write permissions**。

### 本地维护

本地运行需要 Python 3.11+ 和 FFmpeg：

```bash
python3 scripts/build_playlist.py
```

修改完成后提交：

```bash
git add .
git commit -m "更新直播源"
git push
```
