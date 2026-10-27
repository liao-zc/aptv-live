# IPTV 直播源

## 使用说明

主订阅地址：

```text
https://raw.githubusercontent.com/liao-zc/iptv-live/main/IPTV_ALL.m3u
```

备用订阅地址（主地址访问困难时可尝试）：

```text
https://testingcf.jsdelivr.net/gh/liao-zc/iptv-live@main/IPTV_ALL.m3u
```

在 IPTV 播放器中添加远程 M3U 订阅，粘贴其中一个地址并保存。建议开启自动刷新订阅，不要作为本地文件导入。

订阅每小时更新一次。备用地址可能存在缓存延迟，且不保证在所有网络下可访问。直播播放效果受地区、运营商和网络环境影响。

## 维护说明

### 添加频道

进入 **Issues → New issue → 提交新的直播源**，填写频道名称和公开的 HTTP/HTTPS 直播地址。

也可以编辑 `sources/manual.m3u`：

```m3u
#EXTINF:-1 tvg-name="频道名称" group-title="其他频道",频道名称
https://example.com/live/index.m3u8
```

分类请使用：央视频道、卫视频道、港澳台频道、国际频道、地方频道、其他频道、动画频道、体育频道、经典剧场、成人频道。成人频道放在最后。

### 报告问题

进入 **Issues → New issue → 报告失效或错误频道**，填写频道名称、直播地址、问题类型、所在地区和网络运营商。

### 手动更新

进入 **Actions → Update IPTV playlist → Run workflow**，选择 `main` 分支并运行。

在 **Settings → Actions → General → Workflow permissions** 中选择 **Read and write permissions**。

### 本地维护

安装 Python 3.11+ 和 FFmpeg，然后运行：

```bash
python3 scripts/build_playlist.py
```

修改后提交：

```bash
git add .
git commit -m "更新直播源"
git push
```
