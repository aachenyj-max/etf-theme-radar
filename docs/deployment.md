# 内部试用部署手册

本手册适用于约 5 位内部用户。当前运行模型是**单台常驻 Linux 主机、一个 API/Worker 实例和本机 SSD 上的 SQLite**。不要把 `data/radar.db` 放到 NFS、SMB 或多主机共享卷，也不要增加 Uvicorn worker 数或 Compose 副本数。

## 上线前准备

1. 准备 Ubuntu LTS 主机（建议 2 vCPU、4 GB RAM、60 GB SSD；启用浏览器采集时使用 4 vCPU、8 GB RAM）。
2. 安装 Docker Engine 和 Docker Compose 插件。
3. 为正式外网地址准备一个域名，并把它的 A 记录指向服务器公网 IP。若仅公司内网使用，可继续保持本机入口并由内网网关转发。
4. 不要为 8001、3000 或 SQLite 打开防火墙端口；它们只存在于 Docker 内部网络。
5. 提前准备一个加密的异地备份位置。`backups/` 只是本机暂存目录，不是异地备份。

## 首次部署

```bash
cp deploy/.env.production.example deploy/.env.production
chmod 600 deploy/.env.production
# 编辑 deploy/.env.production：填入真实 key、SEC 联系方式、OpenAlex 邮箱与正式地址。

docker compose --env-file deploy/.env.production -f compose.production.yml build
docker compose --env-file deploy/.env.production -f compose.production.yml up -d
docker compose --env-file deploy/.env.production -f compose.production.yml ps
curl --fail http://127.0.0.1:8080/health
```

默认端口只绑定到 `127.0.0.1:8080`。产品内置账号登录，首次部署时在服务器项目目录执行 `python tools/create_internal_users.py --count 5`，将输出的三行 `INTERNAL_AUTH_*` 配置粘贴到 `deploy/.env.production`，再通过私密渠道把五组账号密码分别发给同事。密码只在生成时显示一次，环境文件中只保存哈希。

如需让外网同事直接通过网页使用，在确认域名 DNS 已生效后使用公开 HTTPS 覆盖配置：

```bash
docker compose --env-file deploy/.env.production -f compose.production.yml -f compose.public.yml up -d --build
```

这会只开放 80/443，Caddy 自动申请 HTTPS 证书；8001、3000 和 SQLite 仍不会对公网开放。不要用 HTTP 公网 IP 分享账号密码。公司 VPN、Cloudflare Access 仍可作为额外保护，但不再是使用产品的前提。

检查 `/api/capabilities` 中的服务契约及两个 Worker 心跳。生产地址通过 `PUBLIC_API_URL` 和 `PUBLIC_FRONTEND_URL` 写入能力响应，必须是用户实际访问的 HTTPS 地址。

## 发布与回滚

每次发布前先备份，再构建和替换单一实例：

```bash
docker compose --env-file deploy/.env.production -f compose.production.yml --profile maintenance run --rm backup
docker compose --env-file deploy/.env.production -f compose.production.yml up -d --build
docker compose --env-file deploy/.env.production -f compose.production.yml logs --tail=100 api frontend caddy
```

挂载持久卷时部署会有短暂中断；这符合当前 SQLite 单实例的安全边界。若健康检查、Worker 心跳或业务验收失败，使用上一版镜像重新执行 `up -d`，不要并行运行两个 API 容器。

## 备份与恢复

备份命令使用 SQLite 在线备份 API，并生成 SHA-256 元数据：

```bash
docker compose --env-file deploy/.env.production -f compose.production.yml --profile maintenance run --rm backup
```

建议每天至少一次，并将生成的 `backups/radar-*.db` 和同名 `.json` 加密复制到异地。恢复前必须停掉服务、保留当前数据卷快照，并执行恢复演练：

```bash
docker compose --env-file deploy/.env.production -f compose.production.yml stop caddy frontend api
docker compose --env-file deploy/.env.production -f compose.production.yml --profile maintenance run --rm --no-deps restore \
  --backup /backups/radar-YYYYMMDDTHHMMSSZ.db \
  --target /app/data/radar.db \
  --confirm-target /app/data/radar.db
docker compose --env-file deploy/.env.production -f compose.production.yml up -d
```

恢复服务只在 `maintenance` profile 中存在，并将 `./backups` 只读挂入容器。恢复脚本要求 `--confirm-target` 与容器内解析后的目标路径完全一致，防止误覆盖。

## 上线验收

- 未登录或非公司账号无法触及入口及 API。
- 5 位用户并发浏览、同时创建任务时，一个任务执行、其余 FIFO 排队。
- 研究运行中的 SSE 至少保持 15 分钟；断线后页面回退轮询。
- 在采集、分析、审计阶段各重启一次 API，确认 lease 和 Worker 可以恢复且不产生重复版本。
- 演练 DeepSeek、Yahoo、天天基金和 OpenAlex 超时/限流，确认状态降级且最后成功快照不被覆盖。
- 将备份恢复到独立环境，核对报告版本、引用、主题和证据数量。

当前应用提供统一权限的内部账号、签名 HttpOnly 会话 Cookie 和跨站写操作来源校验；五个账号均可浏览和使用全部页面。正式扩大使用前，仍建议把用户身份写入审核和发布审计记录，并根据岗位增加角色权限。
