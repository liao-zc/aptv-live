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

在播放器中添加远程 M3U 订阅并开启自动刷新。备用地址可能有缓存延迟。

## 更新说明

订阅每小时自动更新。手动更新请进入 GitHub 仓库的 **Actions → Update IPTV playlist → Run workflow**。

无效频道会暂时注释并继续复测；检测恢复后会自动重新启用。
