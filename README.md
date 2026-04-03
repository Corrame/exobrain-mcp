# Personal AI Cognitive Exobrain (MCP) 🧠

这是一个基于 **Model Context Protocol (MCP)** 的个人认知外脑服务器。它能为你的大语言模型（如 Claude Desktop、Cursor、VS Code 插件等）赋予**长期的、结构化的、带情感坐标的真实记忆**。

## 🌟 为什么需要它？（痛点直击）

现在的 AI 模型在处理用户的长期记忆时，常常存在三个致命缺陷：
1. **上下文遗忘（爆内存）**：大模型无法把你一生的聊天记录常驻内存，传统的记忆体往往会导致上下文长度爆炸。
2. **信息的"有损压缩"**：当你说"我想买两箱纯牛奶"时，现在的 AI 可能会把它自作主张地存成 `Task: 买牛奶, Category: 生活`，完全丢失了你说话时的语意和感情色彩。
3. **情绪感知的缺失**：人类的记忆不是平等的——创伤和狂喜会被记住很久，平淡的日常会自然遗忘。传统数据库无法模拟这种**情感权重**。

**我们的解法：情感感知双轨制架构 (Emotion-Aware Dual-Track Architecture)**
*   **轨一：情感标记的真实层（Emotion-Tagged Immutable Log）**：每一句原话不仅被保存，还被标记上 **Valence（效价）** 和 **Arousal（唤醒度）** 情感坐标。高唤醒度的记忆（极度的快乐或痛苦）会自动获得更高权重，像人类记忆一样自然浮现。
*   **轨二：结构化投影层（Projected Structural View）**：从轨一提取的待办、偏好、目标，依然可以随时重建。

---

## 🛠 给 AI 的高内聚语义工具 (MCP Tools)

本系统暴露了对大模型极其友好的 **7 个**函数接口，大幅降低 AI 操作数据库的认知负担（无需写 SQL）：

| 工具 | 功能 |
|---|---|
| `record_thought_or_fact` | 记录随想、偏好或事实到轨一，**自动分析情感坐标**（Valence/Arousal）和主题域 |
| `add_actionable_task` | 捕获交办指令，自动录入轨一并映射为轨二待办任务，支持**任务树层级**（`parent_task_id`）、**优先级**（`priority`）和**工作量评估**（`effort_estimate`） |
| `update_task_status` | 更新任务进度（完成/废弃）并记录变更原因 |
| `add_task_metadata` | 为任务动态附加无限扩展的 JSON 标签（无需修改数据库结构） |
| `recall_past_mentions_of` | **混合检索**：关键词匹配 + 语义向量搜索 + **情感权重排序**，高唤醒度记忆优先浮现 |
| `suggest_next_actions` | 后端算法自动按优先级打分、按空闲时间过滤，返回精准的下一步行动建议 |
| `check_active_emotions` | **会话开始时调用**：自动浮现当前权重最高的 **Top 3** 高唤醒度记忆，让 AI 主动关心你未解决的情绪 |

---

## 🔍 核心亮点

### 1. 语义向量搜索

`recall_past_mentions_of` 实现了**三层混合检索策略**：

- **Pass 1**：高效的 SQLite `LIKE` 精确关键词匹配（零延迟）
- **Pass 2**：基于 `sentence-transformers` 的语义向量搜索
  - 使用 `paraphrase-multilingual-MiniLM-L12-v2` 模型（100MB，CPU 可运行，强中文支持）
  - 服务器启动时预热模型（Eager Loading），消除搜索冷启动延迟
- **Pass 3**：情感权重重排
  - 基于 **艾宾浩斯遗忘曲线** 的动态衰减计算
  - 高 Arousal（唤醒度）记忆获得额外加成
  - 搜索"乳制品"→ 召回"牛奶"记录 ✅

### 2. 情感坐标与记忆浮现

每条记忆都被标记在 **Russell 情感环形模型**上：

- **Valence（效价）**: 0.0（极度负面）→ 1.0（极度正面）
- **Arousal（唤醒度）**: 0.0（平淡如水）→ 1.0（情绪激烈）

**衰减公式：**
```
Score = Importance × (Activation_Count^0.3) × Time_Decay × (Base + Arousal² × Boost)
```

- 高唤醒度记忆衰减慢，更容易被 `check_active_emotions()` 在对话开头浮现
- 激活次数越多的记忆越难忘（被反复提起的事情记得更牢）

---

## 🚀 安装与部署

### 环境要求

- Python 3.11+
- （可选）`ANTHROPIC_API_KEY` 环境变量——用于自动情感分析。如果不提供，系统会使用默认值（Valence=0.5, Arousal=0.3）。

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

2. **配置环境变量（可选但推荐）：**
   ```bash
   # Windows PowerShell
   $env:ANTHROPIC_API_KEY="your-api-key"
   
   # Windows CMD
   set ANTHROPIC_API_KEY=your-api-key
   
   # Linux/Mac
   export ANTHROPIC_API_KEY="your-api-key"
   ```

3. **配置你的 MCP 宿主（如 Claude Desktop）：**
   打开对应的 JSON 配置文件（例如 `claude_desktop_config.json`），并在 `mcpServers` 下方添加注入节点：
   ```json
   "mcpServers": {
     "personal-memory": {
       "command": "C:/绝对路径/.../exobrain-mcp/.venv/Scripts/python.exe",
       "args": [
         "C:/绝对路径/.../exobrain-mcp/server.py"
       ],
       "env": {
         "ANTHROPIC_API_KEY": "your-api-key"
       }
     }
   }
   ```
   > ⚠️ **重要**：`command` 必须指向虚拟环境（`.venv`）里的 Python，而不是系统全局 Python，否则 `sentence-transformers` 将无法被加载，语义搜索会静默降级为纯关键词搜索。

4. **重启并体验：**
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
