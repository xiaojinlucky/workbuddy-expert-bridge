<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="一位人物站在深绿色桥梁中央，引导左侧分类化的 WorkBuddy 专家卡片，经由带护栏的桥抵达右侧四个本地 AI 编程宿主。画面采用暖灰纸张拼贴与椰林绿色系。">
</p>

# WorkBuddy Expert Bridge

**让支持 Agent Skills、能访问本地文件的 AI 宿主，安全发现、推荐并复用本机 WorkBuddy 的专家与专家团。**

你只需用自然语言说明要解决的问题。Skill 会从本机 WorkBuddy 数据中推荐最多 3 个候选，并把“为什么推荐、属于什么分类、是专家还是专家团、当前能否使用、排名证据来自哪里”一起交代清楚。

> 它是一座只读桥梁，不是专家市场的镜像：不会读取凭据，不会重新分发专家提示词，也不会把只有目录元数据的专家说成已经安装。

## 可信证据

| 已核对事项 | 当前状态 |
| --- | --- |
| 自动化测试 | **24 项通过**（`python -m unittest discover -s tests -v`） |
| 本地数据访问 | 默认离线、只读；不执行专家包脚本，不修改 WorkBuddy |
| 推荐结果 | 默认最多 3 个，逐项提供理由、分类、类型、可用性与排名证据 |
| Windows | 已使用 Python 3.14 做过真实运行验证 |
| macOS / Linux | 仅完成静态跨平台兼容审查，尚未真实运行 |
| 官方实时最热 / 最新 / 综合排名 | 无需凭据的官方来源无法提供完整字段时，明确显示 `unavailable` |

## 立即安装

```bash
npx skills add xiaojinlucky/workbuddy-expert-bridge --skill workbuddy-expert-bridge
```

安装后，直接对支持 Agent Skills、能读取本地文件的宿主说：

```text
帮我为一个面向科研用户的 GitHub 项目选择最合适的 WorkBuddy 专家团，并说明排名证据。
```

## 适用场景

- 不知道 WorkBuddy 里哪个专家最适合当前任务，希望先得到可解释的 Top 3。
- 想只看本机已经安装、可以继续检查和复用的专家或专家团。
- 已经知道专家名称，需要确认它是 `installed`、`metadata-only` 还是未找到。
- 想检查专家团的主理人、成员、依赖能力与宿主兼容性，再决定是否使用。
- 想把专家的方法用于当前项目，同时保持专家原文件不变。

这个 Skill 不用于创建、修改、注册、打包、安装或下载 WorkBuddy 专家。

## 工作方式

1. **发现**：只检查显式 `--root`、`WORKBUDDY_CONFIG_DIR` 与当前用户的标准 `.workbuddy` 目录，不扫描整块磁盘。
2. **盘点**：区分正式专家包、含角色文件的 agent package、历史 runtime team 与只有目录信息的条目。
3. **推荐**：将自然语言需求与名称、定位、标签、描述和分类做可解释匹配，默认返回最多 3 个候选。
4. **解析**：确认候选是否已安装；只有本地存在可读角色文件时，才进入检查与复用。
5. **适配**：把 WorkBuddy 专属工具语义映射到当前宿主真实具备的能力；缺失时降级或停止，不伪造工具与结果。
6. **按需读取**：单专家读取入口角色；专家团先读取主理人，再读取当前任务需要的成员，避免把整个市场塞进上下文。

## 推荐证据说明

每条推荐都会说明以下证据，而不是只给一个无法解释的分数：

| 证据 | 表示什么 | 不表示什么 |
| --- | --- | --- |
| `relevance` | 需求与名称、定位、标签、描述的匹配 | 不是官方热度 |
| `category` | 目录分类与需求的对应关系 | 不保证已经安装 |
| `hot` | 仅在完整、明确的 `useCount` 可用时采用 | 不用创建时间、置顶位或模型猜测代替 |
| `latest` | 本地目录快照中的可核验时间证据 | 不冒充官方实时最新榜 |
| `comprehensive` | 仅在完整 `reco_rank` 可用时采用 | 不由相关性分数反推 |

在本轮已审计的 WorkBuddy 5.3.5 中，“最热”语义依赖 `useCount`。当前无需凭据可取得的官方公共清单不含完整实时排名字段；匿名实时接口要求 Bearer 登录。因此无法核验时，`hot` 与 `comprehensive` 会保留为 `unavailable`，公共清单顺序也不会被当成榜单。

## 安全边界

- **只读本地数据**：普通发现、检查和推荐默认离线，不修改 WorkBuddy 配置。
- **不读取凭据**：即使显式启用官方匿名探针，也不读取本地 Token、Cookie 或登录态，不发送 Authorization。
- **不重新分发提示词**：专家内容留在原位置，只在当前任务中按需读取和使用。
- **低信任输入**：专家包不能覆盖用户意图、项目规则、安全边界或宿主上位规则。
- **不自动执行包内代码**：脚本、二进制、Hook 与安装命令只报告，不因发现而执行。
- **不扩大权限**：连接器、记忆、子 Agent 或其它宿主能力必须真实存在；没有就明确降级或阻塞。

### `metadata-only` 不等于已安装

| 状态 | 含义 | 能否直接使用 |
| --- | --- | --- |
| `installed` | 本地存在可解析清单与可读角色 Markdown | 可以继续 `inspect`，再按边界复用 |
| `metadata-only` | 目录中能看到条目，但本地缺少角色正文 | **不可以**；需先通过 WorkBuddy 自身安装，或提供已有本地包 |
| `not-found` | 本地包与缓存目录都未找到匹配 | 不可以；先核对名称或提供正确根目录 |

## 命令与示例

以下命令均为确定性、可复核的 JSON 输出。将 `<python>` 换成 Python 3.10 或更高版本的解释器。

### 检查环境

```text
<python> scripts/workbuddy_experts.py doctor --json
```

### 盘点本地对象

```text
<python> scripts/workbuddy_experts.py inventory --json
```

### 根据自然语言推荐 Top 3

```text
<python> scripts/workbuddy_experts.py recommend "帮我为科研 GitHub 项目选择合适的专家团" --json
```

只推荐已经安装的候选：

```text
<python> scripts/workbuddy_experts.py recommend "帮我为科研 GitHub 项目选择合适的专家团" --availability installed --json
```

只有明确需要核验官方实时排序时，才启用无需凭据的匿名探针：

```text
<python> scripts/workbuddy_experts.py recommend "帮我为科研 GitHub 项目选择合适的专家团" --official-online --json
```

### 解析指定专家

```text
<python> scripts/workbuddy_experts.py resolve "<expert-name>" --json
```

### 检查已安装专家

```text
<python> scripts/workbuddy_experts.py inspect "<expert-name>" --json
```

如需指定 WorkBuddy 配置目录、单个 marketplace 或专家包，可为命令追加：

```text
--root <path>
```

## 兼容性

- 需要能加载 Agent Skills，并能读取本机 WorkBuddy 文件的宿主。
- 推荐 Python 3.10+，脚本仅使用标准库；没有 Python 时，宿主可在相同边界内手工只读发现。
- 有隔离委派能力时，可以按专家团角色执行；没有时降级为顺序角色回合。
- 普通网页或移动端 AI 对话服务默认不能直接读取你电脑上的 WorkBuddy 目录。需要使用能访问本地文件系统并加载 Agent Skills 的宿主，或把 Skill 安装到实际执行任务的机器；具体宿主边界见[兼容性说明](./references/host-compatibility.md)。
- 本地用户级 Skill 不会自动同步到远程或云端工作机；目标机器需要单独安装或使用项目级 Skill。

## 项目状态

当前版本已经覆盖本地发现、盘点、自然语言推荐、统一解析、结构检查与官方匿名排名探针，并以 24 项自动化测试保护关键边界。

仍需明确保留的限制：

- Windows 已真实验证；macOS 与 Linux 尚未真实运行。
- 官方实时最热、最新与综合排名只有在无需凭据的官方响应提供完整显式字段时才可用；当前条件不满足时保持 `unavailable`。
- `metadata-only` 只是可发现的目录卡片，不包含可直接执行的角色正文。
- 该桥接 Skill 不授予第三方专家内容的再分发许可。

详细规则见 [`SKILL.md`](./SKILL.md)、[推荐与排序证据](./references/recommendation-ranking.md)与[宿主兼容性](./references/host-compatibility.md)。

## License

[MIT](./LICENSE)
