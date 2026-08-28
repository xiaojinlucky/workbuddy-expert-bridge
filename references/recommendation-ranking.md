# 推荐与排序证据

本页记录 `recommend` 的事实来源、可用范围和诚实边界。它不是对 WorkBuddy 服务端协议的长期承诺；应用升级后若字段或行为改变，应重新只读取证并更新本页。

## 2026-08-28 本机与官方匿名取证

- WorkBuddy 文件版本与渲染版本：`5.3.5`。
- 已安装应用资源：`D:\WorkBuddy\resources\app.asar`，SHA-256 `402A8A42C04D7806595BB19EE2D3C535E46899189E344CA4950BFCB56406E070`。
- 本地专家目录：`~/.workbuddy/app/cache/experts/manifest.json`，SHA-256 `3D0DC960039560668D888760E673962563209C44BE03AC188DD73FFC29A9E239`。
- 目录快照包含 442 个专家、15 个分类；442 条都有 `createdAt`，9 条有 `displayPosition`，没有条目提供 `useCount/use_count` 或 `reco_rank`。
- 已安装应用内置的公共目录对象为 [`expert_center.json`](https://acc-1258344699.cos.accelerate.myqcloud.com/workbuddy/expert-marketplace/expert_center.json)。2026-08-28 匿名读取返回 `200`、423 个公开专家、15 个分类，但 `use_count`、`reco_rank`、`published_at` 的有效覆盖均为 0。它是公共目录快照，不是实时排名。
- WorkBuddy 官方专家页 [`/agents/experts`](https://www.workbuddy.cn/agents/experts) 的匿名 HTML 没有内嵌专家排名结果或可复用的实时字段。官方[更新日志](https://www.workbuddy.cn/docs/workbuddy/Changelog)确认产品存在专家中心排名和热门专家排行，但不表示榜单数据可以匿名导出。
- 已检查标准专家缓存、应用数据目录和文本日志，没有找到可复用的本地 `/console/expert/ranking` 响应或完整热度表。没有读取或导出 Cookie、令牌、浏览器存储及其它凭据。

## 官方匿名接口结果

安装包中的第一方客户端实现给出了真实接口和排序字段。`--official-online` 用固定来源做无凭据探针，2026-08-28 的结果如下：

| 来源 | 匿名结果 | 可用于实时排名 |
|---|---:|---|
| 公共目录 `expert_center.json` | `200`，423 条；排名字段覆盖 0 | 否，仅目录快照 |
| `GET https://copilot.tencent.com/console/expert/ranking?limit=500` | `401`，`WWW-Authenticate: Bearer` | 否 |
| `POST https://copilot.tencent.com/portal/operation-platform/market/expert/list`，`sort_by=use_count` | `401` | 否 |
| 同一列表接口，`sort_by=reco_rank|published_at` | 共用的匿名认证门槛 | 否 |

探针不读取本地凭据，不发送 `Authorization` 或 Cookie，禁用环境代理，不跟随跨地址重定向。遇到共同的 Bearer 认证门槛后可以停止重复请求其它排序字段，但必须把跳过项和原因写入证据。`401/403`、非 JSON、部分字段或只覆盖部分候选都不能升级为可用排名。

## WorkBuddy 真实排序语义

以下行为来自本机 `app.asar` 内已安装渲染代码，不是根据界面名称猜测：

| UI 排序 | 请求字段 | 方向 | 其它行为 |
|---|---|---|---|
| 综合 | `reco_rank` | 降序 | 服务端推荐秩；本地目录未提供 |
| 最热 | `use_count` | 降序 | 以 `useCount` 为热度；`displayPosition` 可固定运营位 |
| 最新 | `published_at` | 降序 | 本地目录只提供可核验的 `createdAt` 快照字段 |

代码路径与职责：

- `renderer/assets/colleague-chat-page-Cv5TTxHj.js`：`sortBuiltinByPopularity` 先处理 `displayPosition`，其余按 `useCount` 降序；`resolveUseCountMap` 优先使用列表返回值，缺失时请求排名。
- `renderer/assets/common-BWvXPHiV.js`：排名请求是 `GET /console/expert/ranking`，返回项包含归一化使用次数。
- `renderer/assets/connector-5116UCMY.js`：个人用户专家中心通过市场列表接口读取数据，把综合、最热、最新分别映射为 `reco_rank`、`use_count`、`published_at`；专家与专家团分别带 `expertType=agent|team`，分类按 `categoryId` 过滤。

`displayPosition` 是运营置顶位置，不是人气数。只看到置顶位、创建时间或界面顺序，都不足以声称某专家“最热”。

## `recommend` 怎样使用这些证据

1. 先用需求词对名称、专业定位、标签、描述和分类做可解释相关性评分。
2. 明确的 `agent|team` 意图和 `installed` 状态只作有限调整；不会让完全不相关的本地包压过高相关候选。
3. 分类来自 `expert.categoryId` 与同一快照的 `categories` 连接。
4. 只有候选全集拥有完整、显式的 `useCount` 时，热度才可作为次级排序证据。当前本机结果必须为 `hot.status=unavailable`。
5. `createdAt/publishedAt` 可作为本地快照的最新证据和同分次序，但不得改名为热度或实时最新榜。
6. `reco_rank` 不完整时，综合排序必须为 `unavailable`，不得由相关性分数反推。
7. 用户明确要求实时官方核验时才启用 `--official-online`。公共快照与实时接口分开报告；只有官方实时响应对本地候选提供完整、显式字段时才允许合并。匿名接口要求登录时继续保持 `unavailable`，不得读取凭据或从 UI 卡片顺序推断。

每个候选都保留字段命中、分数、分类连接、时间字段、热度状态和本地包路径。这样其它宿主可以复核“为什么推荐”，也能分清“目录里能看到”和“本地已经能执行”。
