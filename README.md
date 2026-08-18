# APTV 自动更新直播源

手机 APTV 订阅地址：

```text
https://raw.githubusercontent.com/liao-zc/aptv-live/main/APTV_ALL.m3u
```

在 APTV 中选择“远程订阅”或“通过 URL 添加”，不要下载后作为本地文件导入。需要立即获取 GitHub 上的新版时，在 APTV 中手动刷新订阅。

## 自动更新方式

GitHub Actions 每天北京时间 04:30 执行：

1. `update-playlist.ps1` 下载 Guovin/TV 聚合、测速后的最新版；
2. `clean-playlist.ps1` 并发检测地址；
3. 每个频道和每个 URL 只保留一条；
4. 删除没有任何可用候选地址的频道；
5. 将更新后的 `APTV_ALL.m3u` 提交回 `main` 分支。

清理脚本设有安全下限：如果网络异常导致不足 150 个频道通过检测，任务会失败并保留仓库中的上一版列表。

## 第一次启用

进入仓库的 **Settings → Actions → General → Workflow permissions**，选择 **Read and write permissions** 并保存。

然后进入 **Actions → Update APTV playlist → Run workflow**，选择 `main` 后运行。任务显示绿色对号即表示配置成功。

## 手动在 Windows 更新

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\update-playlist.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\clean-playlist.ps1
```

脚本修改播放列表前会生成 `.bak` 备份；备份文件已由 `.gitignore` 排除，不会上传 GitHub。

## 常见问题

- Raw 地址显示 `404`：确认仓库为 Public、默认分支为 `main`，且根目录存在 `APTV_ALL.m3u`。
- Actions 出现 `403` 或无法 `git push`：重新检查 Workflow permissions 是否为 Read and write。
- 手机没有看到新版：在 APTV 中手动刷新；GitHub 定时任务可能有几分钟延迟。
- 手机无法打开 Raw 地址：先用手机浏览器测试订阅地址。部分网络访问 GitHub 较慢，可切换网络后刷新。

直播源可用性与运营商、地区和 IPv6 支持有关，无法保证所有频道在所有网络中表现一致。
