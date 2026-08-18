# APTV 独立聚合与自动更新

手机 APTV 订阅地址：

```text
https://raw.githubusercontent.com/liao-zc/aptv-live/main/APTV_ALL.m3u
```

在 APTV 中选择“远程订阅”或“通过 URL 添加”，并开启启动时刷新。不要下载后作为本地文件导入。

## 系统现在如何工作

仓库不再只是复制某一个上游结果。每15分钟运行一次自己的聚合流水线：

1. 读取 `config/upstreams.json` 中登记的多个公开订阅；
2. 读取 `sources/manual.m3u` 自有候选库；
3. 将上一版成功结果作为历史候选，避免上游短暂消失；
4. 读取带有 `aptv-source-submission` 标记的 GitHub Issue 社区提交；
5. 拒绝内网、回环、链路本地地址及跳转到内网的 URL，降低 SSRF 风险；
6. 实际读取 HLS 清单和媒体分片，测量响应延迟及传输速度；
7. 使用 FFprobe 确认存在视频流并获取分辨率；
8. 使用历史成功率、速度、延迟和分辨率综合评分；
9. 使用 `config/aliases.json` 合并同一频道的不同名称；
10. 每个频道及每个 URL 只发布一个优先结果；
11. 发布前再次读取 HLS 清单和媒体分片，进行即时复检；
12. 整组无可播放地址的频道以 `#DISABLED-*` 注释保留，APTV不会显示；
13. 每15分钟重新检测注释频道，恢复后自动取消注释；
14. 按央视数字顺序、卫视、港澳台、地方台、其他频道固定排序；
15. 少于150个频道时拒绝覆盖，继续保留上一版。

结果和诊断数据：

- `APTV_ALL.m3u`：手机订阅的最终列表；
- `data/history.json`：每条地址的历史成功、失败、速度及延迟；
- `reports/latest.json`：最近一次候选数、频道数和选中结果；
- `sources/manual.m3u`：仓库自己维护的候选地址；
- `config/aliases.json`：频道别名到统一名称的映射；
- `config/upstreams.json`：外部候选入口和安全阈值。

## 添加自己的频道

推荐使用仓库的 **Issues → New issue → 提交新的直播源**。提交不会直接进入订阅，必须通过公网地址检查、HLS分片读取和 FFmpeg 视频验证。

仓库维护者也可以编辑 `sources/manual.m3u`：

```m3u
#EXTINF:-1 tvg-name="频道名称" group-title="自有频道",频道名称
https://example.com/live/index.m3u8
```

提交后会自动触发更新。

## 报告失效或错配

使用 **Issues → New issue → 报告失效或错误频道**，填写频道、当前 URL、问题类型及所在地区。自动检测仍以实际网络探测为准，避免单个匿名报告直接删除频道。

## 多节点探测

默认节点是 GitHub Ubuntu 云端。`scripts/build_playlist.py` 支持区域探测报告：

```bash
python3 scripts/build_playlist.py --node asia-self-hosted --probe-only reports/probes/asia.json
```

`.github/workflows/asia-probe.example.yml` 是亚洲自托管节点模板。只有注册了带 `self-hosted, asia, aptv-probe` 标签的服务器后才能改名启用。主任务会合并24小时内的区域报告，并按评分选择更合适的地址。

GitHub官方运行器不能指定中国或亚洲区域，因此仓库不会伪装地域测速。若要让测速更接近中国手机网络，需要在中国香港、日本、新加坡或中国大陆合规服务器上注册自托管 GitHub Runner。

## 自动任务

工作流位于 `.github/workflows/update-playlist.yml`，支持：

- 每15分钟定时执行；
- 修改脚本、配置或自有候选库后立即执行；
- 新建或编辑 Issue 后立即审核；
- 手动 `Run workflow`；
- 失败自动重试三次；
- 更新异常时不覆盖上一版。

最终 M3U 中只有同时通过 HLS 媒体分片读取、FFmpeg 视频流确认和发布前即时复检的频道处于激活状态。失效频道的信息仍在文件底部，但所有相关行均以 `#` 开头，因此播放器不会把它们当作可播放频道；后续任务会持续重试。

在仓库 **Settings → Actions → General → Workflow permissions** 中必须选择 **Read and write permissions**。

## 本地运行

需要 Python 3.11+ 和 FFmpeg：

```bash
python3 scripts/build_playlist.py
```

项目只使用 Python 标准库，不需要安装 pip 依赖。

## 边界说明

任何聚合器都需要公开网站、电视台接口、社区提交或已有地址作为候选入口。“独立”指本仓库拥有自己的候选库、审核、安全校验、视频检测、评分、历史和发布体系，而不是声称能在没有任何公开入口的情况下凭空生成直播地址。
