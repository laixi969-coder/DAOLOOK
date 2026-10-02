# HTTP 缓存与滥用防护

这些配置是运维工作，不展示给普通用户。本次只提供配置示例，未改动线上服务器、DNS、证书或防火墙。

## 已落地

- 静态 HTML、JS、CSS 使用内容 SHA-256 ETag 和 `public, no-cache`：浏览器可以保留文件，每次确认是否更新，未变返回 304。没有给无版本文件长时间 immutable，发布后不会继续使用过期页面。进程内静态缓存最多 8 MiB / 64 项，文件改变自动失效。
- API、错误、下载默认 `private, no-store`，不跨用户共享缓存。
- HTTP 同时连接默认最多 64 个，额外连接返回 503 和 Retry-After。请求头/正文接收有 15 秒绝对截止时间；总请求头上限 32 KiB、URL 8 KiB、JSON 请求体 3,000,000 字节（保留 2 MB 文件经 base64 上传的余量）。拒绝重复 Content-Length、Transfer-Encoding、非 JSON 写请求、深度异常 JSON。
- 线程安全 token bucket：每 IP 所有请求容量 1200/分钟、API 900/分钟，登录/注册/验证码/找回合计 15/分钟、演示账户 30/分钟；另有邮箱维度 15/分钟、已登录账户 600/分钟、写操作 120/分钟、昂贵操作账户 30/分钟 + IP 120/分钟。容量按时间连续恢复，返回 429 和准确 Retry-After，不自动重试扣费写操作。
- 限流身份表最多 20,000 项；空闲 10 分钟清理。表满时拒绝新身份，不淘汰正在被限制的身份来放行攻击。此限制在单进程内生效，重启会清空。
- SameSite=Strict Cookie、Origin 协议/域名核对、Sec-Fetch-Site 校验、JSON Content-Type 共同保护写操作；公网部署用固定来源校验 Host，阻止伪造域名。普通非浏览器客户端可不发 Origin。
- 不依赖 User-Agent 黑名单，不用验证码阻碍每个正常用户。主要保护成本入口、私有内容读取和注册入口；不能阻止已有合法账号把自己可见的内容保存。

## 上线配置

复制并按实际域名/证书修改 [nginx.conf.example](./nginx.conf.example)，先执行 `nginx -t` 再 reload。本环境没有 nginx，配置尚未执行语法验证，也未部署。

给应用设置（示例值需替换）：

```dotenv
HOST=127.0.0.1
PORT=8000
DAOLOOK_PUBLIC_ORIGIN=https://daolook.example
DAOLOOK_SECURE_COOKIE=1
DAOLOOK_TRUSTED_PROXIES=127.0.0.1/32
DAOLOOK_HTTP_CONNECTIONS=64
```

代理必须覆盖 `X-Real-IP`，不要透传客户端传入的原值。应用只信任显式网段内代理发来的单个 X-Real-IP；默认完全不信任代理头。不要设 0.0.0.0/0。若前面还有 CDN，应先在 Nginx 配置 CDN 官方公布的可信出口和真实 IP 模块，否则所有用户会按 CDN 出口共享额度。必须在防火墙阻止直接访问源站端口。

没有配置 PUBLIC_ORIGIN 时维持开发/现有代理兼容，仅验证 Host 语法并按 Cookie HTTPS 配置核对来源协议。公网必须配置真实 HTTPS 来源；本地 HTTP 测试不设置 Secure Cookie。PUBLIC_ORIGIN 设置后内部健康检查必须发送匹配 Host。

## 边界与后续

这不是“已具备 DDoS 清洗”的承诺。应用限流和有界线程保护单机资源，挡不住带宽耗尽、分布式多 IP 洪泛、源站绕过或大量合法注册积累的磁盘增长。公网必须使用 CDN/WAF/云 DDoS 防护、源站防火墙及监控告警；验证真实付费需求后再接入账号验证/付费额度，不能把赠送积分当作公共免费算力。

保留标准库 HTTP 服务的轻量架构；[Python 官方明确不建议将 http.server 直接用于生产](https://docs.python.org/3/library/http.server.html)。公网必须在受管理反向代理后运行，后续多实例应迁移生产服务器和共享 Redis 限流，当前不能声明跨实例全局限流。[Nginx 限流模块](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html) 可按 IP 限制请求处理速率，配置需结合真实 NAT/企业用户访问分布调参。

监控至少记录 429/503 比例、请求耗时、活跃连接、任务积压、失败退款、磁盘空间。当前应用未新增用户行为分析或外部日志上传。
