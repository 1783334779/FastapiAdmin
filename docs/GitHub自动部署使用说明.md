# master 推送自动部署

本仓库的发布入口是 `.github/workflows/deploy.yml`。本文件说明实现，不表示任意一次工作流都已成功；每次发布结果以 GitHub Actions 与线上版本号为准。

## 1. 以后怎样发布

只提交你确认需要发布的源文件，然后执行：

```bash
git push origin master
```

本地 `git commit` 本身不会发布。推送到其它分支不会部署生产服务器。

进入 GitHub 仓库的 **Actions → Deploy master**，查看本次执行。也可以在该工作流点击 **Run workflow**，选择 master 手动重试。

优化后的工作流依次执行：

1. 用受限 SSH 的 `baseline <SHA>` 读取服务器**实际成功发布**的版本，核对正在运行的后端镜像和健康状态。
2. 对比这个版本到本次提交的全部变更，生成发布计划。不是只比较上一个提交，避免遗漏前一次发布失败的内容。
3. 执行对应组件的检查、密钥扫描。需要更新 Web 才构建 Web，需要更新后端才跑后端检查；任一必要检查失败，不发布。master 不再另外重复触发独立的前后端和密钥扫描工作流，PR 检查保留。
4. 后端变化时，在 GitHub 构建 Linux amd64 镜像并推送私有 GHCR，使用 Buildx 跨次构建缓存。不会在这台小内存服务器上编译。
5. SSH 只上传前端成品（需要时）及少量运行配置、发布清单，不再夹带 `backend-image.tar`。镜像使用 `ghcr.io/1783334779/fastapiadmin-backend@sha256:...` 锁定，不依赖可变的 latest。
6. 服务器校验发布基准没变。仅前端更新时保留全部后端服务；后端更新时按 digest 拉取缺少的镜像层，备份、迁移、更新后端。镜像拉取在停止旧后端**之前**执行。
7. 原子切换前端目录；仅 Nginx 配置改变时才重载。检查公网 HTTPS、数据库、Redis、前端版本和实际后端镜像。

| 变更 | 自动发布行为 |
| --- | --- |
| 仅 `frontend/web/` | 构建、检查并更新 Web；不构建后端、不重启后端、不执行数据库备份和迁移 |
| 仅 `backend/` | 检查后端、构建/推送镜像、拉取变化层、备份迁移及更新后端；复用线上 Web |
| 前后端都变 | 同一次发布处理两端；仍不是零停机部署 |
| 仅 `frontend/app/` | 检查 App；这台服务器不部署 App，不更新 Web/后端 |
| 仅 `docs/` 或指定 README/LICENSE/AGENTS | 密钥扫描，不发布；线上 SHA 不前进是正常的 |
| Docker/工作流/共享工具或未分类文件 | 保守执行完整发布 |

首次升级到此协议、线上基准不在当前 Git 历史时执行完整发布。无法验证线上健康/镜像状态、或计划生成后基准改变时，停止并提示重跑，而不是盲目覆盖。默认基准只读检查失败不降级绕过。

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
| `.github/workflows/deploy.yml`       | master 触发、识别变更、按需检查、私有 GHCR 构建、发布、验证 |
| 已有三个 `*-ci.yml` / `secrets.yml`  | 继续做代码检查；增加 workflow_call 供发布调用             |
| `docker/docker-compose.ci.yaml`      | 覆盖基础 Compose 的低内存参数、固定持久化目录和服务器端口 |
| `docker/nginx/host-ci.conf.template` | apt Nginx 的 HTTPS、前端与接口配置                        |
| `scripts/ci_server.py`               | 服务器初始化、收取成品、备份、迁移、更新与健康验证        |
| `scripts/ci_release.py`              | 对比线上成功版本、生成组件发布计划、打包小发布包          |
| `scripts/ci_ssh.sh`                  | 临时准备专用 SSH 密钥、严格核对主机公钥、传递受限命令     |

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
    last-success.json          最近成功发布的 SHA、两端 SHA、后端镜像 digest
  incoming/                    上传暂存，成功后删除对应包
  releases/<完整 Git SHA>/     每版前端与运行配置
  current -> releases/<SHA>    当前前端版本，使用符号链接切换
  previous -> releases/<SHA>   上一个成功切换的前端目录
  backups/                    发布前数据库、文件、配置、诊断日志
```

业务数据不放在发布目录中。更新源码不会覆盖 `shared/server.env`，不会重新生成口令，不会删除数据卷，不执行全局 Docker prune。

按脚本规则，保留最近约 3 个发布目录（当前/上一版额外受保护）、5 份数据库发布备份和另 5 份仅前端发布日志。连续发布前端不会挤掉数据库备份。共享同一后端镜像的保留版本会保护该镜像，不按“前端 SHA”错误删除后端。首次部署也是独立新数据库，不复制本机数据和邮件授权码。

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

`<专用公钥>` 是占位符。这个密钥只接受 `baseline/receive/deploy/status <完整 SHA>`，不能开交互 shell、转发端口或执行普通 SSH 命令。它仍具有更新应用的高权限；master 写权限也就是发布权限，不应给不可信人员。

### 私有 GHCR 的权限与临时凭据

镜像包名为 `ghcr.io/1783334779/fastapiadmin-backend`，已由管理员核对为私有，并关联本仓库的 Actions 访问权限。工作流推送前必须确认包已经存在且私有；包不存在、无权读取或可见性不是 private 时都停止，不能仅凭文档中“默认私有”的描述就上传业务镜像。推送后再次检查。镜像通过 OCI source 标签关联仓库。

迁移到另一账号/新包名时，管理员应先用不含业务代码和凭据的最小占位镜像准备包，在 Package settings 核对为 Private、授权对应仓库 Actions 访问，再启用业务镜像发布。不要为通过检查把镜像公开，也不要把管理员长期令牌放进普通发布脚本。

- 构建任务：本任务的 `GITHUB_TOKEN` 具备 `packages: write`。
- 发布任务：**另一份**本任务的 `GITHUB_TOKEN` 仅具备 `packages: read`，通过已经验证主机公钥的 SSH 标准输入传给服务器。
- 服务器：只在后端更新时读取这个临时令牌，用 0700 临时目录进行 `docker login --password-stdin` 和 pull；无论成功失败都清理目录。令牌不进入发布包、业务环境文件、命令参数或仓库。不保存长期 PAT，不要求用户提供新的密码。
- 同仓库的 Actions 必须拥有该私有包的访问权；已有包未关联仓库时，需要管理员在包设置中授权，而不是改为公开。
- Actions 缓存用于减少重复构建；Docker 分层拉取用于减少服务器下载。缓存缺失、基础镜像/依赖变化、旧层已清理时仍会下载较多数据。

不能保证永远免费或固定几分钟。私有包存储、Actions 额度受账号配额影响，实际以账号计费设置为准；保留的 SHA 标签/缓存应定期审核，禁止为省空间无差别删除正在运行或回退所需的镜像。

生产环境应只允许 master 发布，不设置每次人工审批，满足自动部署目标。Actions 必须在仓库启用，且需要有可用的 GitHub 托管运行额度。

## 7. 发布失败怎样排查

| 失败位置                 | 第一排查点                                                          |
| ------------------------ | ------------------------------------------------------------------- |
| backend/frontend/secrets | 对应检查日志；发布未开始，不要去重启数据库                          |
| 构建镜像                 | Dockerfile 依赖、镜像仓库网络、构建日志                             |
| 读取线上基准             | 服务器当前链接/last-success/运行镜像是否一致，线上是否健康；不要直接绕过 |
| 推送/拉取私有 GHCR       | 包是否私有且关联本仓库、Actions 包访问权、临时令牌权限和 GHCR 网络    |
| SSH 认证                 | 专用公钥是否安装、Secrets 是否匹配；不要关闭主机密钥校验            |
| 数据库备份               | 服务器磁盘、MySQL 健康与备份目录里的私有 deploy.log                 |
| 初始化/迁移              | 对应迁移脚本和私有日志；脚本不会自动清空数据库来重试                |
| 后端健康                 | `db_status`、`redis_status`、内存、容器状态                         |
| HTTPS                    | 证书有效期、IP SAN、Nginx 配置、防火墙                              |
| 前端版本不符             | `current` 链接、Nginx、CDN/浏览器缓存；不能把 HTTP 200 当作版本匹配 |

服务端日志在 `/opt/fastapiadmin/backups/<本次目录>/deploy.log`，不自动整段输出到公共 Actions 日志。

如果数据库迁移尚未开始就失败，脚本尝试恢复原后端运行；如果已经执行过迁移，不会擅自恢复数据库或假装旧镜像一定兼容。前端切换失败会恢复旧链接/旧 Nginx 配置。**这不是完整的数据库自动回滚方案。** MySQL 部分 DDL 可能不可事务回滚，需按备份人工恢复；本实现不代表已做过完整数据恢复演练。

**仅后端更新**会暂停本项目后端，备份后再更新，是有维护窗口的单机发布，不是零停机。仅前端发布不停止后端。首次切换 GHCR 需要建立镜像/缓存，不能拿第一次的耗时当作后续缓存命中后的耗时。

## 8. 怎样确认实际发布了哪一版

本机：

```bash
git rev-parse HEAD
curl --fail https://154.37.219.196/web/version.json
curl --fail https://154.37.219.196/api/v1/monitor/health/check
```

版本 JSON 的 `sha` 是整次发布提交，应等于预期需要部署的提交；`frontend_sha` 是 Web 成品来源，`backend_sha` 是后端镜像来源。只改前端时 backend_sha 不变是正确的，不要要求三个 SHA 永远相等。仅文档或 App 的提交不更新这台服务器版本。健康接口应显示数据库与 Redis 都正常。这里只验证连通性与版本，不代替项目创建、审批、导出等业务验收。

服务器管理员只读检查：

```bash
readlink -f /opt/fastapiadmin/current
cat /opt/fastapiadmin/shared/last-success.json
docker ps --filter label=com.docker.compose.project=fastapiadmin
```

首次网页口令只在私人终端查看：`/opt/fastapiadmin/shared/credentials.txt`。它不会跟随网页改密自动更新；不要截图或公开这个文件。

## 9. 如何确认优化是否生效

1. 改一个 Web 表头并推送：计划应为 frontend=true/backend=false；后端检查、镜像构建任务显示 skipped（不是失败），只有本次前端成品上传。服务器后端容器 ID/StartedAt 应保持不变，无本次 mysql.sql.gz。
2. 改后端代码并推送：计划应为 frontend=false/backend=true；Web 构建 skipped，frontend_sha 保持原值。构建日志可观察 CACHED，服务器 pull 日志可观察 Already exists；实际传输取决于层是否相同。
3. 只改 docs：检查后 publish skipped，页面不变化是预期。
4. Actions 的上传步骤显示 SSH bundle 字节数、SSH 上传秒数、服务器部署秒数。每次成功还会核对公网版本和运行容器的实际镜像 ID，不只看“构建通过”。

旧协议仍兼容，用于不中断切换时已在运行的旧工作流；新发布不再生成/上传镜像 tar。升级服务器管理脚本前，先保存现有脚本，在同一 deploy.lock 锁下原子替换并验证 Python 3.10 语法，不覆盖口令和业务数据。后续若要退回旧协议，需要同时审核管理脚本、工作流、Compose 和发布清单，不能只回退一个文件。

### 本次接入遇到的真实问题

第一次 GHCR 推送后，包实际显示 Public，与预期不符；后置私有性检查失败，服务器发布任务被跳过，线上仍运行旧版。已通过账号登录的 Package settings 将该包收紧为 Private，并核对本仓库 Actions 访问权限。公开状态出现的具体原因尚未确定，不能推断为 GHCR 的通用默认行为。为避免再次依赖默认值，前置检查改为必须存在已确认的私有包；404 不再放行。构建上下文排除了真实 .env、上传数据和私有附件，服务器独立口令也从未打入镜像；这不等于可以忽略镜像可见性检查。

参考：[Docker 构建缓存](https://docs.docker.com/build/ci/github-actions/cache/)、[GHCR 访问和权限](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。本文描述实现规则；具体提速幅度必须看实际发布记录，不预先保证耗时。
