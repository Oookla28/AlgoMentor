# 本机 DNS 解析失败诊断

## 现象

- `git push` / `curl https://github.com` 报 `Could not resolve host: github.com`
- 同一时间直连 GitHub IP 的 443 端口正常（HTTP 200），说明出口网络与 TLS 没有整体中断
- `scutil --dns` 显示系统 resolver 为 `223.5.5.5`，并标记为 Reachable
- `dig +time=2 +tries=1 github.com` 返回 `connection timed out; no servers could be reached`
- `dig @8.8.8.8 github.com` 能返回响应

## 原因

本机当前使用的 DNS 服务器 `223.5.5.5` 实际不可用：macOS 的 resolver 配置来自系统网络服务/DHCP，`scutil` 的 Reachable 标志只表示路由层可达，不代表 DNS 查询能返回。对该地址的 DNS 查询超时，而改用 `8.8.8.8` 可以解析。因此这是**配置的 DNS 服务器不可用或被网络过滤**，不是 GitHub 单独故障，也不是应用代码问题。

`/etc/resolv.conf` 在 macOS 上不是主要解析来源，手工改它通常无效；应修改“系统设置 → 网络 → DNS”，或修正路由器的 DHCP DNS。

## 修复建议

1. 系统设置 → 网络 → 当前连接 → 详情 → DNS，改为 `8.8.8.8`、`1.1.1.1`（或可用的内网 DNS）。
2. 刷新缓存（需要管理员权限）：
   ```bash
   sudo dscacheutil -flushcache
   sudo killall -HUP mDNSResponder
   ```
3. 验证：
   ```bash
   dig +time=2 +tries=1 github.com
   git ls-remote https://github.com/Oookla28/AlgoMentor.git
   ```

## 本次 Skill 内置的处理方式

为了不在系统层面修改 DNS，本次固定版本文件通过以下方式获取：

- 先用 `git ls-remote`（临时 CONNECT 代理只把 `github.com` 解析到已知 GitHub IP）取得真实 commit；
- 再用 `curl --resolve raw.githubusercontent.com:443:<known-ip>` 下载固定 commit 的 `SKILL.md` 与许可证；
- 计算真实 SHA-256，记录到 `skills.lock.json` / `agent_skills/development/index.json`；
- 临时代理在推送/下载结束后关闭，不写入系统设置，不修改 `/etc/hosts`，不设置全局代理。

应用运行时不需要访问 GitHub 或任何外部 DNS；只有开发/维护时的更新需要网络。
