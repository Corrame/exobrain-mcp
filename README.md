# Personal AI Cognitive Exobrain (MCP) 🧠

这是一个基于 **Model Context Protocol (MCP)** 的个人认知外脑服务器。它能为你的大语言模型（如 Claude Desktop、Cursor、VS Code 插件等）赋予**长期的、结构化的真实记忆**。

## 🌟 为什么需要它？（痛点直击）

现在的 AI 模型在处理用户的长期记忆时，常常存在两个致命缺陷：
1. **上下文遗忘（爆内存）**：大模型无法把你一生的聊天记录常驻内存，传统的记忆体往往会导致上下文长度爆炸。
2. **信息的"有损压缩"**：当你说"我想买两箱纯牛奶"时，现在的 AI 可能会把它自作主张地存成 `Task: 买牛奶, Category: 生活`，完全丢失了你说话时的语意和感情色彩。这种死板的结构化数据会导致未来更聪明的人工智能无法追溯你的原始意图。

**我们的解法：双轨制架构 (Dual-Track Architecture)**
*   **轨一：潜意识/黑匣子（Immutable Raw Input Log）**：只允许追加（Append Only）。你的每一句原话都会作为"绝对真理"被永久保存在 SQLite 数据库中。
*   **轨二：结构化投影（Projected Structural View）**：为了方便当前的 AI 帮你管理日常事务（比如待办列表），它会动态从"轨一"生成这一层的任务数据。即使 AI 偶尔标错了分类，或者你想重构任务体系，这层"脏缓存"也可以随时删库重建，因为**你的原话永远在轨一里安全保存着。**

---

## 🛠 给 AI 的高内聚语义工具 (MCP Tools)

本系统暴露了对大模型极其友好的 **6 个**函数接口，大幅降低 AI 操作数据库的认知负担（无需写 SQL）：

| 工具 | 功能 |
|---|---|
| `record_thought_or_fact` | 记录随想、偏好或事实到不可改变的真理层（轨一） |
| `add_actionable_task` | 捕获交办指令，自动录入轨一并映射为轨二待办任务，支持**任务树层级**（`parent_task_id`）、**优先级**（`priority`）和**工作量评估**（`effort_estimate`） |
| `update_task_status` | 更新任务进度（完成/废弃）并记录变更原因 |
| `add_task_metadata` | 为任务动态附加无限扩展的 JSON 标签（无需修改数据库结构） |
| `recall_past_mentions_of` | **混合检索**：同时运行精确关键词匹配 + 语义向量搜索，搜"乳制品"也能找到"牛奶"的记录 |
| `suggest_next_actions` | 后端算法自动按优先级打分、按空闲时间过滤，返回精准的下一步行动建议 |

---

## 🔍 语义向量搜索（核心亮点）

`recall_past_mentions_of` 实现了**混合检索策略**：

- **Pass 1**：高效的 SQLite `LIKE` 精确关键词匹配（零延迟）
- **Pass 2**：基于 `sentence-transformers` 的语义向量搜索（始终运行，并行补充结果）
  - 使用 `paraphrase-multilingual-MiniLM-L12-v2` 模型（100MB，CPU 可运行，强中文支持）
  - 服务器启动时预热模型（Eager Loading），消除搜索冷启动延迟
  - 搜索"乳制品"→ 召回"牛奶"记录 ✅
  - 搜索从未提过的"西瓜"→ 正确返回空结果 ✅

---

## 🚀 安装与部署

### 选项 A：让你的 AI 帮你全自动安装（最赛博朋克的推荐！）
如果你正在使用具有 Agent 能力的 IDE（如 Cursor / Cline / Antigravity）：
1. 将本项目 clone 到本地。
2. 直接向你的 AI 发送指令：**"请阅读目录下的 `INSTALL-MCP.md`，并帮我自动安装这个 MCP 服务。"**
3. AI 将自动建立虚拟环境，寻找配置入口，完成一切注入！

### 选项 B：极客手动配置

1. **获取代码并初始化环境：**
   ```bash
   git clone <你的仓库地址>
   cd exobrain-mcp
   python -m venv .venv
   .\.venv\Scripts\activate  # Windows 用户
   source .venv/bin/activate # Mac/Linux 用户
   pip install -r requirements.txt
   ```
   > ⚠️ `requirements.txt` 包含 `sentence-transformers`，首次安装时会下载约 100MB 的语义模型，请确保网络畅通。

2. **配置你的 MCP 宿主（如 Claude Desktop）：**
   打开对应的 JSON 配置文件（例如 `claude_desktop_config.json`），并在 `mcpServers` 下方添加注入节点：
   ```json
   "mcpServers": {
     "personal-memory": {
       "command": "C:/绝对路径/.../exobrain-mcp/.venv/Scripts/python.exe",
       "args": [
         "C:/绝对路径/.../exobrain-mcp/server.py"
       ]
     }
   }
   ```
   > ⚠️ **重要**：`command` 必须指向虚拟环境（`.venv`）里的 Python，而不是系统全局 Python，否则 `sentence-transformers` 将无法被加载，语义搜索会静默降级为纯关键词搜索。

3. **重启并体验：**
   保存配置并重启你的 Client（比如重启 Claude Desktop），并在对话框里试着说出：*"我非常讨厌吃香菜，无论如何都要记住这一点。"* 然后看看你的认知外脑如何为你工作！

---

## 📂 数据隐私

你的个人数据（`exobrain.db`）存储在本地，且已被 `.gitignore` 永久屏蔽，不会被推送至任何远端仓库。

---

## 🙏 致谢 / Acknowledgments

本项目在设计和实现过程中参考并整合了以下开源项目的优秀思想：

- **[Ombre-Brain](https://github.com/P0lar1zzZ/Ombre-Brain)** by P0lar1zzZ (MIT License)
  - 情感坐标体系（Valence/Arousal）的概念与应用
  - 基于艾宾浩斯遗忘曲线的记忆衰减算法
  - 高唤醒度记忆权重加成机制
  
  上述概念经适配后应用于本项目的 `emotion_engine.py` 模块，为记忆系统赋予了情绪感知和自然遗忘的能力。

---

**从普通的 LLM 到通用人工智能 (AGI)，系统需要数字灵魂的缓存。祝你和你的 AI 合作愉快！**
