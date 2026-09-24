# Skill 提示词升级说明(2026-09)

## 背景

内置 4 条 Skill(xhs_analysis / douyin_analysis / xhs_creation / douyin_creation)初始为同一段通用基础 Prompt。产品 PRD 第 17 节「GitHub 参考(仅开发阶段)」要求:借鉴 GitHub 上优秀的 Schema / 流程 / 提示词,改写为本产品 Skill;线上后台不做 GitHub 自动搜索安装。本次补齐该改写工作,以 Draft v2 形式写入,经测试、发布后生效,不覆盖 v1 历史。

## 参考来源(均为 MIT 或公开方法论)

| 来源 | 星标 | 借鉴点 |
| --- | --- | --- |
| [ziguishian/xhs-visual-director-skill](https://github.com/ziguishian/xhs-visual-director-skill) | ~1.4k | 小红书原生结构思维:先判内容任务再定形式、封面 3:4 点击钩子、逐页/逐维度单一主信息、自检清单 |
| [OrangeViolin/content-pipeline](https://github.com/OrangeViolin/content-pipeline) | ~220 | 多平台改写流水线;反面清单:过度总结、段落过长、「正确的废话」;人工复核三查(标题不失实、结构逻辑、可照做) |
| [langgptai/wonderful-prompts](https://github.com/langgptai/wonderful-prompts) | 高星 | 结构化中文提示词方法论(角色/规则/工作流/输出分离) |
| 小红书/抖音运营社区公开沉淀的通用写法 | — | 标题数字/反差/身份标签、emoji 克制使用、收藏点设计、黄金三秒钩子、口播短句化、话题标签三层结构 |

仅借鉴框架与规则写法,未复制任何受限商业模板(与《封面能力接入评估》的边界一致)。

## 与旧版的关键差异

1. 平台分化:4 条 Prompt 按平台与任务(拆解/创作)分别改写,不再共用一段。
2. 贴合 Schema:分析维度名与 `schemas/*.schema.json` 的 10 个 prefixItems 一一对应;创作字段逐个给出硬性要求(字数、结构、数量)。
3. 防编造强化:拆解侧「归因到结构、数据克制、画面推断需注明」;创作侧「缺失事实必须进 missing 字段、正文占位」,与系统已有的 JSON Schema 校验和「素材不可信」系统指令叠加。
4. 明确边界:测试与发布仍走 Draft → Test → Published 版本链;发布自动归档旧 Published,可回滚。

## 生效条件

拆解/创作真实调用需要先在管理后台配置模型服务(Base URL / Key / 模型 ID);演示模式的预置样本不经过模型,不受 Prompt 影响。「结构测试」在未配置模型时会报「请管理员配置并启用对应任务的模型」。

## 2026-09 二次增强(v3 草稿)

第一轮写入 v2 后,又对 GitHub 做了一轮按平台复核,新增吸收:

| 来源 | 星标 | 平台 | 借鉴点 |
| --- | --- | --- | --- |
| [otter1101/blogger-distiller](https://github.com/otter1101/blogger-distiller) | ~668 | 通用 | 三层蒸馏(认知/策略/内容)、藏赞比解读、反共识切角、人设三要素、标题公式库 |
| [EBOLABOY/xhs-ai-writer](https://github.com/EBOLABOY/xhs-ai-writer) | ~326 | 小红书 | 标题公式库、痛点→产品→细节→感受→建议骨架、去 AI 味禁用词、广告法极限词替换、tags 四层组合 |
| [JuneYaooo/social-account-doctor](https://github.com/JuneYaooo/social-account-doctor) | ~258 | 小红书+抖音 | 拆爆款四问(钩子第几秒/首帧模板/清单体还是故事体/评论区议题)、流量点与转化点区分、没看过视频不假装看过 |

均为 MIT 协议。v3 为草稿,经测试、发布后替换 v2。

## 版本收敛(应用户要求)

v3 经确认后直接置为生效版,v1/v2 已删除;每类 Skill 只保留一条「生效中」记录。此后发布新版本时,服务端仍会把旧生效版转为「已归档」(可在界面回滚或手动清理)。
