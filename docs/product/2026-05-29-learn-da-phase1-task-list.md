# Learn DA 第一阶段实施任务清单 v1

面向 `Pandas / SQL -> Polars / DuckDB` 迁移学习者

## 使用方式

这份清单面向 claude code 执行，目标不是一次性大改，而是按阶段完成可验证的小步迭代。建议每完成一个任务块就做一次人工审查，再进入下一块。

建议执行顺序：

1. 首页与学习入口
2. 课程与 Playground 闭环
3. Agent 辅导化
4. 完成态与体验收口

## 阶段 0：执行前基线检查

### Task 0.1 盘点现有页面与数据来源

目标：
确认首页、学习页、课程详情页、Playground、Agent 面板当前依赖的组件、状态和接口边界。

建议检查文件：

- `learn_da_vue/src/views/Home.vue`
- `learn_da_vue/src/views/Learning.vue`
- `learn_da_vue/src/views/LessonDetail.vue`
- `learn_da_vue/src/views/Playground.vue`
- `learn_da_vue/src/components/agent/AgentPanel.vue`
- `learn_da_vue/src/stores/localState.ts`
- `learn_da_vue/src/stores/playground.ts`
- `learn_da_vue/src/lib/learningTracks.ts`
- `learn_da_vue/src/api/learning.ts`
- `learn_da_vue/src/api/agent.ts`

验收：

- 明确哪些改动只涉及前端文案和交互
- 明确哪些改动需要补接口或补内容字段
- 形成最小改动策略，避免一上来大面积重构

### Task 0.2 建立实现边界

目标：
确保第一阶段不被非主线需求稀释。

执行约束：

- 不新增登录注册
- 不改成复杂后端持久化方案
- 不引入新的大型 UI 框架
- 不做全站视觉重构
- 优先复用现有 learning / playground / agent 结构

验收：

- 实施范围明确
- 每个后续任务都能对齐“学习闭环”目标

## 阶段 1：首页与学习入口

### Task 1.1 首页定位文案收敛

目标：
让首页首屏明确表达“这是给 Pandas / SQL 迁移学习者的产品”。

建议修改文件：

- `learn_da_vue/src/views/Home.vue`
- `learn_da_vue/src/lib/learningTracks.ts`

执行内容：

- 重写 Hero 标题、副标题和主 CTA
- 弱化泛平台表达，强化迁移场景
- 增加“我会 Pandas / 我会 SQL / 我都熟”三类起步引导

验收：

- 用户打开首页 10 秒内能理解目标人群
- 首屏 CTA 能直接进入推荐路径

### Task 1.2 首页学习路径区块改造

目标：
把原本偏内容展示的路径卡片改成“迁移路径卡片”。

建议修改文件：

- `learn_da_vue/src/views/Home.vue`
- `learn_da_vue/src/lib/learningTracks.ts`

执行内容：

- 每张卡片增加“适合谁”“你将获得什么”“推荐起点”
- 课程数之外，增加预计耗时或推荐起步课
- 路径命名统一为迁移导向表达

验收：

- 三条路径的区别一眼可理解
- 用户知道每条路径的预期收益

### Task 1.3 学习页从“内容库”调整为“路径入口”

目标：
让 Learning 页默认承担“帮用户选学习路线”的职责。

建议修改文件：

- `learn_da_vue/src/views/Learning.vue`
- `learn_da_vue/src/lib/learningTracks.ts`
- `learn_da_vue/src/types/api.ts`

执行内容：

- 在列表上方增加路径说明区块
- 默认强调推荐路径，而不是单纯筛选器
- 调整分类文案，使其体现迁移关系

验收：

- 用户进入 Learning 页后，不需要搜索也能开始学习
- 页面默认信息架构优先服务“路径选择”

### Task 1.4 课程卡片文案语义增强

目标：
让课程卡片更像“迁移任务”，不是普通文章列表。

建议修改文件：

- `learn_da_vue/src/views/Learning.vue`
- 如需要则扩展 `learn_da_vue/src/types/api.ts`
- 如需要则调整后端 lesson summary 字段来源

执行内容：

- 在课程卡片中增加迁移收益描述
- 补充“学完你能做什么”的短句
- 保留难度、耗时，但提升任务导向表达

验收：

- 用户看到卡片时能快速判断是否适合自己
- 课程列表不再只是静态目录感

## 阶段 2：课程与 Playground 闭环

### Task 2.1 统一课程页结构

目标：
让每节课都遵循一致的学习模板。

建议修改文件：

- `learn_da_vue/src/views/LessonDetail.vue`
- `learn_da/content/lessons/*.md`
- `learn_da/app/learning/service.py`
- `learn_da/app/learning/schemas.py`

执行内容：

- 给课程内容补充统一结构块
- 增加迁移问题、核心概念、对比说明、练习任务、下一步建议
- 优先先改 3 到 5 节样板课，而不是一次性重写全部内容

验收：

- 至少一条路径的前几节课结构一致
- 用户读课时知道本课目标和学后收益

### Task 2.2 强化课程到 Playground 的操作链路

目标：
把“看示例”变成“立即动手练”。

建议修改文件：

- `learn_da_vue/src/views/LessonDetail.vue`
- `learn_da_vue/src/views/Playground.vue`
- `learn_da_vue/src/stores/playground.ts`
- `learn_da_vue/src/stores/localState.ts`

执行内容：

- 优化“加载代码”按钮文案与反馈
- 增加从课程进入 Playground 的明确入口
- 保证按 lesson slug 保存草稿的体验稳定

验收：

- 用户从课程内容到运行代码不超过 1 到 2 次点击
- 课程上下文和草稿上下文一致

### Task 2.3 为课程补最小练习动作

目标：
让每节课至少有一个“我可以自己动手改”的练习点。

建议修改文件：

- `learn_da/content/lessons/*.md`
- 必要时调整 lesson detail 渲染逻辑

执行内容：

- 给样板课补练习说明
- 练习动作应足够小，避免变成作业系统
- 优先围绕修改筛选、排序、聚合、连接、SQL 改写等高频迁移动作

验收：

- 每节样板课至少包含一个具体可执行练习
- 用户不需要自己想“接下来改什么”

### Task 2.4 课程结束后的下一步引导

目标：
解决“这节课学完了，然后呢”。

建议修改文件：

- `learn_da_vue/src/views/LessonDetail.vue`
- `learn_da_vue/src/views/Playground.vue`
- `learn_da_vue/src/stores/localState.ts`

执行内容：

- 课程底部增加下一课推荐
- 增加“去 Playground 自己练”和“让 AI 出一道小练习”入口
- 若已有上一课 / 下一课字段，充分利用

验收：

- 用户完成一课后至少有 2 个明确下一步动作
- 路径连续性可感知

## 阶段 3：Agent 辅导化

### Task 3.1 收敛 Agent 的角色定位

目标：
把 Agent 从泛聊天面板收敛为课程内辅导员。

建议修改文件：

- `learn_da_vue/src/components/agent/AgentPanel.vue`
- `learn_da_vue/src/api/agent.ts`
- `learn_da/app/agent/prompts.py`
- `learn_da/app/agent/service.py`
- `learn_da/app/agent/schemas.py`

执行内容：

- 重写欢迎语、空状态、快捷操作文案
- 快捷操作围绕“解释代码 / 修复错误 / 对比迁移 / 生成小练习 / 下一步”
- 提示词明确面向迁移学习者，而非泛编程助手

验收：

- 用户一眼知道 Agent 是来辅导当前课程的
- 默认快捷操作覆盖高频学习卡点

### Task 3.2 强化上下文注入

目标：
让 Agent 对当前课程、当前代码、当前错误更敏感。

建议修改文件：

- `learn_da_vue/src/views/Playground.vue`
- `learn_da_vue/src/components/agent/AgentPanel.vue`
- `learn_da_vue/src/types/api.ts`
- `learn_da/app/agent/service.py`

执行内容：

- 检查并补齐当前课程标题、课程分类、当前代码、stdout、stderr 等上下文
- 确保快捷操作默认带上这些上下文
- 必要时在后端 prompt 中明确使用这些字段

验收：

- 同一个问题在不同课程场景下，回答有明显差异
- 出错修复建议能引用当前报错和当前代码

### Task 3.3 增加迁移型快捷能力

目标：
让 Agent 的优势直接服务目标用户。

建议修改文件：

- `learn_da_vue/src/components/agent/AgentPanel.vue`
- `learn_da/app/agent/tools.py`
- `learn_da/app/agent/service.py`

执行内容：

- 增加 Pandas -> Polars 迁移解释
- 增加 SQL -> DuckDB 写法提示
- 增加“根据当前课出一道小练习”

验收：

- Agent 的亮点与目标用户强相关
- 回答更有“迁移训练”味道

## 阶段 4：完成态与体验收口

### Task 4.1 学习完成反馈

目标：
让完成一课有最基础的正反馈。

建议修改文件：

- `learn_da_vue/src/views/LessonDetail.vue`
- `learn_da_vue/src/stores/localState.ts`

执行内容：

- 保留并强化已完成状态
- 在课程页底部显示“你已完成本课”
- 给出下一课或推荐动作

验收：

- 用户能看到自己完成了什么
- 完成后的继续学习入口清晰

### Task 4.2 学习页轻量进度可视化

目标：
让路径学习状态有可见性，但不做复杂系统。

建议修改文件：

- `learn_da_vue/src/views/Learning.vue`
- `learn_da_vue/src/stores/localState.ts`
- `learn_da_vue/src/lib/learningTracks.ts`

执行内容：

- 显示每条路径已完成课程数
- 显示继续学习入口
- 若用户有最近访问课程，突出“继续学习”

验收：

- 用户返回 Learning 页时能迅速回到之前进度
- 页面能体现出“你正在学习中”

### Task 4.3 错误提示、空状态与微交互优化

目标：
把体验从“能用”打磨到“顺手”。

建议修改文件：

- `learn_da_vue/src/views/Learning.vue`
- `learn_da_vue/src/views/LessonDetail.vue`
- `learn_da_vue/src/views/Playground.vue`
- `learn_da_vue/src/components/agent/AgentPanel.vue`

执行内容：

- 统一空状态语气
- 优化失败提示和重试入口
- 优化加载代码、复制代码、运行结果切换等反馈

验收：

- 常见失败场景下用户知道下一步怎么做
- 页面反馈更一致

## 建议交付节奏

建议分 4 轮交付给 claude code：

1. 第一轮：只做首页与 Learning 页
2. 第二轮：只做课程 / Playground 闭环
3. 第三轮：只做 Agent 辅导化
4. 第四轮：只做完成态和体验收口

每轮结束都要求：

- 提供改动摘要
- 提供实际修改文件列表
- 提供验证方式
- 说明是否引入了新的技术债

## 最终验收问题

在第一阶段结束时，用下面 6 个问题验收：

1. 新用户进入首页后，是否能立刻知道这是给 Pandas / SQL 迁移学习者的？
2. 用户是否能快速找到适合自己的学习路径？
3. 用户是否能在课程中方便地进入 Playground 并运行示例？
4. 用户报错后，Agent 是否能结合当前上下文给出有帮助的回答？
5. 用户学完一课后，是否能明确知道下一步该做什么？
6. 整体产品是否体现为一个学习闭环，而不是几个分散功能的集合？
