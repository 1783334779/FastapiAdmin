# master 推送自动部署

本仓库的发布入口是 `.github/workflows/deploy.yml`。本文件说明实现，不表示任意一次工作流都已成功；每次发布结果以 GitHub Actions 与线上版本号为准。

## 1. 以后怎样发布

只提交你确认需要发布的源文件，然后执行：

```bash
git push origin master
```

本地 `git commit` 本身不会发布。推送到其它分支不会部署生产服务器。

进入 GitHub 仓库的 **Actions → Deploy master**，查看本次执行。也可以在该工作流点击 **Run workflow**，选择 master 手动重试。

工作流依次执行：

1. 调用现有后端检查、前端检查、密钥扫描。任一失败，不执行发布。
2. 使用本次提交通过检查的前端成品，不在发布阶段另找一份旧 dist。
3. 复用 `docker/backend/Dockerfile`，在 GitHub 的 Linux amd64 机器上构建后端。
4. 以完整 Git SHA 命名镜像，打包前端、镜像与所需 Compose 配置。
5. 通过 SSH 上传成品，调用服务器受限发布入口。
6. 检查公网 HTTPS、数据库、Redis 和前端版本。失败会将工作流标红。

同一个生产环境串行部署，不会同时更新两次；GitHub 的并发队列可能合并/取消中间的待运行任务，不保证每个连续推送都逐个上线。正在进行的发布不主动取消。

## 2. 服务器结构

```text
浏览器 HTTPS
    ↓
apt 安装的宿主机 Nginx（唯一公网入口）
    ├─ /web/ → /opt/fastapiadmin/current/web
    └─ /api/v1 → 127.0.0.1:8001 → 后端 Docker 容器
                                      ├─ MySQL 容器
                                      └─ Redis 容器
```

不会重新安装宝塔版 Nginx，也不启动基础 Compose 中的 Nginx 容器。

服务器只运行成品，不安装 Node/pnpm 来构建 Vue，不在服务器执行后端镜像构建。

## 3. 文件各自负责什么

| 文件                                 | 用途                                                      |
| ------------------------------------ | --------------------------------------------------------- |
| `.github/workflows/deploy.yml`       | master 触发、检查依赖、打包、SSH 发布、结果验证           |
| 已有三个 `*-ci.yml` / `secrets.yml`  | 继续做代码检查；增加 workflow_call 供发布调用             |
| `docker/docker-compose.ci.yaml`      | 覆盖基础 Compose 的低内存参数、固定持久化目录和服务器端口 |
| `docker/nginx/host-ci.conf.template` | apt Nginx 的 HTTPS、前端与接口配置                        |
| `scripts/ci_server.py`               | 服务器初始化、收取成品、备份、迁移、更新与健康验证        |

`scripts/ci_server.py` 作为管理工具安装到服务器 `/usr/local/sbin/fastapiadmin-ci`。更改这个受限入口自身后，需要管理员审核并更新服务器上的副本；普通业务、前端、Dockerfile、发布工作流和打包的 Compose/Nginx 模板随推送发布。

## 4. 服务器目录

```text
/opt/fastapiadmin/
  shared/
    server.env                 数据库/Redis 密码、JWT 和加密密钥（root 可读）
    credentials.txt            首次网页管理员口令（root 可读）
    sys_user.initial.json      随机口令哈希，默认只启用 super
    deployment.json            IP、证书位置
    mysql/ redis/              数据库与缓存持久化数据
    uploads/ files/            上传文件、私有附件
    last-success.json          最近成功发布的 SHA
  incoming/                    上传暂存，成功后删除对应包
  releases/<完整 Git SHA>/     每版前端与运行配置
  current -> releases/<SHA>    当前前端版本，使用符号链接切换
  previous -> releases/<SHA>   上一个成功切换的前端目录
  backups/                    发布前数据库、文件、配置、诊断日志
```

业务数据不放在发布目录中。更新源码不会覆盖 `shared/server.env`，不会重新生成口令，不会删除数据卷，不执行全局 Docker prune。

按脚本规则，保留最近约 3 个发布目录（当前/上一版额外受保护）和 5 份发布备份。首次部署也是独立新数据库，不复制本机数据和邮件授权码。

## 5. 首次服务器准备（不是每次发布都执行）

管理员需要先完成这些条件：

- Docker Compose 支持 `!override`（至少 2.24.4）；服务器 Python 至少 3.10。
- apt Nginx 正常；IP 证书已经签发且未过期。
- `10.255.178.0/24` 不与已有网络冲突，127.0.0.1:8001 不被其它服务使用。
- 在 `/usr/local/sbin/fastapiadmin-ci` 安装审核后的 `scripts/ci_server.py`，权限 755、root 所有。
- 准备仓库的 `backend/sql/sys_user.json` 公共种子文件，再以 root 执行一次：

```bash
python3 /usr/local/sbin/fastapiadmin-ci bootstrap \
  --host 154.37.219.196 \
  --certificate /etc/letsencrypt/live/ip-154-37-219-196 \
  --seed /管理员准备的路径/sys_user.json
```

上面的 seed 路径是占位符，不要原样粘贴。脚本生成新的服务器口令，真实值只写服务器，不输出到 GitHub。已有完整配置会保留；部分初始化或已有数据但没有配置时会拒绝覆盖，需要管理员核对。

已签发的证书与私钥继续留在 `/etc/letsencrypt/`，不提交 Git，也不复制进镜像。

初始化会把原来指向 `/www/server/nginx/html` 的证书校验路径改为 `/var/www/letsencrypt`，原续期配置备份在 backups。Nginx 的 80 端口放行 ACME 校验路径，证书续期成功后通过 deploy hook 检查并重新加载 Nginx。是否真正可以续期，仍应以 Certbot dry-run 结果为准，不能仅凭定时器存在就认定正常。

## 6. GitHub 配置

仓库 **Settings → Secrets and variables → Actions**：

| 类型     | 名称               | 含义                                       |
| -------- | ------------------ | ------------------------------------------ |
| Variable | DEPLOY_HOST        | 154.37.219.196                             |
| Variable | DEPLOY_PORT        | 22                                         |
| Variable | DEPLOY_USER        | root（使用专用受限密钥，不保存 root 密码） |
| Secret   | DEPLOY_SSH_KEY     | 仅供本仓库发布的 SSH 私钥                  |
| Secret   | DEPLOY_KNOWN_HOSTS | 已通过可信 SSH 通道核对的服务器主机公钥    |

私钥不要粘到聊天、工作流源码或提交记录里。

服务器 `authorized_keys` 中该公钥应有如下限制，不能把已有管理密钥删掉：

```text
restrict,command="/usr/local/sbin/fastapiadmin-ci" ssh-ed25519 <专用公钥> <备注>
```

`<专用公钥>` 是占位符。这个密钥只接受 `receive/deploy/status <完整 SHA>`，不能开交互 shell、转发端口或执行普通 SSH 命令。它仍具有更新应用的高权限；master 写权限也就是发布权限，不应给不可信人员。

生产环境应只允许 master 发布，不设置每次人工审批，满足自动部署目标。Actions 必须在仓库启用，且需要有可用的 GitHub 托管运行额度。

## 7. 发布失败怎样排查

| 失败位置                 | 第一排查点                                                          |
| ------------------------ | ------------------------------------------------------------------- |
| backend/frontend/secrets | 对应检查日志；发布未开始，不要去重启数据库                          |
| 构建镜像                 | Dockerfile 依赖、镜像仓库网络、构建日志                             |
| SSH 认证                 | 专用公钥是否安装、Secrets 是否匹配；不要关闭主机密钥校验            |
| 数据库备份               | 服务器磁盘、MySQL 健康与备份目录里的私有 deploy.log                 |
| 初始化/迁移              | 对应迁移脚本和私有日志；脚本不会自动清空数据库来重试                |
| 后端健康                 | `db_status`、`redis_status`、内存、容器状态                         |
| HTTPS                    | 证书有效期、IP SAN、Nginx 配置、防火墙                              |
| 前端版本不符             | `current` 链接、Nginx、CDN/浏览器缓存；不能把 HTTP 200 当作版本匹配 |

服务端日志在 `/opt/fastapiadmin/backups/<本次目录>/deploy.log`，不自动整段输出到公共 Actions 日志。

如果数据库迁移尚未开始就失败，脚本尝试恢复原后端运行；如果已经执行过迁移，不会擅自恢复数据库或假装旧镜像一定兼容。前端切换失败会恢复旧链接/旧 Nginx 配置。**这不是完整的数据库自动回滚方案。** MySQL 部分 DDL 可能不可事务回滚，需按备份人工恢复；本实现不代表已做过完整数据恢复演练。

发布过程中会暂停本项目后端，备份后再更新，是有维护窗口的单机发布，不是零停机。

## 8. 怎样确认实际发布了哪一版

本机：

```bash
git rev-parse HEAD
curl --fail https://154.37.219.196/web/version.json
curl --fail https://154.37.219.196/api/v1/monitor/health/check
```

版本 JSON 的 `sha` 应等于预期提交；健康接口应显示数据库与 Redis 都正常。这里只验证连通性与版本，不代替项目创建、审批、导出等业务验收。

服务器管理员只读检查：

```bash
readlink -f /opt/fastapiadmin/current
cat /opt/fastapiadmin/shared/last-success.json
docker ps --filter label=com.docker.compose.project=fastapiadmin
```

首次网页口令只在私人终端查看：`/opt/fastapiadmin/shared/credentials.txt`。它不会跟随网页改密自动更新；不要截图或公开这个文件。
