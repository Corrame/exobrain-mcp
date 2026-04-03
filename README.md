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

本系统暴露了对大模型极其友好的 **5 个**函数接口，大幅降低 AI 操作数据库的认知负担（无需写 SQL）：

| 工具 | 功能 |
|---|---|
| `remember` | **存一切**——用户原话、AI观察、任何文本，**自动分析情感坐标**（Valence/Arousal）和主题域 |
| `add_task` | 捕获交办指令，自动录入轨一并映射为轨二待办任务，支持**任务树层级**（`parent_task_id`）、**优先级**（`priority`）和**工作量评估**（`effort_estimate`） |
| `update_task` | 更新任务进度（完成/废弃）、附加元数据标签，或两者同时进行 |
| `recall` | **混合检索**：关键词匹配 + 语义向量搜索 + **情感权重排序**。如果 query 为空，自动浮现当前权重最高的 **Top 3** 高唤醒度记忆 |
| `suggest` | 查询待办任务，后端算法自动按优先级打分、按空闲时间过滤，返回精准的下一步行动建议 |

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

- 高唤醒度记忆衰减慢，更容易被 `recall()` （空 query）在对话开头浮现
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

## 📂 数据存储与备份策略

### 踩坑经验：代码公开 vs 数据私密

本项目是一个**开源项目**（代码公开），但你的记忆数据（`exobrain.db`）是**极度私密的**。

**问题场景：**
> 你想 fork 这个项目改进代码并贡献回社区，但你的数据库里存着"昨天和 AI 聊的情感问题"、"明天的待办清单"、"你的个人偏好"...

**错误做法：**
- 把数据库提交到公开仓库 → 隐私泄露
- 把本地路径硬编码进代码 → 换机器失效

**正确做法：**

#### 方案 1：快速开始（单机使用）
```bash
git clone https://github.com/Corrame/exobrain-mcp.git
cd exobrain-mcp
# 直接运行，数据库自动创建在项目目录下
# .gitignore 已屏蔽 *.db，不会误提交
```

**适合：** 试用、数据不敏感、单机使用

#### 方案 2：生产部署（代码与数据分离）
**推荐用于长期使用、多设备同步、数据备份需求**

1. **Fork 公开仓库**（用于代码贡献和改进）
   ```bash
   git clone https://github.com/<你的账号>/exobrain-mcp.git
   ```

2. **创建私有仓库**（仅用于备份数据）
   ```bash
   # 在 GitHub 上新建私有仓库，例如：my-exobrain-data
   git clone https://github.com/<你的账号>/my-exobrain-data.git
   ```

3. **配置数据路径**
   
   复制 `.env.example` 为 `.env`：
   ```bash
   cp .env.example .env
   ```
   
   编辑 `.env` 文件：
   ```env
   MEMORY_DB_PATH=/path/to/my-exobrain-data/exobrain.db
   ```
   
   或者在启动时设置环境变量：
   ```powershell
   # Windows
   $env:MEMORY_DB_PATH="C:\Users\<用户名>\Documents\my-exobrain-data\exobrain.db"
   
   # Linux/Mac
   export MEMORY_DB_PATH="/home/<用户名>/my-exobrain-data/exobrain.db"
   ```

4. **启动服务**
   ```bash
   python server.py
   # 数据库现在存储在私有仓库目录下
   ```

**架构说明：**
- `exobrain-mcp/` —— 公开仓库，存放代码，随时可以 pull 上游更新
- `my-exobrain-data/` —— 私有仓库，存放 `exobrain.db` 和配置文件
- `.env` —— 本地配置文件（已被 `.gitignore` 保护，不会提交）

**备份策略：**
```bash
# 定期提交数据变更
cd my-exobrain-data
git add exobrain.db
git commit -m "backup: $(date)"
git push origin main
```

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
