# 后端逻辑梳理

本文档用于按“文件 + 行号 + 类/函数职责 + 实现方式 + 可疑点”理解当前后端仿真逻辑。这里的“后端”指 `models/` 下的仿真、数据、寻路模块，加上 `utils/helpers.py` 和 `controllers/main_controller.py` 中负责调度仿真 worker 的边界代码。

本文档只解释现有实现，不设计 B/S 迁移，不修改业务逻辑。

## 1. 总览

### 当前架构

当前代码不是干净的纯 Python 仿真核心。`models/simulation_engine.py` 中的 `SimulationWorker` 同时承担两类职责：

- Qt worker：继承 `QObject`，通过 `pyqtSignal` 和 `QThread` 与 PyQt 界面通信。
- 仿真引擎：维护学生、窗口、桌子、订单、路径、统计和实时帧。

主数据流如下：

```text
MainWindow -> MainController -> SimulationWorker.run()
  -> _spawn_due_students()
  -> _complete_ready_food()
  -> _update_students()
  -> _separate_students()
  -> _build_frame()
  -> frameReady.emit(frame)
```

### 当前后端文件分工

| 文件 | 行数 | 主要职责 |
| --- | ---: | --- |
| `models/entities.py` | 248 | 状态枚举、配置、学生、窗口、菜品、订单、座位、餐桌等数据模型 |
| `models/simulation_engine.py` | 1613 | 仿真主循环、状态推进、路径、排队、出餐、找座、统计采样、frame 输出 |
| `models/data_recorder.py` | 893 | 事件记录、事件索引、统计指标计算 |
| `models/pathfinding.py` | 259 | 粗网格 A* 寻路、障碍物、门洞、拥堵成本 |
| `utils/helpers.py` | 36 | 数值裁剪、距离、移动一步等数学工具 |
| `controllers/main_controller.py` | 83 | PyQt 线程创建、信号槽连接、worker 生命周期管理 |

## 2. 数据模型

### `models/entities.py:7-30` 状态枚举

**负责什么**

定义学生、窗口、订单的有限状态值，是仿真状态机和前端展示状态的共同基础。

**怎么实现**

- `StudentState` 定义学生从思考、去排队、排队、找座、就餐、回收餐具到离场的状态。
- `StallStatus` 定义窗口待营业、营业中、售罄。
- `OrderStatus` 定义订单排队、制作中、完成、取消。

**输入**

无外部输入，是固定枚举。

**输出/副作用**

这些枚举值会出现在 `Student`、`Stall`、`Order` 对象中，也会通过 `_build_frame()` 输出给前端。

**疑点**

`OrderStatus.CANCELLED` 已定义，但当前仿真主流程里几乎没有实际取消订单路径。

### `models/entities.py:33-84` `SimulationConfig`

**负责什么**

定义一次仿真的配置参数，包括时长、时间倍率、窗口数、餐桌数、偏好权重、库存、同行比例、入口出口、随机种子、学生数量等。

**怎么实现**

- `duration_game_seconds` 把分钟转为仿真秒。
- `duration_real_seconds` 用仿真秒除以时间倍率，计算理论真实运行时间。
- `resolved_table_type_counts()` 根据显式 2/4/6 人桌数量或总桌数推导桌型分布。

**输入**

来自配置弹窗或测试代码构造的 `SimulationConfig`。

**输出/副作用**

被 `SimulationWorker` 初始化和运行过程中读取。

**疑点**

部分字段当前可能没有真正参与仿真决策，尤其是 `dish_preference_weight`、`price_weight`、`default_dish_stock`、`low_stock_threshold`、`entrance_count`、`exit_count`。例如入口和出口的实际构建逻辑使用固定列表，不直接按 `entrance_count`、`exit_count` 截断。

### `models/entities.py:87-134` `Student`

**负责什么**

表示一个学生实体，保存其位置、目标、偏好、状态、订单、同行、座位、路径和拥堵相关运行状态。

**怎么实现**

- `x/y` 是当前位置，`target_x/target_y` 是移动目标。
- `state` 表示学生当前业务阶段。
- `preferences` 保存多维偏好，如荤素、价格敏感度、等待容忍度、辣度等。
- `path` 保存当前剩余路径点。
- `actual_speed`、`stuck_time`、`reroute_count` 用于拥堵和重规划统计。
- `eating_time` 用 `appetite / eat_speed` 推导就餐时长。

**输入**

主要由 `SimulationWorker._build_student()` 创建。

**输出/副作用**

学生对象会被 `_update_students()` 持续修改，也会被 `_student_frame()` 序列化到实时帧。

**疑点**

`last_x/last_y` 存在但当前主要移动逻辑中实际价值有限。学生字段较多，说明实体承载了业务状态、运动状态和统计状态，后续若重构可以拆分。

### `models/entities.py:137-201` `Stall`、`Dish`、`Order`

**负责什么**

描述窗口、菜品和订单。

**怎么实现**

- `Stall.queue` 保存排队学生 ID。
- `Stall.ready_times` 保存 `(student_id, ready_at, order_id)`，用于判断何时出餐。
- `Stall.orders` 保存订单对象。
- `Dish.available` 用库存是否大于 0 判断是否可售。
- `Order` 记录学生、窗口、菜品、创建时间、开始时间、完成时间和状态。

**输入**

窗口和菜品由 `_build_stalls()`、`_build_stall_dishes()` 创建；订单由 `_join_stall_queue()` 创建。

**输出/副作用**

出餐时会减少 `Dish.stock`，刷新 `Stall.status`，更新 `Order.status`。

**疑点**

窗口既有 `ready_times` 又有 `orders`，两套结构共同描述出餐队列，存在状态不同步风险。`Stall.cook_time` 和菜品级 `Dish.cook_time` 并存，实际出餐主要使用菜品 cook time。

### `models/entities.py:204-248` `Seat`、`Table`、`RunSummary`

**负责什么**

描述座位、餐桌和仿真结束摘要。

**怎么实现**

- `SeatStatus` 区分空闲、预留、占用。
- `Table.__post_init__()` 根据 `seat_count` 自动创建座位。
- `free_seat_indexes()` 返回空闲且没有学生 ID 的座位索引。
- `occupied_count` 只统计 `OCCUPIED` 座位，不统计 `RESERVED`。
- `RunSummary` 保存结束状态、时间、生成数、服务数和场内人数。

**输入**

餐桌由 `_build_tables()` 创建，座位状态由找座和就餐流程修改。

**输出/副作用**

餐桌和座位状态会被 `_build_frame()` 输出到 `tables` 和 `seat_frames`。

**疑点**

`occupied_count` 不包含已预留座位，前端若只看 `occupied` 会低估已经被锁定但学生未到达的座位。

## 3. 仿真主引擎

### `models/simulation_engine.py:30-125` `SimulationWorker` Qt 壳和运行循环

**负责什么**

把仿真跑在 PyQt worker 中，负责启动、暂停、停止、调时间倍率和向 UI 推送帧。

**怎么实现**

- 类继承 `QObject`。
- 定义 `frameReady`、`statusChanged`、`finished`、`errorOccurred` 四个 Qt 信号。
- `run()` 初始化场景后进入循环。
- 每轮用真实时间差乘以 `time_scale` 得到 `game_delta`。
- 每轮推进学生生成、出餐、学生状态、拥堵分离，然后发出 `_build_frame()`。
- 用 `QThread.msleep(16)` 控制近似 60 FPS。

**输入**

`SimulationConfig`、Qt 线程启动信号、暂停/停止/倍率信号。

**输出/副作用**

持续修改 worker 内部状态；向 PyQt UI 发状态、帧、结束摘要或错误。

**疑点**

仿真核心与 PyQt 强耦合，导致后端逻辑测试需要 PyQt6。若迁移 B/S，建议先拆出纯 Python `SimulationEngine.step(game_delta)`。

### `models/simulation_engine.py:126-259` 初始化布局

**负责什么**

构建一次仿真的静态空间和初始运行状态，包括入口、出口、窗口、餐桌、回收点和数据记录器。

**怎么实现**

- `_initialize()` 调用各类 `_build_*` 函数，清空学生、重置时间和计数器。
- `_build_entrances()` 基于固定位置和 `entrance_weights` 构造入口。
- `_build_exits()` 创建三个固定出口。
- `_build_stalls()` 按 `stall_count` 在上方横向铺开窗口。
- `_build_stall_dishes()` 为每个窗口生成三个菜品，带特征、价格、库存、出餐时间。
- `_build_tables()` 按桌型配置生成网格餐桌。
- `_build_tray_return_points()` 生成一个固定回收点。

**输入**

`SimulationConfig`、随机数生成器、固定画布尺寸和布局常量。

**输出/副作用**

填充 `entrances`、`exits`、`stalls`、`tables`、`tray_return_points`，重置 `DataRecorder`。

**疑点**

布局大量写死在引擎中，不是配置文件驱动。`entrance_count`、`exit_count` 未直接控制入口/出口数量。`default_dish_stock` 没有传入菜品生成逻辑，库存使用随机值。

### `models/simulation_engine.py:261-426` 学生生成、同行组和注册事件

**负责什么**

按仿真进度生成学生，支持独行、二人同行和多人同行，并记录学生入场事件。

**怎么实现**

- `_spawn_due_students()` 根据目标生成数、总人数限制和最大在场人数限制计算本轮应生成多少人。
- `_target_spawned_students()` 使用前慢后慢、中间快的曲线控制生成节奏。
- `_choose_group_size()` 根据同行比例随机决定组大小。
- `_spawn_group()` 为同组学生共享偏好和同一目标菜品/窗口。
- `_choose_entrance()` 根据入口权重和入口附近密度选择入口。
- `_build_student()` 创建学生并设置初始位置、目标点、速度、偏好和决策完成时间。
- `_register_student()` 保存学生，更新生成数和入口流量计数，记录 `student_spawned` 事件。

**输入**

当前时间、配置中的学生数量和同行比例、入口列表、窗口/菜品状态。

**输出/副作用**

向 `students` 字典加入学生，递增 ID 和生成计数，记录入场事件。

**疑点**

`entrance_flow_counts` 会递增，但 `DataRecorder` 没有记录 `entrance_used` 事件，因此 `frame.stats.entrance_flow` 可能为空。同行组创建也没有记录 `group_created` / `group_member_joined` 事件，统计里的同行完成率依赖事件时会不足。

### `models/simulation_engine.py:428-529` 菜品/窗口选择和排队容量

**负责什么**

为学生选择菜品和窗口，判断菜品是否还能接单。

**怎么实现**

- `_choose_best_stall()` 是兼容式入口，最终调用 `_choose_dish_and_stall()`。
- `_choose_dish_and_stall()` 先遍历全场菜品，按学生偏好选菜，再在提供该菜品且有容量的窗口中选综合成本最低的窗口。
- `_dish_preference_cost()` 用口味差异、价格敏感度和随机扰动计算菜品成本。
- `_stall_choice_cost()` 综合队列长度、距离、走廊密度、窗口拥堵、出餐时间、价格和随机扰动。
- `_dish_has_order_capacity()` 用库存减去待处理订单数判断还能否接单。

**输入**

学生偏好、窗口队列、菜品库存、订单状态、学生当前位置和周边密度。

**输出/副作用**

返回 `(dish_id, stall_id)`，本段通常不直接修改状态。

**疑点**

配置里的 `dish_preference_weight`、`price_weight` 没有参与成本计算。选择过程中有随机扰动，固定 seed 可复现，但同样场景的解释性会下降。

### `models/simulation_engine.py:531-632` 学生生命周期状态机

**负责什么**

推进学生从思考到离场的完整主流程。

**怎么实现**

- `_complete_ready_food()` 先处理已经完成出餐的订单，把学生转为 `SEARCHING_SEAT`。
- `_update_students()` 按学生当前 `state` 分支处理：
  - `DECIDING`：等待决策时间，结束后转向窗口。
  - `MOVING_TO_QUEUE`：移动到队列目标，到达后加入窗口队列。
  - `QUEUED`：跟随队列目标移动。
  - `SEARCHING_SEAT` / `WAITING_SEAT`：寻找座位或等座。
  - `MOVING_TO_SEAT`：到座后占用座位并开始就餐。
  - `EATING`：吃完后释放座位，前往回收点。
  - `MOVING_TO_TRAY_RETURN`：到达回收点后转向出口。
  - `LEAVING`：到达出口后标记 `DONE` 并从活跃学生中移除。

**输入**

当前学生列表、`game_delta`、窗口出餐时间、座位状态、路径和空间判断函数。

**输出/副作用**

修改学生状态、位置、座位状态、订单状态、计数器，并记录 `food_ready`、`eating_started`、`eating_finished`、`student_left` 等事件。

**疑点**

`served_students` 在学生吃完并前往回收点时递增，不是离场时递增。回收点到达没有独立事件，只能通过状态变化推断。若学生一直无座，缺少明确最大等待或放弃机制。

### `models/simulation_engine.py:634-740` 窗口队列、订单创建和订单刷新

**负责什么**

处理学生进入窗口队列、创建订单、设置出餐时间、刷新订单状态。

**怎么实现**

- `_queue_target_position()` 根据学生在窗口队列中的 index 计算排队点。
- `_start_queue_path()` 为去窗口阶段规划路径。
- `_set_queue_target()` 让排队学生跟随队列位置移动。
- `_join_stall_queue()` 检查目标窗口和菜品，必要时重选；创建 `Order`，追加到 `stall.orders` 和 `stall.ready_times`，把学生转为 `QUEUED`。
- `_refresh_orders_and_stalls()` 把到达开始时间的订单从 `QUEUED` 改成 `COOKING`，并刷新窗口售罄状态。

**输入**

学生目标窗口/菜品、窗口队列、当前仿真时间、菜品库存。

**输出/副作用**

创建订单、更新窗口队列、学生订单 ID 和学生状态，记录 `queue_started` 事件。

**疑点**

创建订单时没有记录 `order_created` 事件，订单开始和完成也没有记录 `order_started`、`order_completed`。因此 `DataRecorder` 的订单统计能力在实际仿真中可能拿不到数据。

### `models/simulation_engine.py:742-879` 找座、预留、占用、释放和同行座位偏置

**负责什么**

为拿到餐的学生选择座位，处理座位预留、就座和离座。

**怎么实现**

- `_send_student_to_table()` 收集所有空座；没有空座就转为 `WAITING_SEAT` 并去等待点。
- `_best_seat_candidate()` 为每个候选座位计算综合评分，包括路程、桌旁密度、距离回收点、已占用座位数、同行偏置和随机扰动。
- `_group_seat_bias()` 优先让同组成员坐同桌或相邻座位。
- `_occupy_reserved_seat()` 到达后把预留座位改成占用。
- `_release_seat()` 吃完后释放座位。
- `_seat_position()` 和 `_seat_offsets()` 根据桌型和座位索引计算座位坐标。

**输入**

学生位置、桌子和座位状态、同行关系、路径规划函数。

**输出/副作用**

修改学生 `table_id` / `seat_index` / `table_walk_speed` / `state`，修改座位状态和学生 ID。

**疑点**

座位分配没有记录 `seat_assigned` 事件，桌型注册也没有记录 `table_type_registered`，所以 `DataRecorder` 的同行和桌型利用率统计可能无法从实际仿真事件中完整计算。

### `models/simulation_engine.py:881-1314` 出口、回收点、路径规划、移动、避障和重规划

**负责什么**

处理学生在空间中的路径、移动、出口选择、回收点路径、拥堵检测和重规划。

**怎么实现**

- `_set_exit_path()` 根据 `_choose_exit()` 选择出口，并规划路径。
- `_choose_exit()` 以距离和出口局部密度综合选择出口。
- `_set_tray_return_path()` 选择最近回收点并规划路径。
- `_build_navigation_path()` 每次创建 `GridPathFinder`，使用障碍物、门洞和拥堵点规划路径。
- `_navigation_obstacles()` 从窗口、桌子、墙体生成障碍物。
- `_move_student()` 按速度向目标移动，遇到不可走点尝试重规划，更新实际速度、朝向、卡住时间。
- `_separate_students()` 检测学生之间过近或卡住，累计拥堵时间，必要时调用 `_try_start_detour()`。
- `_try_start_detour()` 优先重规划，失败时尝试插入侧向绕行点。
- `_is_static_walkable_point()`、`_is_inside_exit()`、`_is_inside_tray_return()` 判断空间位置合法性和是否到达区域。

**输入**

学生位置、目标、速度、障碍物、出口/入口/回收点、其他学生位置。

**输出/副作用**

修改学生位置、路径、目标、朝向、实际速度、拥堵时间、重规划次数和出口 ID。

**疑点**

路径规划每次都重新创建 `GridPathFinder`，学生多时可能有性能压力。`_avoid_static_obstacles()` 定义后当前未在主循环中调用。出口流量有 `exit_flow_counts`，但未记录 `exit_used` 事件，因此 `DataRecorder` 的出口流量统计可能为空。

### `models/simulation_engine.py:1316-1372` 事件记录和运行时统计采样

**负责什么**

把学生事件、队列长度和运行时指标送入 `DataRecorder`。

**怎么实现**

- `_record_student_event()` 构造 `EventRecordP0`，记录学生 ID、窗口、餐桌、座位、状态变化。
- `_record_queue_samples()` 每帧记录每个窗口当前队列长度。
- `_record_runtime_sample()` 计算平均移动速度、拥堵指数、卡住人数、重规划次数、平均队列长度、回收点等待人数。

**输入**

当前学生、窗口、队列、路径和运行时间。

**输出/副作用**

向 `DataRecorder.events`、`queue_samples`、`runtime_samples` 追加数据。

**疑点**

`_record_student_event()` 只记录了部分字段，缺少 dish/order/group/entrance/exit/path/stock 等事件字段。`_record_queue_samples()` 和 `_record_runtime_sample()` 在 `_build_frame()` 内被调用，意味着读取 frame 会产生统计采样副作用。

### `models/simulation_engine.py:1374-1599` 实时 `frame` 输出结构

**负责什么**

把仿真内部状态转换成前端消费的字典。

**怎么实现**

- `_build_frame()` 先刷新订单和窗口状态，再记录队列与运行采样，然后调用 `data_recorder.build_stats()`。
- 顶层输出时间、时长、倍率、人数、入口出口、回收点、地图尺寸、统计、路径、障碍物、窗口、餐桌、学生。
- `_stall_frame()` 输出窗口位置、队列数、状态、菜品、订单、出餐进度。
- `_dish_frame()` 输出菜品特征、价格、库存、出餐时间和可售状态。
- `_order_frame()` 输出订单基础时间和状态。
- `_student_frame()` 输出学生位置、目标、路径、状态、偏好、订单、同行、入口出口、速度和重规划信息。
- `_build_walk_paths()` 构造前端调试用通道线。

**输入**

当前仿真对象全量状态。

**输出/副作用**

返回一个 `dict[str, Any]`，通过 `frameReady.emit(frame)` 交给 UI。

**疑点**

`_build_frame()` 不是纯序列化函数，它会写入统计采样。重复调用会增加样本数量，可能影响最大队列、运行时趋势等统计。`served_students` 字段名容易被理解为已离场人数，但当前是在吃完饭时递增。

### `models/simulation_engine.py:1601-1613` 底部辅助函数

**负责什么**

提供状态值转换和平均数计算。

**怎么实现**

- `_state_value()` 把 `StudentState` 或字符串统一转为字符串。
- `_average_float()` 把输入迭代器转成浮点列表并求平均。

**输入**

状态值、数字迭代器。

**输出/副作用**

返回字符串或平均值。

**疑点**

`_average_float()` 会立即展开所有值，当前数据量小问题不大。

## 4. 数据记录和统计

### `models/data_recorder.py:47-265` 事件和统计帧数据结构

**负责什么**

定义事件记录和所有统计结果的数据结构。

**怎么实现**

- `EventRecordP0` 是统一事件结构，包含学生、窗口、菜品、订单、同行、入口出口、路径、座位等字段。
- 多个 `*Stats` dataclass 定义队列、菜品销售、库存、桌型、流量、路径拥堵等统计结果。
- `StatsFrameP0` 是最终统计帧，`to_dict()` 把内部对象转成前端可消费的字典。
- `RuntimeStatsSample` 和 `QueueLengthSample` 保存运行时采样。

**输入**

来自仿真引擎的事件字典或 `EventRecordP0` 对象。

**输出/副作用**

为 `DataRecorder` 的索引和统计计算提供统一字段。

**疑点**

结构定义覆盖 P0/P1/P2/P3 很多能力，但仿真引擎实际记录的事件远少于这些字段能表达的内容。

### `models/data_recorder.py:266-399` 事件录入和索引

**负责什么**

把事件录入主列表，并按学生、窗口、菜品、订单、同行、桌型、入口、出口、路径、障碍物、座位建立索引。

**怎么实现**

- `record_event()` 接受 `EventRecordP0` 或字典。
- 不认识的 `event_type` 会写入 `issues` 并跳过。
- 根据事件字段是否存在，追加到不同索引字典。
- `record_queue_sample()` 和 `record_runtime_sample()` 分别记录队列长度和运行时指标。
- `student_events()`、`order_events()` 等查询函数返回排序后的事件列表。

**输入**

事件对象、事件字典、队列采样、运行时采样。

**输出/副作用**

修改 `events`、各类 `events_by_*` 索引、`queue_samples`、`runtime_samples`、`issues`。

**疑点**

这里能记录入口、出口、路径等事件，但 `SimulationWorker` 当前没有完整调用对应事件类型。

### `models/data_recorder.py:400-438` `build_stats()` 汇总入口

**负责什么**

把所有事件和采样汇总成一个 `StatsFrameP0`。

**怎么实现**

按事件时间排序后，调用各个私有统计函数：

- 等待时间、总耗时、最大在场人数。
- 窗口最大队列、座位利用率。
- 订单耗时、菜品销售、售罄、库存。
- 同行同桌率、桌型利用率。
- 入口/出口流量、路径拥堵。
- 最新运行时采样。

**输入**

`events`、`queue_samples`、`runtime_samples`、可选 `current_time`。

**输出/副作用**

返回 `StatsFrameP0`。内部统计函数可能向 `issues` 追加异常口径信息。

**疑点**

统计能力依赖事件完整性。若事件未记录，返回值可能为空、`None` 或 0，而不是说明业务没有发生。

### `models/data_recorder.py:439-806` 各类统计计算

**负责什么**

具体计算等待时间、总耗时、最大人数、队列、座位利用率、订单、同行、桌型、流量和路径指标。

**怎么实现**

- `_average_duration_by_student()` 用学生的起止事件求平均耗时。
- `_max_active_students()` 用 `student_spawned` 加、`student_left` 减统计最大在场人数。
- `_stall_queue_stats()` 优先使用队列采样，没有采样才用事件推导。
- `_seat_utilization()` 用 `eating_started` 到 `eating_finished` 的占用时长除以总座位时长。
- `_dish_sales_stats()`、`_dish_sold_out_stats()`、`_dish_stock_stats()` 基于订单和库存事件计算菜品指标。
- `_order_timing_stats()` 基于 `order_created`、`order_started`、`order_completed`、`order_cancelled` 计算订单指标。
- `_group_table_stats()` 根据同行组座位分配判断是否同桌。
- `_table_type_utilization()` 按桌型统计座位占用时长。
- `_flow_stats()` 统计入口/出口事件数量。
- `_path_congestion_stats()` 统计路径长度、时长、拥堵和阻塞样本。

**输入**

事件索引、队列采样、运行时采样、当前时间。

**输出/副作用**

返回各类统计对象或基本数值，发现负耗时、缺字段等情况会写入 `issues`。

**疑点**

实际仿真未完整记录订单、库存、同行、入口、出口、路径事件，因此这些高级统计可能无法反映真实运行。`_stall_queue_stats()` 一旦有队列采样，就完全不使用事件推导。

### `models/data_recorder.py:807-893` 统计工具函数

**负责什么**

提供事件排序、查找首个事件、查找已知字段、平均值、比例裁剪、默认座位数和可选类型转换。

**怎么实现**

- `_event_sort_key()` 使用事件时间和事件类型稳定排序。
- `_first_event()` 查找指定类型且满足最小时间的第一个事件。
- `_first_known_int()` / `_first_known_float()` 从事件列表中找字段值。
- `_average()`、`_bounded_ratio()` 做基础数学处理。
- `_optional_*()` 负责从字典构造事件时的类型转换。

**输入**

事件、字段名、数字列表或原始字典值。

**输出/副作用**

返回排序 key、事件、数值或 `None`。

**疑点**

辅助函数本身简单，主要风险来自上游事件缺失或字段口径不一致。

## 5. 路径规划和工具函数

### `models/pathfinding.py:14-42` 障碍物和门洞模型

**负责什么**

定义寻路时的矩形障碍物和可穿过墙体的门洞。

**怎么实现**

- `NavRect.contains()` 判断点是否落在矩形加安全距离范围内。
- `Doorway.contains()` 根据门洞所在边判断点是否在可通行区域。

**输入**

地图坐标点、障碍矩形、门洞参数、安全距离。

**输出/副作用**

返回布尔值，不修改状态。

**疑点**

门洞判断使用经验系数，和实际绘制区域是否完全一致需要联调验证。

### `models/pathfinding.py:44-99` `GridPathFinder` 初始化和坐标转换

**负责什么**

建立粗网格寻路空间，并提供点坐标和网格坐标之间的转换。

**怎么实现**

- 默认网格大小 `24.0`，安全距离 `14.0`。
- 根据地图宽高计算行列数。
- 保存障碍物、门洞、拥堵点。
- 初始化时预计算拥堵成本。
- `find_path()` 把起点和终点映射到最近可通行网格，执行 A*，最后平滑路径。

**输入**

地图宽高、障碍物、门洞、拥堵点、起点、终点。

**输出/副作用**

返回路径点列表。内部缓存 `_passable_cache` 会记录网格是否可通行。

**疑点**

如果起点或终点附近找不到可通行网格，会直接返回 `[target]`，这可能让移动阶段再处理不可走问题。

### `models/pathfinding.py:101-259` A*、障碍判断、拥堵成本和路径平滑

**负责什么**

执行网格 A* 寻路，并用障碍物、门洞和拥堵点影响路径。

**怎么实现**

- `_astar()` 用优先队列搜索目标网格。
- `_neighbors()` 支持 8 方向移动，并避免斜穿障碍。
- `_is_passable_cell()` 和 `_is_passable_point()` 判断边界、墙体、障碍物和门洞。
- `_nearest_passable_cell()` 从不可通行点向外找最近可通行网格。
- `_build_congestion_costs()` 给拥堵点周围网格增加成本。
- `_smooth_points()` 用视线检测减少路径折点。

**输入**

起止网格、障碍物、门洞、拥堵点、地图边界。

**输出/副作用**

返回 A* 回溯路径、平滑路径或可通行判断结果。会读写 `_passable_cache`。

**疑点**

每次导航都重新创建 `GridPathFinder`，无法复用缓存。拥堵成本来自当前学生位置快照，不是持续动态更新的路径场。

### `utils/helpers.py:6-36` 数学辅助函数

**负责什么**

提供仿真移动和评分中常用的小工具。

**怎么实现**

- `clamp()` 把数值限制在上下界内。
- `manhattan_2d()` 计算曼哈顿距离。
- `distance()` 计算欧氏距离。
- `move_towards()` 从当前位置朝目标移动不超过 `max_distance`，并返回是否到达。
- `triangle_peak_factor()` 根据时间和总时长生成中间高、两端低的三角因子。

**输入**

坐标、目标点、距离、时间。

**输出/副作用**

返回数值或新坐标，不修改状态。

**疑点**

`triangle_peak_factor()` 当前未在主要仿真引擎中明显使用。

## 6. 调度边界和高风险点

### `controllers/main_controller.py:10-83` PyQt 线程调度边界

**负责什么**

连接窗口 UI 和仿真 worker，创建线程，管理启动、暂停、停止、时间倍率和清理。

**怎么实现**

- `MainController` 继承 `QObject`，定义控制 worker 的 Qt 信号。
- `__init__()` 把窗口信号连接到控制器方法。
- `start_simulation()` 创建 `QThread` 和 `SimulationWorker`，把 worker 移入线程。
- 连接 `thread.started -> worker.run`。
- 连接 worker 的 `frameReady`、`statusChanged`、`finished`、`errorOccurred` 到窗口方法。
- `stop_simulation()`、`pause_simulation()`、`change_time_scale()` 通过信号控制 worker。
- `_cleanup_thread()` 断开信号，退出线程，清空引用。

**输入**

窗口发出的开始、停止、暂停、时间倍率信号。

**输出/副作用**

创建和销毁后台线程，向窗口推送仿真帧和状态。

**疑点**

这个控制器让 UI 和仿真 worker 强绑定在 PyQt 线程模型上。后端逻辑测试和未来 Web 服务都不应该依赖它。

## 7. 当前高风险点汇总

1. `SimulationWorker` 同时是 Qt worker 和仿真引擎，后端逻辑被 PyQt 依赖污染。
2. `_build_frame()` 会调用 `_record_queue_samples()` 和 `_record_runtime_sample()`，因此它不是纯读取函数。
3. 部分配置字段定义了但可能未真正参与仿真，例如 `dish_preference_weight`、`price_weight`、`default_dish_stock`、`low_stock_threshold`、`entrance_count`、`exit_count`。
4. `served_students` 在吃完饭时递增，不等价于已离场人数。
5. `DataRecorder` 支持 P1/P2/P3 大量事件，但 `SimulationWorker` 实际只记录了少量学生事件、队列采样和运行时采样。
6. 订单对象存在，但缺少 `order_created`、`order_started`、`order_completed` 等事件记录，导致订单统计可能为空。
7. 入口、出口、路径、同行、桌型相关统计结构存在，但实际事件链不完整。
8. 空间布局写死在仿真引擎中，后续若要做 B/S 或配置化，需要先拆布局和仿真核心。

## 8. 阅读建议

如果只是想快速看懂业务主流程，建议按这个顺序读：

1. `models/entities.py:7-30` 看有哪些状态。
2. `models/simulation_engine.py:69-96` 看每帧推进顺序。
3. `models/simulation_engine.py:562-632` 看学生状态机。
4. `models/simulation_engine.py:682-725` 看排队和订单创建。
5. `models/simulation_engine.py:742-760` 看找座和预留。
6. `models/simulation_engine.py:1374-1435` 看前端拿到的 `frame` 顶层结构。
7. `models/data_recorder.py:400-438` 看统计是怎么汇总出来的。
