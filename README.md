# 麦麦塔罗

面向 MaiBot / MaiCore 新版插件系统的本地塔罗占卜插件。插件会从本地牌组中真实随机抽牌，可发送牌面图片、牌名、简短解读和延伸评论。

本插件基于 [KArabella](https://github.com/Kristen23557) 的复活版继续适配、整理和扩展，当前主要面向 MaiBot 1.0.5 与 maibot-plugin-sdk v2。

## 功能特点

- 支持单张、圣三角、时间之流、四要素、五牌阵、吉普赛十字、马蹄、六芒星等牌阵。
- 支持自然语言、Planner Tool 和 `/塔罗` 命令触发。
- 支持 AI 生成准备台词、牌义解读、延伸评论和失败提示。
- 可选择是否遵循 MaiBot 当前人格与表达风格。
- 可选合并转发模式，减少大型牌阵刷屏。
- 可选同用户同聊天流冷却限制，减少刷屏和 LLM 消耗。
- 支持本地自定义牌组、缺图纯文字输出和不完整牌组补齐。
- 插件主动发送的占卜文本不会写入 MaiBot 长期记忆。

## 版本更新

### 1.0.5

- 修复 Planner Tool 路径下模型可能自行编造 `stream_id`，导致合并转发发送到不存在聊天流的问题；现在优先使用 MaiBot 工具上下文注入的真实聊天流。
- 精简正常占卜路径日志，仅保留可行动问题为 warning/error。
- 新增“自动补全标准塔罗牌”选项，可关闭 classic / 内置文字牌库对当前牌组缺失标准牌的补齐，只使用当前牌组自身包含的牌，以便自定义 / 修改牌组。

### 1.0.4

感谢 [@xcr1234](https://github.com/xcr1234) 通过 issue 贡献。

- 新增合并转发发送模式：准备台词、牌面图片、牌名解读和延伸评论可作为聊天记录合并发送。
- 新增可配置冷却限制：开启后，同一用户在同一聊天流内成功占卜后需要等待冷却结束才能再次触发。
- 仓库不再跟踪 `config.toml`，运行配置由 MaiBot 根据插件内置配置模型自动生成。

### 1.0.3

- 修复 AI 生成文本没有反映 MaiBot 人格与表达风格的问题。
- 修复插件输出仍可能写入长期记忆的问题。
- 重新整理自然语言触发规则，减少短指令漏触和普通聊天误触。
- 重做牌组加载，支持缺牌补齐、只有大/小阿卡纳的牌组和缺图纯文字输出。
- 增强 AI 文案配置，准备台词、解读、延伸评论、失败提示均可编辑。
- 增强稳定性，同一聊天流串行执行，避免多次占卜输出交错。

## 安装与启用

推荐通过 MaiBot 插件市场安装并启用本插件。插件市场会负责下载插件包并放置到正确目录，启用后可在 WebUI 中调整配置。

如果需要手动安装，将本仓库目录放入 MaiBot 的 `plugins/Mai_tarots` 目录下。目录内应直接包含：

```text
plugin.py
_manifest.json
tarot_jsons/
resources/
```

`config.toml` 会在插件首次加载时由 MaiBot 自动生成。安装后重启 MaiBot，或按当前运行环境支持的方式重新加载插件。

启用后建议先在 WebUI 确认：

- 插件已启用。
- 自然语言触发和 `/塔罗` 命令按需启用。
- 当前牌组指向存在的本地牌组，默认使用 `classic`。

## 使用方式

### 自然语言触发

开启自然语言触发后，用户可以直接发送类似内容：

```text
占卜！
@机器人 占卜
塔罗
抽一张牌
给我来个塔罗
Tarot reading please
pull a card for me
帮我塔罗占卜一下最近的工作
用塔罗看看今年感情会不会有进展
```

触发模式可在配置中调整：

- `严格`：只接受更保守、更明确的占卜表达。
- `平衡`：默认推荐，识别明确的塔罗、占卜、抽牌、问牌、算卦等请求。
- `宽松`：包含平衡模式，并额外识别“看看感情”“算算运势”这类带占卜主题的模糊表达。

示例边界：

- `占卜！`、`抽一张牌`、`给我来个塔罗`：平衡和宽松都会触发。
- `帮我看看感情`、`算算最近运势`：仅宽松触发。
- `帮我看看这个代码`、`算算一共多少钱`、`塔罗是什么意思`：不会触发占卜。

### 手动命令

```text
/塔罗
/塔罗 大阿卡纳
/塔罗 小阿卡纳 圣三角
/tarot 全部 六芒星
/tarots 大牌 单张
```

命令格式：

```text
/塔罗 [全部|大阿卡纳|小阿卡纳] [牌阵]
/tarot [全部|大阿卡纳|小阿卡纳] [牌阵]
/tarots [全部|大阿卡纳|小阿卡纳] [牌阵]
```

未指定抽牌范围时使用“自动”范围，即只从当前牌组原本包含的类别中抽取；明确填写 `全部` 才会启用完整大小阿卡纳牌池。未指定牌阵时默认为 `单张`。

### 支持的牌阵

| 牌阵 | 张数 | 正逆位 | 位置含义 |
| --- | ---: | --- | --- |
| 单张 | 1 | 支持 | 现状 |
| 圣三角 | 3 | 不切牌 | 现状、愿望、行动 |
| 时间之流 | 3 | 支持 | 过去、现在、未来 |
| 四要素 | 4 | 不切牌 | 行动、言语、感情、物质 |
| 五牌阵 | 5 | 支持 | 现在或主要问题、过去影响、未来、主要原因、行动结果 |
| 吉普赛十字 | 5 | 不切牌 | 对方想法、你的想法、问题、环境、结果 |
| 马蹄 | 6 | 支持 | 现状、可预知、不可预知、即将发生、结果、主观想法 |
| 六芒星 | 7 | 支持 | 过去、现在、未来、对策、环境、态度、预测结果 |

## 配置说明

配置文件为运行目录中的 `config.toml`。该文件由 MaiBot 在插件首次加载时自动生成，并可通过 WebUI 修改；仓库不再跟踪默认 `config.toml`，发布默认值以插件内置配置模型为准。

常用配置：

- `natural_trigger_mode`：自然语言触发模式，可选 `严格`、`平衡`、`宽松`。
- `using_cards`：当前牌组目录名，必须是 `tarot_jsons` 下包含 `tarots.json` 的目录。
- `auto_complete_standard_cards`：是否用 `classic` 和内置纯文字牌库补齐当前牌组缺少的标准牌；默认开启。
- `follow_bot_persona`：AI 文本是否遵循 MaiBot 当前人格与表达风格；默认开启。
- `output_mode`：发送方式，可选 `逐条发送` 或 `合并转发`；默认 `逐条发送`。
- `cooldown_enabled`：是否启用同用户同聊天流冷却；默认关闭。
- `cooldown_seconds`：冷却秒数，默认 `3600`。
- `cooldown_notice_text`：冷却中发送的提示文案，可用 `{minutes}` 和 `{seconds}`。
- `llm_model`：AI 输出使用的模型任务名，WebUI 会从 MaiBot 当前提供的任务配置中生成下拉选项。
- `nickname_source`：称呼来源，可选 `QQ昵称` 或 `群名片`。

AI 相关配置：

- `send_preface` / `ai_preface`：是否发送占卜前准备台词，以及是否由 AI 生成。
- `send_card_names`：是否在占卜结果中包含抽到的牌名列表。
- `send_interpretation` / `ai_interpretation`：是否发送牌义解读，以及是否由 AI 生成。
- `send_extension_comment` / `ai_extension_comment`：是否发送占卜后延伸评论，以及是否由 AI 生成。
- `ai_failure_notice`：后台占卜异常或超时时是否使用 AI 生成失败提示。
- `preface_prompt` / `interpretation_prompt` / `extension_comment_prompt` / `failure_notice_prompt`：四类 AI 输出的可编辑提示词。
- `preface_text` / `extension_comment_text` / `failure_notice_text`：AI 关闭或生成失败时使用的固定文案。

发送行为说明：

- `逐条发送` 会保留各阶段发送延迟。
- `合并转发` 会调用 `send.forward` 一次性发送完整占卜结果，不使用各阶段发送延迟。
- 合并转发和普通文本输出都会避免写入 MaiBot 长期记忆。
- 冷却限制使用 `platform + user_id + stream_id` 作为 key，因此同一用户在不同群聊或私聊中分别计时。
- 只有占卜成功后才会写入冷却；失败、参数错误、发送失败和合并转发失败都不会计入冷却。
- 冷却数据保存在插件目录下的 `tarot_cooldown.json`，该文件不会提交到仓库。

开启 `follow_bot_persona` 后，AI 生成准备台词、牌义解读、延伸评论和失败提示时，会读取 MaiBot 当前的 `bot.nickname`、`bot.alias_names`、`personality.personality` 和 `personality.reply_style`，并进行风格重写。关闭后不会读取宿主人格，只使用塔罗任务提示词。

## 牌组说明

默认牌组为 `classic`，包含大小阿卡纳共 78 张牌，使用公开领域 Rider-Waite-Smith 图像素材：

> Based on the public-domain Rider-Waite-Smith Tarot illustrations by Pamela Colman Smith, first published 1909/1910.

默认不再附带 bilibili 卡组。如需使用其它牌组，请自行添加到 `tarot_jsons` 并在配置中切换 `using_cards`。

### 自定义牌组

每个牌组放在 `tarot_jsons/<牌组名>` 下，至少需要：

```text
tarot_jsons/
  formation.json
  classic/
    tarots.json
    愚者正位.jpg
    愚者逆位.jpg
    ...
```

图片命名格式：

```text
<牌名>正位.jpg
<牌名>逆位.jpg
```

`tarots.json` 用于描述牌名和正逆位牌义。标准牌可以继续使用 `0`–`77` 作为键，插件会自动推断标准编号和大小阿卡纳分类。自定义 ID 建议显式填写：

```json
{
  "my-fool": {
    "standard_id": 0,
    "arcana": "major",
    "name": "愚者",
    "info": {
      "description": "新的开始、冒险",
      "reverseDescription": "鲁莽、时机不对"
    }
  }
}
```

字段说明：

- `standard_id` 可选，标准牌取值为 `0`–`77`；相同编号的自定义牌会覆盖后备牌。
- `arcana` 必须是 `major` 或 `minor`。使用数字键或填写 `standard_id` 时可自动推断。
- 没有 `standard_id` 的牌会作为该类别的额外自定义牌加入牌池。
- 牌名、正位牌义和逆位牌义不能为空。

### 不完整牌组与缺图

插件支持不完整的自定义牌组。默认开启 `auto_complete_standard_cards` 时，比如只做大阿卡纳牌组，未指定范围的触发默认只会在大阿卡纳范围内抽牌；如果用户明确指定“小阿卡纳”或“全部”，插件会优先从 `classic` 补齐缺少的标准牌。

如果 `classic` 不存在，插件会使用内置纯文字牌库补齐牌名和牌义。缺少图片不会中止占卜，插件会跳过图片，继续发送牌名和解读。

如果关闭 `auto_complete_standard_cards`，插件只会使用当前牌组自身包含的牌，不会从 `classic` 或内置纯文字牌库补齐。

抽牌始终从当前有效牌池中随机抽取，不会根据问题内容挑选特定牌面。

## 常见问题

### 询问牌义会触发占卜吗？

一般不会。插件会尽量识别“某张牌是什么意思”“牌阵有哪些”“正逆位含义是什么”等知识类问题，这类问题不会主动执行占卜。

### 为什么塔罗请求有时会被普通 reply 抢答？

插件已经尽量避免普通回复链路直接编造牌面，但不能承诺 100% 阻止所有误触发。

明确的塔罗请求会优先被自然语言 Hook 拦截，例如“占卜”“抽一张牌”“算一卦”“问牌”等。未被 Hook 命中的请求可能进入 Planner 判断，由模型决定是否调用 `tarots` Tool。

如果明确占卜请求经常漏触发，可以把 `natural_trigger_mode` 调整为 `宽松`；如果群聊误触普通咨询，建议改用 `平衡` / `严格`，或使用 `/塔罗` 命令明确触发。

### 为什么提示没有可用牌组？

请确认 `tarot_jsons/<牌组名>/tarots.json` 存在，并且运行目录 `config.toml` 中的 `using_cards` 与牌组目录名一致。默认牌组为 `classic`。

## 兼容性

- 最低麦麦版本：`1.0.5`
- SDK：`2.5.2+`
- 依赖能力：`send.text`、`send.image`、`send.forward`、`llm.generate`、`llm.get_available_models`、`config.get`

## 致谢与来源关系

本项目是在既有 MaiBot 塔罗插件工作上的继续适配与重构：

- [A0000Xz/MaiBot-Tarots-Plugin](https://github.com/A0000Xz/MaiBot-Tarots-Plugin) 是更早的原版实现，提供了 MaiBot 塔罗插件的主要玩法、牌组解耦思路、牌阵与抽牌范围设计，并在 README 中说明其参考了 FloatTech / ZeroBot 相关塔罗插件与数据资源。
- [Kristen23557/MaiBot-Tarots-Plugin-REBORN](https://github.com/Kristen23557/MaiBot-Tarots-Plugin-REBORN/) 是 GitHub 上从 A0000Xz 仓库 fork 出来的复活版，目标是让原版插件继续适配更高版本的麦麦，并转向本地牌组使用方式。
- 当前版本是在 REBORN 方向上的进一步整理：面向 MaiBot 1.0.5 与 maibot-plugin-sdk v2 重写触发链路、配置模型、AI 输出和本地牌组加载逻辑。

感谢 [A0000Xz](https://github.com/A0000Xz/)、[KArabella](https://github.com/Kristen23557)，以及更早提供思路和资源基础的相关开源项目维护者。若上游作者或素材权利方认为当前说明存在不准确之处，请通过仓库 issue 联系修正。

感谢 ChatGPT 和 Codex 提供的编程能力让我得以实现各种想法。

## 许可证

本插件代码继承 AGPL-v3.0 许可证。牌面素材请以各牌组自身的来源和授权说明为准；默认 classic 牌组基于公开领域 Rider-Waite-Smith 图像整理。
