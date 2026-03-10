# Personal AI Cognitive Exobrain (MCP) 🧠

这是一个基于 **Model Context Protocol (MCP)** 的个人认知外脑服务器。它能为你的大语言模型（如 Claude Desktop、Cursor、VS Code 插件等）赋予**长期的、结构化的真实记忆**。

## 🌟 为什么需要它？（痛点直击）

现在的 AI 模型在处理用户的长期记忆时，常常存在两个致命缺陷：
1. **上下文遗忘（爆内存）**：大模型无法把你一生的聊天记录常驻内存，传统的记忆体往往会导致上下文长度爆炸。
2. **信息的“有损压缩”**：当你说“我想买两箱纯牛奶”时，现在的 AI 可能会把它自作主张地存成 `Task: 买牛奶, Category: 生活`，完全丢失了你说话时的语意和感情色彩。这种死板的结构化数据会导致未来更聪明的人工智能无法追溯你的原始意图。

**我们的解法：双轨制架构 (Dual-Track Architecture)**
*   **轨一：潜意识/黑匣子（Immutable Raw Input Log）**：只允许追加（Append Only）。你的每一句原话都会作为“绝对真理”被永久保存在 SQLite 数据库中。
*   **轨二：结构化投影（Projected Structural View）**：为了方便当前的 AI 帮你管理日常事务（比如待办列表），它会动态从“轨一”生成这一层的任务数据。即使 AI 偶尔标错了分类，或者你想重构任务体系，这层“脏缓存”也可以随时删库重建，因为**你的原话永远在轨一里安全保存着。**

---

## 🛠 给 AI 的高内聚语义工具 (MCP Tools)

本系统暴露了对大模型极其友好的函数接口，大幅降低 AI 操作数据库的认知负担（无需写 SQL）：

*   **`record_thought_or_fact`**：记录你的随想、偏好或事实到“不可改变的真理层”。
*   **`add_actionable_task`**：捕获你的交办指令，自动录入轨一并映射为轨二的待办任务。
*   **`update_task_status`**：更新任务进度或废弃任务。
*   **`recall_past_mentions_of`**：支持模糊查询你过往提到的某个关键词或实体。
*   **`suggest_next_actions`**：由于计算和排序交由系统后端处理，AI 拿到的是精简好的任务列表，再结合你当前的空闲时间，能极其准确地回答“我现在该干点啥”的问题。

---

## 🚀 安装与部署

我们将指引你，或者你的 AI 助手，如何将这个认知外脑连接到你的 MCP 生态中。

### 选项 A：让你的 AI 帮你全自动安装（最赛博朋克的推荐！）
如果你正在使用具有 Agent 能力的 IDE（如 Cursor / Cline / Antigravity）：
1. 将本项目 clone 到本地。
2. 直接向你的 AI 发送指令：**“请阅读目录下的 `INSTALL-MCP.md`，并帮我自动安装这个 MCP 服务。”**
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
   *(注意：请务必将以上路径替换为你本机真实的**绝对路径**。)*

3. **重启并体验：**
   保存配置并重启你的 Client（比如重启 Claude Desktop），并在对话框里试着说出：*“我非常讨厌吃香菜，无论如何都要记住这一点。”* 然后看看你的认知外脑如何为你工作！

---
**从普通的 LLM 到通用人工智能 (AGI)，系统需要数字灵魂的缓存。祝你和你的 AI 合作愉快！**
