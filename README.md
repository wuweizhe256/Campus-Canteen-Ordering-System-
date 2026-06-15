# 北京交通大学校园食堂就餐仿真系统

基于 PyQt6 的校园食堂就餐仿真桌面应用，用于模拟学生在食堂中的到达、选餐、排队、出餐、找座、就餐、回收餐盘和离场流程。系统通过实时画布展示窗口、餐桌、学生、路径与拥堵状态，并在右侧统计面板输出等待时间、队列、座位利用率、订单、菜品库存和通行效率等指标。

## 当前能力

- 实时仿真：支持开始、暂停、停止、时间倍率调整和仿真结果汇总。
- 可视化画布：展示学生状态、窗口状态、餐桌占用、入口出口、碗筷回收点、路径调试层和障碍物层。
- 学生行为：覆盖思考、前往窗口、排队、取餐、找座、等座、就餐、前往回收点、离场等状态。
- 窗口与菜品：从 `config/menu.json` 加载窗口、菜品、价格、库存、出餐时间和菜品特征。
- 座位系统：支持空闲、预留、占用三类座位状态，并支持 2 人桌、4 人桌、6 人桌。
- 同行行为：支持同行组生成、同桌优先分配和同行同桌率统计。
- 路径与避让：包含网格寻路、静态障碍、动态学生障碍、局部避让、卡住恢复和路径拥堵统计。
- 数据统计：记录事件流，并生成平均等待时间、平均就餐总耗时、最大在场人数、窗口队列、座位利用率、菜品销售、订单耗时、入口出口流量等指标。

## 环境要求

- Python 3.10
- PyQt6 >= 6.7, < 7

安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 运行应用

```bash
python main.py
```

启动后点击“开始仿真”，在配置弹窗中设置仿真时长、时间倍率、窗口数量、餐桌数量、学生数量等参数。运行过程中可以调整时间倍率、显示路径调试层、显示障碍物层、缩放或重置画布。

## 运行测试

```bash
python -m unittest discover -s tests
```

也可以运行开发自测脚本：

```bash
python scripts/backend_self_test.py
python scripts/test_data_recorder_p0.py
```

## 项目结构

```text
├── main.py                 # 应用入口
├── models/                 # 仿真模型、状态机、寻路、事件记录和统计
├── controllers/            # UI 与仿真 worker 的信号连接、线程生命周期管理
├── views/                  # PyQt6 主窗口、画布、配置弹窗、统计面板和信息弹窗
├── utils/                  # 字体、数学和通用工具函数
├── config/                 # 默认设置和菜单 / 菜品配置
├── assets/                 # 画布图片资源
├── tests/                  # 单元测试
├── scripts/                # 开发自测与辅助脚本
└── docs/                   # 业务逻辑、接口契约、测试计划和开发规范
```

## 关键配置

- `config/settings.json`：默认仿真参数，例如时长、时间倍率、窗口数量、餐桌数量、学生数量和最大同时在场人数。
- `config/menu.json`：窗口与菜品数据，包括菜品名称、特征、价格、库存和出餐时间。
- `models/entities.py`：核心实体、状态枚举和 `SimulationConfig` 配置结构。

## 文档导航

- `rule.md`：Git 协作流程、分支分工、提交信息规范和基础注意事项。
- `docs/development_guidelines.md`：开发规范、分层边界、状态机、接口和统计口径约定。
- `docs/business_logic_draft.md`：业务逻辑、对象模型、状态流转和阶段性规划。
- `docs/realtime_frame_interface.md`：后端输出给前端的实时 `frame` 数据契约。
- `docs/frontend_backend_integration_test_plan.md`：前后端独立测试与联调测试方案。

## 主要技术路线

项目采用接近 MVC 的组织方式：

- `models` 负责仿真推进、实体状态、路径规划、订单、事件记录和统计。
- `views` 只消费实时 `frame` 数据，负责绘制、弹窗和用户交互。
- `controllers` 管理 PyQt 信号、仿真线程启动停止和运行时状态同步。

实时数据边界是后端输出的 `frame` 字典。新增或修改展示字段时，应同步更新 `docs/realtime_frame_interface.md`，并补充对应测试。
