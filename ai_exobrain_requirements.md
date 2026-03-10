# 个人 AI 认知外挂 (Personal AI Cognitive Exobrain)
> 设计文档 v2.0 | 最后更新：2026-03-10

## 1. 核心理念与挑战

这是一个陪伴用户从"普通大模型"向"通用人工智能 (AGI)"过渡期间使用的个人记忆与日程系统。

### 1.1 核心挑战（痛点）
*   **当前 AI 的智力瓶颈与上下文限制**：当前的 AI 无法像 AGI 那样始终挂在常驻内存里记住一切；如果把几十年的记忆以生硬的数据库结构全塞给它，不仅会耗尽上下文（爆内存），还会被复杂的表结构（元数据）搞晕。
*   **信息的"有损压缩"与演进**：所有的"结构化数据"（把"我想买牛奶"转化成 `category=household, due=today`）都是当前 AI 智力水平下的一种"有损压缩"。为了保证以后更聪明的 AI 能读懂，系统必须永远保留用户的**原始意图（Raw Input）**作为唯一真理。
*   **交互接口的认知负担**：不能让 AI 去读厚厚的 Schema 设计文档（即：元数据大于实际数据）。系统提供给 AI 的操作接口（API / Tools）必须是高度语义化的，即"见名知意"，使得各种弱智或聪明的模型拿到锤子就知道怎么砸钉子。

### 1.2 最终愿景
系统物理表现为一个极其轻量、跨平台（甚至手机端可用）的文件或数据库。
*   对最笨的 AI：它是几个极简的函数调用，帮用户备忘。
*   对未来的 AGI：它是无损读取用户半生所思所想的数字灵魂切片。

---

## 2. 总体系统架构：双轨制 (Dual-Track Architecture)

为了兼顾"绝对真实"与"当前可查询"，系统采用严格的数据分层：

### 2.1 轨一：真实层 (Immutable Raw Input Log) —— 【只追加，不修改】✅ 已实现
这是系统的"潜意识"和"灵魂备份"，是唯一不被 AI 幻觉污染的 Ground Truth。
*   **存储内容**：用户的每一句原话、每一个未经加工的想法。
*   **已实现字段**：`id`, `raw_text`, `ai_summary`, `source_module`, `created_at`。
*   **待完善字段**：`source_device`（字段已存在但暂未写入），`context_snippet`（暂未实现，多设备场景再做）。
*   **设计原则**：就像飞行数据记录仪（黑匣子）。即使当前的 AI 把这条意图处理错了，在轨一里也永远保留着原话，供明年的强力引擎重新解析。

### 2.2 轨二：结构化投影层 (Projected Structural View) —— 【可随时重建的"脏缓存"】✅ 已实现
这是给"当前的 AI"为了快速回答"我今天该干嘛"而建立的业务表。
*   **存储内容**：从"轨一"解析出来的具体待办、偏好、目标、人际关系实体。
*   **已实现字段**：`id`, `log_id`（关联轨一）, `task_name`, `status`, `due_date`, `priority`（low/normal/high/critical）, `effort_estimate`（quick/small/medium/large）, `parent_task_id`（支持任务树层级）, `metadata_json`（JSON 动态扩展标签）, `created_at`, `updated_at`。
*   **设计原则**：它是"易失"的。如果 Schema 设计得不好，或者目前的模型解析能力太弱把分类标错了，用户可以随时清空这一层，让目前的模型或未来的更强模型对着"轨一"的数据重新洗出一套新的结构化表列。

---

## 3. 给 AI 暴露的工具接口（语义交互层）✅ 全部已实现

**关键原则**：绝对不给 AI 暴露原生的 SQL 或大而全的 `insert_into_db(id, category, status...)` 这种充满元数据负担的接口。工具必须是语义化的。

我们通过 MCP（模型上下文协议）向 AI 暴露以下 **6 个**高内聚、低认知的"锤子"：

### 3.1 捕获与表达（Write Tools）
为了避免 AI 纠结填什么表，只提供最直观的意图捕获。

1.  **`record_thought_or_fact(raw_thought_string, ai_summary?)`** ✅
    *   **业务语义**："用户刚说了一句可能有用的事实或者随想，记下来。"
    *   **职责范围**：将 `raw_thought_string` 打入轨一（真实层）。如果 AI 觉得有必要，可以提炼一条 `ai_summary`。

2.  **`add_actionable_task(task_name, raw_user_quote, due_date?, priority?, effort_estimate?, parent_task_id?)`** ✅ **超额完成**
    *   **业务语义**："用户明确要我提醒他/帮他做一件事。"
    *   **职责范围**：直接写进轨二（结构化层）的待办表，同时将原话关联至轨一。
    *   **升级点**：`urgency` 被拆分为正交的 `priority`（紧急程度）和 `effort_estimate`（工作量），并新增 `parent_task_id` 支持任务树层级嵌套。

3.  **`update_task_status(task_id, new_status, reason?)`** ✅
    *   **业务语义**："用户刚才说的那个事做完了，或者不想做了。"

4.  **`add_task_metadata(task_id, tags_json_string)`** ✅ **额外实现**
    *   **业务语义**："给一个已有任务附加长尾信息，比如位置、关联链接、所属风格。"
    *   **职责范围**：在不修改任何 Schema 的前提下，将任意 JSON 键值对合并注入到 `metadata_json` 字段，充当无限延伸属性的逃生舱。

### 3.2 动态检索与关联（Read Tools）
为了防止全量拉取导致"爆内存"，一切读取都是被动且精准的。

5.  **`recall_past_mentions_of(concept_or_keyword)`** ✅ **超额完成**
    *   **对应场景**：用户问"我昨天提过牛奶吗？"
    *   **行为**：混合检索策略——Pass 1 执行 LIKE 精确匹配；Pass 2 始终运行语义向量搜索（`paraphrase-multilingual-MiniLM-L12-v2`，中文友好，CPU可跑），两路结果去重、按相似度排序后返回 Top N。
    *   **设计亮点**：服务器启动时即预热 Embedding 模型（Eager Loading），搜索无冷启动延迟；搜索"乳制品"能召回你说的"牛奶"记录；搜索完全陌生的词（如"西瓜"）则正确返回空。

6.  **`suggest_next_actions(available_time_minutes?)`** ✅ **超额完成**
    *   **对应场景**：用户问"我好无聊，接下来做点啥？"
    *   **行为**：后端代码（不是 AI！）去扫描结构化表中未完成任务，按 `priority`（critical=+20, high=+10, low=-5）和 `effort_estimate`（quick=+5, small=+2）算法打分排序，若用户提供了空闲时间则过滤掉不匹配的大任务，最终返回精简的推荐列表。

---

## 4. 关键演进与扩展性

1.  **脱离大模型绑定** ✅：数据存储为 SQLite 单文件格式。不论是 VS Code 里的插件、手机上的端侧模型，还是云端的超级大模型，只要能接入读取该文件的接口，都能无缝接管用户的记忆。

2.  **结构化演进策略** ✅：`add_task_metadata` 工具已实现，AI 可以调用它以 Key-Value 的形式动态附着扩展数据（比如给"找设计资源"任务加上`{"style": "赛博朋克风", "website": "Pinterest"}`），而不必让数据库抛出 Schema 验证错误。

3.  **向量化升级** ✅ **已提前实现**：`recall_past_mentions_of` 已同时集成 LIKE 文本搜索和 `sentence-transformers` 语义向量搜索两套引擎，真正实现"语义联想回忆"。

4.  **任务树支持** ✅ **新增实现**：`actionable_tasks` 表支持 `parent_task_id` 递归自引用，AI 可以把大项目拆解成有层级的子任务树，并支持级联删除（父任务删除时，子任务自动清理）。

---

## 5. 待办与未来演进方向

*   [ ] `source_device` 字段的实际写入（多设备接入时再做）
*   [ ] `context_snippet` 字段的实现（记录触发这条记忆时的环境快照）
*   [ ] 将 Embedding 向量离线预计算并持久化到 SQLite（记录达到数千条时再优化）
*   [ ] `suggest_next_actions` 的返回结构改为嵌套树形（方便展示并行字任务）
*   [ ] 多模态输入（语音转文字后写入轨一）
