# workbuddy-expert-bridge

## 有什么用

让支持 Agent Skills 的 AI 编程宿主直接使用本机 WorkBuddy 专家、专家团和包含角色提示词的插件包。它会只读发现本地对象、解析角色和依赖、把 WorkBuddy 专属工具语义转换为宿主现有能力，再执行真实任务。

它解决三类常见失败：手工寻找提示词、把整套市场塞入上下文、以及照搬 `SendMessage`、连接器或记忆工具等宿主专属指令。专家内容仍留在原位置，不会被复制进本 Skill。

## 安装

用户级安装目录：

```text
~/.agents/skills/workbuddy-expert-bridge/
```

项目级安装目录：

```text
<project>/.agents/skills/workbuddy-expert-bridge/
```

把仓库地址直接交给支持 Agent Skills 的 Agent：

```text
请帮我安装这个 Skill：https://github.com/xiaojinlucky/workbuddy-expert-bridge
```

也可以使用 Skills CLI：

```bash
npx skills add xiaojinlucky/workbuddy-expert-bridge --skill workbuddy-expert-bridge
```

## 配置

通常不需要配置。脚本依次检查：

1. 命令行 `--root` 指定的目录；
2. `WORKBUDDY_CONFIG_DIR` 环境变量；
3. 当前用户目录下的 `.workbuddy`。

`--root` 可以指向 WorkBuddy 配置目录、`plugins/marketplaces`、单个 marketplace 或单个专家包。Skill 不需要密钥。

## 使用

自然语言示例：

- “列出我本机可用的 WorkBuddy 专家团。”
- “我想运营小红书并持续涨粉，推荐最合适的 WorkBuddy 专家或专家团。”
- “用 WorkBuddy 的 MVP 开发专家团完成这个需求。”
- “检查一人公司专家团依赖了哪些宿主能力。”
- “把这个 WorkBuddy 专家的方法用于当前项目，但不要修改专家原文件。”

盘点结果会区分：正式专家包、未声明专家类型但含角色文件的 agent package、历史 runtime team，以及只有目录元数据的 `metadata-only` 条目。默认只给计数和有界样例，不展开数百条缓存目录。

指定专家时，Skill 会先同时解析本地包和缓存目录。若缓存里有名称但本地没有角色提示词，它会停止执行，说明缺少的文件，并明确给出一条可执行恢复动作：通过 WorkBuddy 自身安装或提供已经存在的本地包后重新解析；不会自行下载。

开放式需求使用 `recommend`，默认返回 Top 3，并逐项给出推荐理由、分类、专家/专家团类型、本地可用性，以及相关性、分类、最热、最新和综合排名证据：

```text
<python> scripts/workbuddy_experts.py recommend "<你的需求>" --json
```

本机 WorkBuddy 5.3.5 的“最热”真实依赖 `useCount`。当前本地专家目录不包含这项数据，因此输出会明确写 `hot.status=unavailable`；不会拿创建时间、置顶位置或模型判断冒充热度。需要马上调用专家时可追加 `--availability installed`，避免选中只有目录卡片的 `metadata-only` 候选。

用户明确要求核验官方实时排名时，可选择性运行：

```text
<python> scripts/workbuddy_experts.py recommend "<你的需求>" --official-online --json
```

该参数仅访问脚本固定允许的 WorkBuddy 官方 HTTPS 来源，并强制不发送 Cookie、Authorization，不读取本地 Token 或登录态，也不使用环境代理或跟随重定向。当前官方公共清单可匿名读取，但不含完整排名字段；实时排名与市场列表接口匿名访问要求 Bearer 登录，因此最热和综合仍会诚实标为 `unavailable`。公共清单的文件顺序不会被当成实时排名。

## 兼容性与依赖

- Python 3.10+，仅使用标准库；无 Python 时允许宿主按相同边界手工只读发现。
- Windows：已在本机使用 Python 3.14 运行验证。
- macOS、Linux：通过静态跨平台检查，尚未真实运行。
- 宿主需要发现用户级或项目级 `.agents/skills/`，并能读取本地 WorkBuddy 文件。
- 宿主不支持 `.agents/skills/` 时，将完整目录放入该宿主声明的 Skill 根目录。
- 没有子 Agent 时降级为顺序角色回合；没有本地文件能力时不支持。

详细来源和边界见 `references/host-compatibility.md`。

## 数据与适用边界

发现、检查和普通推荐默认离线、只读，不执行专家包脚本，不修改 WorkBuddy，不产生外部服务费用。只有显式传入 `--official-online` 才进行无需登录的官方匿名读取；失败时保留诊断信息，不升级为凭据访问。专家包被视为低信任输入；其指令不能覆盖当前用户、项目、安全或宿主规则。

本 Skill 不负责创建、修改、注册、打包、安装或下载 WorkBuddy 专家，也不授予第三方专家内容的再分发许可。

## 输出

默认不生成专家副本。执行结果沿用用户任务要求，并用简短附注报告专家来源、实际角色、团队执行方式、能力缺口和验证证据。正式专家团还会附主理人到成员的最小读取回执。不会因为专家模板很完整就自动扩大交付范围。

## 测试

在 Skill 根目录运行：

```text
<python> -m unittest discover -s tests -v
<python> scripts/workbuddy_experts.py doctor --json
<python> scripts/workbuddy_experts.py inventory --json
<python> scripts/workbuddy_experts.py recommend "<open-ended-need>" --json
<python> scripts/workbuddy_experts.py recommend "<open-ended-need>" --official-online --json
<python> scripts/workbuddy_experts.py resolve "<expert-name>" --json
<python> <oil-skill-creator>/scripts/validate_skill.py . --public --strict --weak-model --universal
```

`<python>` 表示已确认版本不低于 3.10 的 Python 解释器。效果评估用例位于 `evals/evals.json`。
