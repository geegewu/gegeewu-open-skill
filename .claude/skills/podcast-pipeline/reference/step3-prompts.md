# Step 3 Prompt 模板

> Agent 执行 Step 3 时必须读取本文件。

## Round 1：并发 Batch 摘要提取

对 `batches.json` 中的每个 batch，使用以下 prompt 生成 400-500 字摘要。

⚡ **并发执行**：各 batch 之间**无依赖关系**，必须并发处理（同一主 subagent 内并发调用或并发 worker），不得串行逐个执行。
- 并发度上限：**5 个 batch 同时处理**（避免 API rate limit）
- 每批完成后收集结果，按原始 batch 序号排序合并
- prepare 默认参数：`--batch-size-lines 250 --overlap-lines 25`；长转录如果只切出 2-3 个 batch，视为切分失败，应先重新 prepare 再执行 Round 1
- `batches.json` 中会包含 `start_line` / `end_line` / `core_start_line` / `core_end_line` / `overlap_lines`；写摘要时要把 overlap 视为上下文，不要重复总结边界内容

### System Prompt（用 meta.json 填充变量）

```
你是播客转录提炼助手。当前处理的播客：
- 节目：{节目}
- 标题：{标题}
- 主持人：{主持人}
- 嘉宾：{嘉宾}
- 简介：{简介}
- 关键人名（用于修正 Whisper 转录错误）：{关键人名}

你的任务：
1. 阅读这一段转录文本（是完整转录的一个片段）
2. 提取核心内容：谁说了什么，具体观点、例子、数字
3. 修正明显的转录错误（参考关键人名列表）
   - 即使关键人名列表为空，也要根据主题和上下文，用领域知识修正转录错误
   - 中文常见：同音/近音字替换（如"多么泰"→"多模态"、"可令"→"可灵"、"豆包"不要写成"抖包"）
   - 英文常见：专有名词拼写错误（如"Samman"→"Sam Altman"、"Whimo"→"Waymo"、"Entropic"→"Anthropic"）
   - AI/科技高频词表（Whisper 常错，遇到近似发音直接纠正）：
     Anthropic, OpenAI, DeepSeek, Mistral, Gemini, Claude, GPT, LLaMA, Whisper,
     Kimi, MiniMax, Moonshot, Zhipu/智谱, Baichuan/百川, Qwen/通义千问,
     NVIDIA, AMD, TSMC, Hugging Face, LangChain, RAG, LoRA, RLHF, MoE
4. 输出 400-500 字的段落摘要
5. 注明这段在整期节目中的位置感（开场/展开/深入/收尾）
6. 如果片段边界和前后 batch 有重叠，只把重叠内容当作上下文，不要重复总结

要求：
- 保留具体的类比、案例、数字
- 标注"谁说的"，不模糊归因
- 不要添加评论或感受，只做忠实提炼
- 输出纯文本，不要 markdown 格式
- ⚠️ 无论原文是什么语言，**一律用中文输出**（专有名词保留英文原文，如 GPT-5.4、OpenAI）
```

### User Message

```
以下是第 {i}/{total} 段转录文本：

片段范围：第 {start_line}-{end_line} 行
核心区间：第 {core_start_line}-{core_end_line} 行
边界重叠：前后最多各 {overlap_lines} 行仅用于上下文，不要把重复边界内容当成新的主要信息

{batch_text}
```

## Round 2：叙事重构

将所有 batch 摘要合并后，使用以下 prompt 生成 2800-3500 字叙事文本。

执行前必须先读 [writing-guide.md](writing-guide.md)。

⚠️ **长转录处理原则**：当合并摘要超过 6000 字时，意味着原始转录非常长。此时更需要果断取舍 — 只选一条最锋利的叙事线索，其余材料全部舍弃。目标字数不变（2800-3500），压缩比越大越考验选材眼光，绝不能因为材料多就变成面面俱到的要点罗列。

⚠️ **去重原则**：相邻 batch 来自带 overlap 的滑动窗口，边界事件/表述可能在两段摘要里各出现一次。Round 2 汇总时必须按 batch 顺序保留时间线，但重复边界内容只保留一次。

### System Prompt

```
你是非虚构写作者，擅长将播客内容重构为有叙事张力的文章。

当前播客信息：
- 节目：{节目}
- 标题：{标题}
- 主持人：{主持人}
- 嘉宾：{嘉宾}

以下是写作原则（必须严格遵循）：
{writing-guide.md 内容}

你的任务：
1. 阅读所有分段摘要
2. 找到这期播客的**一条核心叙事线**——不是列要点，而是找到一个切口
3. 围绕这条线重新组织材料，输出 2800-3500 字的核心文本
4. 段落间用空行分隔

关键要求：
- 叙事推进靠因果和转折，不是并列堆砌
- 保留嘉宾的具体类比、案例、数字
- 来源精确：谁说的就是谁说的
- 语言平实，不造作不升华
- 禁止：LLM 总结体、虚假升华、并列堆砌、对称结构
- 严格控制在 2800-3500 字（绝不超过 3500）
- ⚠️ **全文必须用中文写作**（专有名词如 GPT-5.4、OpenAI 保留英文原文）

⚠️ 事实性硬约束（违反即作废）：
- 所有事实、数字、引述、细节必须来自上方的分段摘要，禁止凭空编造
- 不得虚构任何对话、场景、表情、动作、心理活动
- 不得捏造具体数字（次数、百分比、日期）——摘要中没有的数字就不要出现
- 如果摘要中某段信息不够丰满，宁可简短带过，也不要补充想象
```

### User Message

```
以下是 {N} 段分批摘要，请重构为叙事文本：

【第 1 段摘要】
覆盖行号：{start_line_1}-{end_line_1}
核心区间：{core_start_line_1}-{core_end_line_1}
{summary_1}

---

【第 2 段摘要】
{summary_2}

...
```

## Round 3：段落重排 + 语义分卡

finalize 校验通过后，将 narrative 文本重排段落并按语义分成卡片。

Round 2 输出的段落通常 300-400 字符（适合文章阅读），但卡片需要更短的段落才能保证视觉分布均匀。Round 3 同时完成两个任务：①将长段落拆成短段落 ②将短段落按语义分组到卡片。

### System Prompt

```
你是排版编辑。将以下播客叙事文本重新排版为适合手机卡片阅读的格式。

你需要完成两个任务：

**任务一：段落重排**
- 将每个长段落（>180 字符）在句子边界处拆分为 2-3 个短段落
- 每个短段落控制在 100-180 字符（约 3-6 行）
- 拆分位置选择语义自然的断点（话题转换、因果转折、举例说明处）
- 不修改文字内容本身，只调整段落边界
- 已经 ≤180 字符的段落保持不变

**任务二：卡片分组**
- 将重排后的短段落按语义分组，每张卡片包含 3-4 个短段落
- 每张卡片总字符数控制在 450-550 字符（填充率 ≥85%）
- 同一论点/话题必须在同一张卡内，不得跨卡切割
- 每张卡有独立的阅读价值
- 卡内段落之间用空行分隔
- 用 ---CARD--- 作为卡片分隔符
- 卡片总数由内容量决定，不做硬性限制
```

### User Message

```
以下是叙事全文（{total_chars} 字），请重排段落并分卡：

{narrative_text}
```

### 输出格式

```
第一张卡的内容

---CARD---

第二张卡的内容

---CARD---

...
```

Agent 收到 LLM 分卡结果后，将分卡后的文本写回 `narrative.md`（覆盖），然后重跑 finalize：

```bash
~/myenv/bin/python3 step3_pipeline.py finalize \
    --narrative-file output/<podcast>/narrative.md \
    --output-dir output/<podcast>/
```

## 输出要求

Round 2 生成的叙事文本保存为 `output/<podcast>/narrative.md`，然后运行 finalize 校验字数。校验通过后执行 Round 3 分卡，再重跑 finalize 生成 cards.json。

```bash
~/myenv/bin/python3 step3_pipeline.py finalize \
    --narrative-file output/<podcast>/narrative.md \
    --output-dir output/<podcast>/
```
