# 麦麦塔罗

面向 MaiBot / MaiCore 新版插件系统的本地塔罗占卜插件。插件会从本地牌组中真实抽牌，发送牌面图片、牌名和简短解读。
本插件基于 Kristen23557 的复活版进行了适配、整理和功能追加。

当前版本主要围绕 MaiBot 1.0.5 与 maibot-plugin-sdk v2 进行适配。附带的默认牌组  `classic` 使用公有领域的 Rider-Waite-Smith 塔罗图像素材。

## 功能特点

- 抽牌占卜：支持单张、圣三角、时间之流、四要素、五牌阵、吉普赛十字、马蹄、六芒星牌阵；抽牌范围支持全部、大阿卡纳、小阿卡纳。
- 多入口触发：支持自然语言触发、Planner Tool 调用和手动命令。
- 可选AI生成回复 ：准备台词、牌义解读、延伸评论均可选择使用本地模板/牌义文本，或是让 AI 按插件内置的塔罗回复风格生成回复。
- 语境化回复：AI 准备台词和延伸评论可参考用户原始占卜问题生成回复内容。
- 防误触知识问答：询问“某张牌是什么意思”“牌阵有哪些”等知识问题时，不主动执行占卜。
- 记忆写回规避：插件主动发送的占卜文本会清空 `processed_plain_text`，减少长期记忆把占卜文案当成人物事实写回的风险。

## 现版本主要改动

- 适配新版 MaiBot 插件运行时，使用 `MaiBotPlugin`、`Tool`、`Command`、`EventHandler` 和 `HookHandler` 组织插件能力。
- 重构为本地牌组模式，启动时扫描 `tarot_jsons` 下包含 `tarots.json` 的牌组。
- 默认优先使用 `classic` 牌组，未配置或配置不可用时自动选择第一个可用本地牌组。
- 新增自然语言触发模式：严格、平衡、宽松。
- 新增 `/塔罗`、`/tarot`、`/tarots` 命令入口。
- 新增 AI 准备台词、AI 解读、AI 延伸评论及其语境开关。
- 新增各发送阶段延迟配置，模拟更自然的抽牌节奏。
- 新增称呼来源配置，可优先使用 QQ 昵称或群名片。
- 移除旧版远程牌面下载、代理下载、一键缓存、切换牌组命令等路径；当前以本地牌组文件为准。

## 安装与启用

推荐通过 MaiBot 插件市场安装并启用本插件。插件市场会负责下载插件包并放置到正确目录，启用后可在 WebUI 中调整配置。

如果需要手动安装，可以将本仓库目录放入 MaiBot 的 `plugins/Mai_tarots` 目录下，目录内应直接包含 `plugin.py`、`_manifest.json`、`config.toml` 和 `tarot_jsons`。放置完成后重启 MaiBot，或按当前运行环境支持的方式重新加载插件。

启用后建议先确认以下配置：

- `enabled` 为 `true`，用于启用插件整体功能。
- `enable_tarots` 为 `true`，用于启用自然语言拦截和 `tarots` Tool。
- `enable_tarots_command` 为 `true`，用于启用 `/塔罗`、`/tarot`、`/tarots` 命令。
- `using_cards` 指向存在的本地牌组目录，默认使用 `classic`。

## 使用方式

### 自然语言

开启自然语言触发后，用户可以直接发送类似内容：

```text
帮我塔罗占卜一下最近的工作
抽一张牌看看
用塔罗看看今年感情会不会有进展
帮我用圣三角测测未来
```

触发模式可在配置中调整：

- `严格`：只拦截明确包含塔罗、占卜、抽牌等表达的请求。
- `平衡`：兼顾常见的塔罗问题表达。
- `宽松`：会尝试拦截更多“看看”“算算”“测测”类请求。

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

未指定抽牌范围时默认为 `全部`。未指定牌阵时默认为 `单张`。

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

配置文件为 `config.toml`。

关键配置：

- `enabled`：是否启用插件。
- `enable_tarots`：是否启用自然语言触发和 Tool 触发。
- `enable_tarots_command`：是否启用 `/塔罗`、`/tarot`、`/tarots` 命令。
- `natural_trigger_mode`：自然语言触发强度，可选 `严格`、`平衡`、`宽松`。
- `using_cards`：当前牌组目录名，必须是 `tarot_jsons` 下包含 `tarots.json` 的目录。
- `send_card_names`：是否发送抽到的牌名列表。
- `send_interpretation`：是否发送牌义解读。
- `ai_interpretation`：是否使用 AI 生成解读；关闭后使用牌组 JSON 中的牌义文本。
- `send_preface` / `ai_preface`：是否发送占卜前准备台词，以及是否由 AI 生成。
- `send_extension_comment` / `ai_extension_comment`：是否发送占卜后延伸评论，以及是否由 AI 生成。
- `contextual_preface` / `contextual_extension_comment`：AI 生成时是否参考用户原始问题和抽牌内容。
- `delay_*_seconds`：不同阶段的发送延迟。
- `llm_model`：AI 输出使用的模型任务名。
- `nickname_source`：称呼来源，可选 `QQ昵称` 或 `群名片`。

## 牌组结构

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

`tarots.json` 用于描述 78 张牌的名称和正逆位牌义。图片命名需与牌名匹配，格式为：

```text
<牌名>正位.jpg
<牌名>逆位.jpg
```

例如：

```text
愚者正位.jpg
愚者逆位.jpg
圣杯二正位.jpg
圣杯二逆位.jpg
```

当前默认牌组为 `classic`，包含大小阿卡纳共 78 张牌。classic 牌库使用的卡图说明：

> Based on the public-domain Rider-Waite-Smith Tarot illustrations by Pamela Colman Smith, first published 1909/1910.

这些 Rider-Waite-Smith 公开领域素材可用于开源项目，classic 牌库包含大阿卡纳与小阿卡纳。默认不再附带 bilibili 卡组；如需使用其它牌组，请自行添加到 `tarot_jsons` 并在配置中切换 `using_cards`。

## 常见问题

### 为什么塔罗请求有时会被普通 reply 抢答？

插件已经尽量避免普通回复链路直接编造牌面，但不能承诺 100% 阻止所有误触发。

当前有两层处理：

- 明确的塔罗请求会先被自然语言 Hook 拦截，例如“塔罗占卜”“抽一张牌”“算一卦”“测测”“问牌”等。命中后插件会后台执行真实抽牌，并中止普通回复链路。
- 没被 Hook 命中的请求会进入 Planner 判断，模型可以调用 `tarots` Tool 执行真实抽牌。`tarots` Tool 的描述中已经明确要求不要直接用 reply 编造牌面。

残留风险主要来自表达过于隐晦、自然语言触发模式过严，或主程序 Tool 调度后仍继续生成普通回复。遇到这种情况可以把 `natural_trigger_mode` 调整为 `宽松`，或者使用 `/塔罗` 命令明确触发。

### 询问牌义会触发占卜吗？

一般不会。插件会尽量识别“某张牌是什么意思”“牌阵有哪些”“正逆位含义是什么”等知识类问题，这类问题不主动执行占卜。

### 为什么提示没有可用牌组？

请确认 `tarot_jsons/<牌组名>/tarots.json` 存在，并且 `config.toml` 中的 `using_cards` 与牌组目录名一致。默认牌组为 `classic`。

## 兼容性

- 最低麦麦版本：`1.0.5`
- SDK：`2.5.2+`
- 依赖能力：`send.text`、`send.image`、`llm.generate`

## 致谢与来源关系

本项目是在既有 MaiBot 塔罗插件工作上的继续适配与重构：

- [A0000Xz/MaiBot-Tarots-Plugin](https://github.com/A0000Xz/MaiBot-Tarots-Plugin) 是更早的原版实现，提供了 MaiBot 塔罗插件的主要玩法、牌组解耦思路、牌阵与抽牌范围设计，并在 README 中说明其参考了 FloatTech / ZeroBot 相关塔罗插件与数据资源。
- [Kristen23557/MaiBot-Tarots-Plugin-REBORN](https://github.com/Kristen23557/MaiBot-Tarots-Plugin-REBORN/) 是 GitHub 上从 A0000Xz 仓库 fork 出来的复活版，目标是让原版插件继续适配更高版本的麦麦，并转向本地牌组使用方式。
- 当前 `kuuri-krtt.mai_tarots` 版本是在 REBORN 方向上的进一步整理：面向 MaiBot 1.0.5 与 maibot-plugin-sdk v2 重写触发链路、配置模型、AI 输出和本地牌组加载逻辑。

感谢 A0000Xz、Kristen23557 / KArabella，以及更早提供思路和资源基础的相关开源项目维护者。若上游作者或素材权利方认为当前说明存在不准确之处，请通过仓库 issue 联系修正。

感谢ChatGPT和Codex提供的编程能力让我得以实现各种想法。

## 许可证

本插件代码继承 AGPL-v3.0 许可证。牌面素材请以各牌组自身的来源和授权说明为准；默认 classic 牌组基于公开领域 Rider-Waite-Smith 图像整理。
