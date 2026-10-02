# Bug Hunt：HTTP 边界、缓存与项目修改

日期：2026-10-02。范围：server/app.py 的 HTTP/auth/资源访问路径、新增 http_security.py、隔离测试与 Nginx 示例。未读取 .env 内容、未访问真实数据库、未对公网压力测试。保留本轮开始前的内容质量改动。

## 修复按严重度排序

| 级别 | 问题 | 复现与证据 | 根因 | 修复 |
|---|---|---|---|---|
| 高 | 无界连接/慢连接占线程 | 新增隔离测试占满 1 个测试连接，第二请求应 503；慢头达到截止时间应释放 | 初始提交 37a0c6e 直接 ThreadingHTTPServer，无 read timeout/并发预算 | BoundedHTTPServer 默认 64 槽；15 秒接收绝对截止；32 KiB 请求头；服务繁忙 Retry-After |
| 高 | 演示注册绕过任何额度限制 | 修复前连续 31 次 demo 请求均 200（替换 new_user 防止测试造库）；测试预期最后 429 | 37a0c6e demo 路由早于认证限流，IP 字典也无锁/不回收 | 提前 IP 限流、邮箱/账户/昂贵操作独立额度，令牌表上限/空闲清理 |
| 高 | HTTP framing 模糊 | 重复 Content-Length、同时 Transfer-Encoding 请求修复前均 200，修复后 400 | 手动只读取第一个 Content-Length，未拒绝不支持的编码 | 同一入口校验 Host、长度、编码、正文类型 |
| 中 | 跨站请求缺少第二层校验 | text/plain 写入和无 Origin 但 Sec-Fetch-Site:cross-site 的写入修复前均 200 | 只在 Origin 存在时比较 netloc，忽略 scheme、Fetch Metadata、Content-Type | 浏览器跨站拒绝、严格 JSON、配置 PUBLIC_ORIGIN 验证 Host |
| 中 | 静态资源每次重传 | 修复前 app.js 没 ETag，Cache-Control:no-store；修复后第二次条件请求 304 零正文 | 37a0c6e send() 统一 no-store | 公开文件有界缓存 + 内容 ETag/revalidation；API/导出继续 private no-store |
| 中 | 无法修改项目名称/介绍 | 根代理浏览器复现：项目管理只能创建/选择；后端无修改 API | 功能缺口；创建时还会静默截断名称/介绍 | 新 PATCH /api/projects/{id}，所有权校验，1–100 字名称、0–2000 字介绍，创建同合同 |

## 调查与验证过程

- Pass 1：读取 HTTP/auth/admin/export 全路径、追踪请求→解析→认证→项目所有权→任务提交，git blame 确认主要 HTTP 问题源于 37a0c6e；原注册白名单逻辑来自 62ad318。六条最小 HTTP 回归测试先全部失败：缺 ETag、模糊长度、编码、跨站、表单类型、demo 限流。
- Pass 2：实施后六条转绿，再补充独立内存缓存失效/有界、并发令牌原子性、代理头伪造、超大头/深层 JSON、慢连接占槽释放、固定域名/来源、项目跨账户拒绝，共 13 条通过。复读发现令牌时间应在锁内读取，已修正，避免并发时间倒序。
- Pass 3：最初全套 133 项中 HTTP/既有用例通过，另一个并行修改范围内的 3 个新适配器负例仍失败；交由对应代理修复，未掩盖失败。最终全套由根代理汇总。
- Pass 4：复读新模块、HTTP 异常分支、全部变更 diff；py_compile 和 git diff --check 通过。304 不发不正确的 Content-Length:0；HEAD 不返回正文；解析错误也不缓存。慢连接测试从饱和到恢复，未遗留服务线程。

## 已验证的边界 / 剩余事项

- 静态路径已有 resolve/is_relative_to 防目录穿越，未发现跨租户读取；项目修改补充成功持久化与他人 404 验证。
- 没有缓存私有 API，也没有按 User-Agent 拉黑正常用户；未新增验证码操作。
- 限流单进程，重启清空，不是分布式防火墙。未部署 Nginx；本地没有 nginx，语法验证需要运维 `nginx -t`。多 IP、带宽洪泛、大量合法注册及磁盘增长仍需 CDN/WAF/入口账户验证/监控。见 deploy/HTTP防护与部署.md。
- 深度模糊测试/属性测试、SMTP 与完整支付系统不在本 HTTP 子任务范围；没有宣称完成线上 DDoS 演练。外部连接负例由任务/适配器子任务负责。
- 假设验证失败次数 0：初始 6 个失败用例是确认真实缺陷，不是错误假设；全套并行测试的中间失败已明确保留日志。

## 最终回归补记

适配器子任务修复后，全套 `python3 -m unittest discover -s tests -v`：150 项通过（27.468 秒）。随后接入 TaskAdmissionError 的 429/503/409 与 Retry-After，新增一个三分支 HTTP 用例，HTTP 子套件增至 14 项全部通过（5.950 秒）；最终联合计数由根代理的合并门禁记录。再次 py_compile、git diff --check 均通过，最后两轮复读无新增高/中风险发现。
