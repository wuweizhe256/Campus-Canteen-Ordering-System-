# 仿真实时帧接口文档

## 0. 文档用途

本文档定义后端仿真 worker 输出给前端的实时帧 `frame` 数据结构。

本文档按阶段拆分：

- `v0_current`：当前代码已经实际输出的接口，前端现在可以直接依赖。
- `P0_current`：当前代码已经实际输出的 P0 接口。
- `P0_planned`：P0 仍计划新增或调整的接口。
- `P1_planned`：菜品、订单、库存、售罄相关接口。
- `P2_planned`：同行关系、多桌型相关接口。
- `P3_planned`：多入口、多出口、空间配置、路径规划相关接口。
- `P4_planned`：行为扩展和高级统计相关接口。

业务逻辑和阶段性 TODO 见：

- `docs/business_logic_draft.md`

联调测试方案见：

- `docs/frontend_backend_integration_test_plan.md`

数据处理在 P0 阶段需要两类接口：

- 后端 -> 数据处理：事件级记录。
- 数据处理 -> 前端：统计结果字段。

## 1. 接口阶段标记

| 标记 | 含义 |
| --- | --- |
| `v0_current` | 当前代码已经输出，前端可直接使用 |
| `P0_current` | P0 阶段当前代码已经输出，前端可直接使用 |
| `P0_planned` | P0 阶段仍计划新增或调整 |
| `P1_planned` | P1 阶段计划新增或调整 |
| `P2_planned` | P2 阶段计划新增或调整 |
| `P3_planned` | P3 阶段计划新增或调整 |
| `P4_planned` | P4 阶段计划新增或调整 |

---

## 2. 当前已实现接口

当前接口来自 `models/simulation_engine.py` 的 `_build_frame()`。

### 2.1 顶层结构 `Frame`

```text
frame
  game_time
  duration
  time_scale
  spawned_students
  served_students
  active_students
  door
  exit
  tray_return_points
  width
  height
  stats
  walk_paths
  collision_boxes
  stalls
  tables
  students
  student_details
```

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `game_time` | `number` | `v0_current` | 当前仿真时间，单位秒 |
| `duration` | `number` | `v0_current` | 总仿真时长，单位秒 |
| `time_scale` | `number` | `v0_current` | 当前时间倍率 |
| `spawned_students` | `integer` | `v0_current` | 已生成学生数 |
| `served_students` | `integer` | `v0_current` | 当前代码中表示已完成就餐并进入离场流程的人数 |
| `active_students` | `integer` | `v0_current` | 当前仍在系统中的学生数 |
| `door` | `PointTuple` | `v0_current` | 当前单入口坐标 |
| `exit` | `PointTuple` | `v0_current` | 当前单出口坐标 |
| `tray_return_points` | `array<TrayReturnFrame>` | `P0_current` | 碗筷收集点 |
| `width` | `number` | `v0_current` | 仿真画布宽度 |
| `height` | `number` | `v0_current` | 仿真画布高度 |
| `stats` | `StatsFrameP0` | `P0_current` | P0 统计和当前扩展运行指标 |
| `walk_paths` | `array<PathFrameV0>` | `v0_current` | 路径调试线 |
| `collision_boxes` | `array<CollisionBoxFrame>` | `P0_current` | 调试用静态与学生碰撞盒 |
| `stalls` | `array<StallFrameV0>` | `v0_current` | 窗口实时数据 |
| `tables` | `array<TableFrameV0>` | `v0_current` | 餐桌实时数据 |
| `students` | `array<StudentFrameV0>` | `v0_current` | 学生实时数据，已 `DONE` 的学生不会输出；worker 高频运行帧中可为轻量学生帧 |
| `student_details` | `array<StudentFrameV0>` | `P0_current` | 可选低频学生详情帧，用于弹窗、调试层和详情面板 |

口径说明：

- `served_students` 当前不是“已离场人数”，而是在学生结束就餐、释放座位并进入碗筷回收流程时递增。
- 真正离场事件以 `student_left` 事件或学生进入 `done` 状态后从 `students` 输出中消失为准。

### 2.2 点 `PointTuple`

当前代码中点使用 tuple / list 形式。

```text
[x, y]
```

### 2.3 学生 `StudentFrameV0`

性能说明：

- `SimulationEngine.build_frame()` 默认仍输出完整 `students`，用于兼容测试和直接调用。
- `SimulationWorker` 高频运行帧会输出轻量 `students`，只保留画布和队列展示所需字段。
- `SimulationWorker` 会低频附带 `student_details`，其中保留路径、偏好、用餐进度和寻路指标等完整详情。

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `v0_current` | 学生编号 |
| `x` | `number` | `v0_current` | 当前横坐标 |
| `y` | `number` | `v0_current` | 当前纵坐标 |
| `target_x` | `number` | `v0_current` | 当前目标横坐标 |
| `target_y` | `number` | `v0_current` | 当前目标纵坐标 |
| `path` | `array<PointTuple>` | `v0_current` | 当前剩余路径点 |
| `state` | `string` | `v0_current` | 学生状态 |
| `meat_pref` | `number` | `v0_current` | 当前学生荤偏好，后续会被多维偏好替换 |
| `veg_pref` | `number` | `v0_current` | 当前学生素偏好，后续会被多维偏好替换 |
| `stall_id` | `integer/null` | `v0_current` | 当前目标窗口 |
| `table_id` | `integer/null` | `P0_current` | 当前目标餐桌 |
| `seat_index` | `integer/null` | `P0_current` | 当前目标座位 |
| `actual_speed` | `number` | `P0_current` | 当前帧估算移动速度 |
| `stuck_time` | `number` | `P0_current` | 当前连续低速 / 卡住时间 |
| `reroute_count` | `integer` | `P0_current` | 当前学生累计绕行或重规划次数 |
| `facing_x` | `number` | `P0_current` | 朝向横向分量，用于前端绘制 |
| `facing_y` | `number` | `P0_current` | 朝向纵向分量，用于前端绘制 |

当前学生状态枚举：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `deciding` | `v0_current` | 思考中 |
| `moving_to_queue` | `v0_current` | 前往窗口 |
| `queued` | `v0_current` | 排队中 |
| `searching_seat` | `P0_current` | 找座中，负责选座 |
| `waiting_seat` | `v0_current` | 等座中 |
| `moving_to_seat` | `P0_current` | 前往座位 |
| `eating` | `v0_current` | 就餐中 |
| `moving_to_tray_return` | `P0_current` | 前往碗筷收集处 |
| `leaving` | `v0_current` | 前往出口 |
| `done` | `v0_current` | 已离场；当前不会出现在 `students` 输出列表中 |

兼容说明：

- `moving_to_table` 是旧接口状态；当前后端已经替换为 `searching_seat` 和 `moving_to_seat`。
- 前端适配层仍建议兼容 `moving_to_table`，用于读取旧帧或测试数据。

### 2.4 窗口 `StallFrameV0`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `v0_current` | 窗口编号 |
| `x` | `number` | `v0_current` | 横坐标 |
| `y` | `number` | `v0_current` | 纵坐标 |
| `meat_ratio` | `number` | `v0_current` | 当前窗口荤特征，后续会被菜品特征替换 |
| `veg_ratio` | `number` | `v0_current` | 当前窗口素特征，后续会被菜品特征替换 |
| `cook_time` | `number` | `v0_current` | 当前窗口级单份出餐时间 |
| `cook_remaining` | `number` | `v0_current` | 当前队首剩余出餐时间 |
| `cook_progress` | `number` | `v0_current` | 当前出餐进度，范围 `0.0 ~ 1.0` |
| `queue_count` | `integer` | `v0_current` | 当前队列长度 |

### 2.5 餐桌 `TableFrameV0`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `v0_current` | 餐桌编号 |
| `x` | `number` | `v0_current` | 横坐标 |
| `y` | `number` | `v0_current` | 纵坐标 |
| `occupied` | `integer` | `v0_current` | 当前占用座位数 |
| `seats` | `array<integer/null>` | `v0_current` | 兼容旧格式的座位数组；元素为学生 `id` 或 `null` |
| `seat_frames` | `array<SeatFrame>` | `P0_current` | P0 座位状态数组，能区分空闲、预留、占用 |

当前座位语义：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `null` | `v0_current` | 空闲 |
| `student.id` | `v0_current` | 已预留或已占用，旧字段无法区分具体状态 |

当前推荐前端优先读取 `seat_frames`，仅在缺失时回退到 `seats`。

### 2.6 座位 `SeatFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `index` | `integer` | `P0_current` | 座位索引 |
| `status` | `string` | `P0_current` | 座位状态 |
| `student_id` | `integer/null` | `P0_current` | 占用或预留学生编号 |

座位状态枚举：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `free` | `P0_current` | 空闲 |
| `reserved` | `P0_current` | 已分配但学生未到达 |
| `occupied` | `P0_current` | 学生已到达并就座 |

### 2.7 路径 `PathFrameV0`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `kind` | `string` | `v0_current` | 路径类型 |
| `points` | `array<PointTuple>` | `v0_current` | 路径点 |

当前路径类型：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `queue` | `v0_current` | 排队主通道 |
| `top` | `v0_current` | 上方主通道 |
| `bottom` | `v0_current` | 下方主通道 |
| `door` | `v0_current` | 入口到通道 |
| `tray` | `P0_current` | 碗筷收集处路径 |
| `exit` | `v0_current` | 通道到出口 |
| `aisle` | `v0_current` | 餐桌间纵向通道 |

### 2.8 碰撞盒 `CollisionBoxFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `x` | `number` | `P0_current` | 中心横坐标 |
| `y` | `number` | `P0_current` | 中心纵坐标 |
| `width` | `number` | `P0_current` | 宽度 |
| `height` | `number` | `P0_current` | 高度 |
| `kind` | `string/null` | `P0_current` | 碰撞盒类型，当前可为 `static` 或 `student` |
| `student_id` | `integer/null` | `P0_current` | 学生碰撞盒所属学生 ID，仅 `kind = student` 时存在 |
| `state` | `string/null` | `P0_current` | 学生碰撞盒所属学生状态，仅 `kind = student` 时存在 |

---

## 3. P0 当前接口和剩余计划

P0 目标是支持 4 天阶段性交付：稳定主流程、补齐座位预留、碗筷收集处、基础统计和数据处理事件记录。

### 3.1 顶层 P0 字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `tray_return_points` | `array<TrayReturnFrame>` | `P0_current` | 碗筷收集点 |
| `stats` | `StatsFrameP0` | `P0_current` | P0 基础统计和当前扩展运行指标 |
| `collision_boxes` | `array<CollisionBoxFrame>` | `P0_current` | 调试用静态与学生碰撞盒 |

### 3.2 学生字段调整

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `table_id` | `integer/null` | `P0_current` | 当前目标餐桌 |
| `seat_index` | `integer/null` | `P0_current` | 当前目标座位 |
| `actual_speed` | `number` | `P0_current` | 当前帧估算移动速度 |
| `stuck_time` | `number` | `P0_current` | 当前连续低速 / 卡住时间 |
| `reroute_count` | `integer` | `P0_current` | 当前学生累计绕行或重规划次数 |
| `facing_x` | `number` | `P0_current` | 朝向横向分量，用于前端绘制 |
| `facing_y` | `number` | `P0_current` | 朝向纵向分量，用于前端绘制 |

P0 新增 / 替换学生状态：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `searching_seat` | `P0_current` | 找座中，负责选座 |
| `moving_to_seat` | `P0_current` | 前往座位，替代当前 `moving_to_table` |
| `moving_to_tray_return` | `P0_current` | 前往碗筷收集处 |

兼容说明：

- `moving_to_table` 是 `v0_current` 状态。
- 当前后端已输出 `moving_to_seat`，前端仍建议兼容 `moving_to_table`。

### 3.3 餐桌 / 座位接口调整

当前代码保留 `tables[].seats` 作为旧格式兼容字段，并新增 `tables[].seat_frames` 作为 P0 状态字段。

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `tables[].seats` | `array<integer/null>` | `v0_current` | 兼容旧格式，无法区分预留和占用 |
| `tables[].seat_frames` | `array<SeatFrame>` | `P0_current` | P0 座位状态数组 |
| `SeatFrame.index` | `integer` | `P0_current` | 座位索引 |
| `SeatFrame.status` | `string` | `P0_current` | 座位状态 |
| `SeatFrame.student_id` | `integer/null` | `P0_current` | 占用或预留学生编号 |

座位状态枚举：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `free` | `P0_current` | 空闲 |
| `reserved` | `P0_current` | 已分配但学生未到达 |
| `occupied` | `P0_current` | 学生已到达并就座 |

### 3.4 碗筷收集点 `TrayReturnFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `P0_current` | 收集点编号 |
| `x` | `number` | `P0_current` | 中心横坐标 |
| `y` | `number` | `P0_current` | 中心纵坐标 |
| `width` | `number` | `P0_current` | 区域宽度 |
| `height` | `number` | `P0_current` | 区域高度 |
| `is_congested` | `boolean` | `P0_current` | 是否拥堵 |

### 3.5 P0 统计 `StatsFrameP0`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `avg_wait_time` | `number/null` | `P0_current` | 平均等待时间：进入窗口队列到完成出餐 |
| `avg_total_time` | `number/null` | `P0_current` | 平均就餐总耗时：学生入场到学生离场 |
| `max_active_students` | `integer` | `P0_current` | 仿真过程中最大在场人数 |
| `stall_queue_stats` | `array<StallQueueStats>` | `P0_current` | 各窗口最大队列统计 |
| `seat_utilization` | `number/null` | `P0_current` | 总座位利用率 |
| `avg_move_speed` | `number/null` | `P0_current` | 当前移动学生平均速度，运行态扩展指标 |
| `congestion_index` | `number` | `P0_current` | 当前拥堵指数，范围 `0.0 ~ 1.0` |
| `stuck_student_count` | `integer` | `P0_current` | 当前卡住学生数 |
| `reroute_count` | `integer` | `P0_current` | 当前活跃学生累计重规划次数 |
| `avg_queue_length` | `number/null` | `P0_current` | 当前各窗口队列长度均值，不是历史平均队列长度 |
| `tray_return_queue_length` | `integer` | `P0_current` | 当前回收点附近等待 / 通行学生数 |

`StallQueueStats`：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `stall_id` | `integer` | `P0_current` | 窗口编号 |
| `max_queue_length` | `integer` | `P0_current` | 最大队列长度 |

### 3.6 P0 后端 -> 数据处理：事件记录 `EventRecordP0`

P0 阶段的数据处理输入来自后端事件记录。该接口依据 `business_logic_draft.md` 中 P0 和统计章节，只覆盖已明确提出的事件。

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `event_type` | `string` | `P0_current` | 事件类型 |
| `game_time` | `number` | `P0_current` | 事件发生的仿真时间 |
| `student_id` | `integer/null` | `P0_current` | 相关学生编号 |
| `stall_id` | `integer/null` | `P0_current` | 相关窗口编号 |
| `table_id` | `integer/null` | `P0_current` | 相关餐桌编号 |
| `seat_index` | `integer/null` | `P0_current` | 相关座位编号 |
| `from_state` | `string/null` | `P0_current` | 事件发生前学生状态 |
| `to_state` | `string/null` | `P0_current` | 事件发生后学生状态 |

P0 事件类型枚举：

| 值 | 阶段 | 说明 | 用于指标 |
| --- | --- | --- | --- |
| `student_spawned` | `P0_current` | 学生入场 | 平均就餐总耗时、最大在场人数 |
| `queue_started` | `P0_current` | 学生开始排队 | 平均等待时间、窗口队列统计 |
| `food_ready` | `P0_current` | 学生完成出餐 | 平均等待时间 |
| `eating_started` | `P0_current` | 学生开始就餐 | 座位利用率 |
| `eating_finished` | `P0_current` | 学生结束就餐 | 座位利用率 |
| `student_left` | `P0_current` | 学生离场 | 平均就餐总耗时、最大在场人数 |

当前限制：

- 当前没有单独的“到达碗筷收集处”事件；回收点流程只能从 `moving_to_tray_return -> leaving` 的实时状态变化推断。

事件口径：

- 平均等待时间 = `food_ready.game_time - queue_started.game_time`。
- 平均就餐总耗时 = `student_left.game_time - student_spawned.game_time`。
- 座位利用率 = 座位被占用总时长 / 总座位时长。
- 最大在场人数由 `student_spawned` 和 `student_left` 事件累计得到。
- 各窗口最大队列长度可由实时 `queue_count` 采样或排队事件累计得到；P0 接口只要求输出 `max_queue_length`。

### 3.7 P0 数据处理 -> 前端：统计输出

P0 阶段前端展示的统计结果应复用 `StatsFrameP0`，由数据处理模块计算后交给前端。

| 字段 | 类型 | 阶段 | 来源事件 / 数据 |
| --- | --- | --- | --- |
| `avg_wait_time` | `number/null` | `P0_current` | `queue_started`、`food_ready` |
| `avg_total_time` | `number/null` | `P0_current` | `student_spawned`、`student_left` |
| `max_active_students` | `integer` | `P0_current` | `student_spawned`、`student_left` |
| `stall_queue_stats[].max_queue_length` | `integer` | `P0_current` | `queue_count` 采样或窗口队列事件 |
| `seat_utilization` | `number/null` | `P0_current` | `eating_started`、`eating_finished` |
| `avg_move_speed` | `number/null` | `P0_current` | 当前活跃移动学生 |
| `congestion_index` | `number` | `P0_current` | 当前邻近密度 |
| `stuck_student_count` | `integer` | `P0_current` | 当前移动速度和目标距离 |
| `reroute_count` | `integer` | `P0_current` | 当前活跃学生 |
| `avg_queue_length` | `number/null` | `P0_current` | 当前窗口队列长度快照 |
| `tray_return_queue_length` | `integer` | `P0_current` | 当前回收点附近学生 |

P0 不加入的统计字段：

- `lost_students`：业务文档中属于直接离场 / 不吃就走的扩展统计，暂不作为 P0 必需输出。
- 历史口径的各窗口平均队列长度：当前 `avg_queue_length` 只是实时快照均值，不是按时间累计的历史平均值。
- 各入口 / 各出口流量：属于多入口、多出口阶段。
- 各桌型利用率：属于多桌型阶段。

---

## 4. P1 计划接口

P1 目标是引入菜品、订单、库存、菜品级出餐时间和窗口售罄。

### 4.1 学生新增字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `preferences` | `object` | `P1_planned` | 多维偏好向量 |
| `dish_id` | `integer/null` | `P1_planned` | 当前选择菜品 |
| `order_id` | `integer/null` | `P1_planned` | 当前订单 |

兼容说明：

- `meat_pref`、`veg_pref` 是 `v0_current` 字段。
- P1 后建议前端优先使用 `preferences`。

### 4.2 窗口新增字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `status` | `string` | `P1_planned` | 窗口营业状态 |
| `is_congested` | `boolean` | `P1_planned` | 是否拥堵 |
| `dishes` | `array<DishFrame>` | `P1_planned` | 菜品列表 |
| `orders` | `array<OrderFrame>` | `P1_planned` | 订单列表 |

窗口状态枚举：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `pending` | `P1_planned` | 待营业 |
| `open` | `P1_planned` | 营业中 |
| `sold_out` | `P1_planned` | 已售罄 |

拥堵规则：

- `queue_count >= 8` 时，`is_congested = true`。

### 4.3 菜品 `DishFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `P1_planned` | 菜品编号 |
| `name` | `string` | `P1_planned` | 菜品名称 |
| `features` | `object` | `P1_planned` | 菜品特征向量 |
| `price` | `number` | `P1_planned` | 价格 |
| `stock` | `integer` | `P1_planned` | 剩余库存 |
| `cook_time` | `number` | `P1_planned` | 基础出餐时间 |
| `available` | `boolean` | `P1_planned` | 是否可售 |

### 4.4 订单 `OrderFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `P1_planned` | 订单编号 |
| `student_id` | `integer` | `P1_planned` | 学生编号 |
| `stall_id` | `integer` | `P1_planned` | 窗口编号 |
| `dish_id` | `integer` | `P1_planned` | 菜品编号 |
| `created_at` | `number` | `P1_planned` | 创建时间 |
| `started_at` | `number/null` | `P1_planned` | 开始处理时间 |
| `finished_at` | `number/null` | `P1_planned` | 完成时间 |
| `status` | `string` | `P1_planned` | 订单状态 |

订单状态枚举：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `queued` | `P1_planned` | 排队等待 |
| `cooking` | `P1_planned` | 出餐中 |
| `done` | `P1_planned` | 已完成 |
| `cancelled` | `P1_planned` | 已取消 |

### 4.5 P1 后端 -> 数据处理：事件记录扩展

P1 在 P0 事件记录基础上增加订单、菜品、库存和售罄事件。数据处理模块已按这些字段兼容 P1 统计；后端未实现时可以不输出这些事件。

新增事件字段：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `dish_id` | `integer/null` | `P1_planned` | 相关菜品编号 |
| `order_id` | `integer/null` | `P1_planned` | 相关订单编号 |
| `quantity` | `integer/null` | `P1_planned` | 菜品数量，缺省按 `1` 统计 |
| `price` | `number/null` | `P1_planned` | 下单时菜品单价 |
| `stock_before` | `integer/null` | `P1_planned` | 库存变化前余量 |
| `stock_after` | `integer/null` | `P1_planned` | 库存变化后余量 |
| `order_status` | `string/null` | `P1_planned` | 订单状态 |
| `stall_status` | `string/null` | `P1_planned` | 窗口营业状态 |

P1 事件类型枚举：

| 值 | 阶段 | 说明 | 用于指标 |
| --- | --- | --- | --- |
| `order_created` | `P1_planned` | 订单创建 / 进入队列 | 订单等待时间、订单总耗时 |
| `order_started` | `P1_planned` | 订单开始处理 | 订单等待时间、出餐耗时 |
| `order_completed` | `P1_planned` | 订单完成 | 菜品销量、收入、订单耗时、库存快照 |
| `order_cancelled` | `P1_planned` | 订单取消 | 取消订单数 |
| `dish_stock_changed` | `P1_planned` | 菜品库存变化 | 最新库存 |
| `dish_sold_out` | `P1_planned` | 菜品售罄 | 售罄次数、最新库存 |

### 4.6 P1 数据处理 -> 前端：统计输出扩展

P1 统计字段继续放在 `frame["stats"]` 中，缺少 P1 事件时返回空数组、`0` 或 `null`。

| 字段 | 类型 | 阶段 | 来源事件 / 数据 |
| --- | --- | --- | --- |
| `dish_sales_stats` | `array<DishSalesStats>` | `P1_planned` | `order_completed` |
| `dish_sold_out_stats` | `array<DishSoldOutStats>` | `P1_planned` | `dish_sold_out` |
| `dish_stock_stats` | `array<DishStockStats>` | `P1_planned` | `dish_stock_changed`、`dish_sold_out`、`order_completed` |
| `avg_order_wait_time` | `number/null` | `P1_planned` | `order_created` -> `order_started` |
| `avg_order_cook_time` | `number/null` | `P1_planned` | `order_started` -> `order_completed` |
| `avg_order_total_time` | `number/null` | `P1_planned` | `order_created` -> `order_completed` |
| `completed_order_count` | `integer` | `P1_planned` | `order_completed` |
| `cancelled_order_count` | `integer` | `P1_planned` | `order_cancelled` |

`DishSalesStats`：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `dish_id` | `integer` | `P1_planned` | 菜品编号 |
| `stall_id` | `integer/null` | `P1_planned` | 窗口编号 |
| `sales_count` | `integer` | `P1_planned` | 完成订单中的累计销量 |
| `revenue` | `number` | `P1_planned` | `price * quantity` 累计收入，缺价格时按 `0` |

`DishSoldOutStats`：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `dish_id` | `integer` | `P1_planned` | 菜品编号 |
| `stall_id` | `integer/null` | `P1_planned` | 窗口编号 |
| `sold_out_count` | `integer` | `P1_planned` | 售罄事件次数 |

`DishStockStats`：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `dish_id` | `integer` | `P1_planned` | 菜品编号 |
| `stall_id` | `integer/null` | `P1_planned` | 窗口编号 |
| `stock` | `integer` | `P1_planned` | 最新 `stock_after`，最小值按 `0` 兜底 |

---

## 5. P2 计划接口

P2 目标是引入同行关系和多桌型。

### 5.1 学生同行字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `group_id` | `integer/null` | `P2_planned` | 同行组编号 |
| `group_size` | `integer/null` | `P2_planned` | 同行组人数 |

### 5.2 餐桌多桌型字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `table_type` | `string` | `P2_planned` | 桌型 |
| `seat_count` | `integer` | `P2_planned` | 座位数量 |

桌型枚举：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `two` | `P2_planned` | 2 人桌 |
| `four` | `P2_planned` | 4 人桌 |
| `six` | `P2_planned` | 6 人桌 |

### 5.3 P2 统计字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `group_same_table_rate` | `number/null` | `P2_planned` | 完整同行组中，全组坐在同一桌的比例 |
| `completed_group_count` | `integer` | `P2_planned` | 已形成完整座位分配的同行组数量，不含独行 |
| `same_table_group_count` | `integer` | `P2_planned` | 全组坐在同一桌的同行组数量 |
| `table_type_utilization` | `array<TableTypeUtilizationStats>` | `P2_planned` | 各桌型利用率 |

### 5.4 P2 后端 -> 数据处理：事件记录扩展

P2 在 P0/P1 事件记录基础上增加同行组和桌型字段。数据处理模块已按这些字段计算同行组同桌率和各桌型利用率。

新增事件字段：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `group_id` | `integer/null` | `P2_planned` | 同行组编号 |
| `group_size` | `integer/null` | `P2_planned` | 同行组人数 |
| `table_type` | `string/null` | `P2_planned` | 桌型，取值见桌型枚举 |
| `seat_count` | `integer/null` | `P2_planned` | 当前餐桌座位数量 |

P2 事件类型枚举：

| 值 | 阶段 | 说明 | 用于指标 |
| --- | --- | --- | --- |
| `group_created` | `P2_planned` | 同行组创建 | 同行组数量、同桌率分母 |
| `group_member_joined` | `P2_planned` | 学生加入同行组 | 同行组成员复盘 |
| `seat_assigned` | `P2_planned` | 座位分配完成 | 同行组同桌率 |
| `seat_released` | `P2_planned` | 座位释放 | 座位流转复盘 |
| `table_type_registered` | `P2_planned` | 餐桌桌型登记 | 各桌型总座位数 |

### 5.5 P2 数据处理 -> 前端：统计输出扩展

P2 统计字段继续放在 `frame["stats"]` 中，缺少 P2 事件时同桌率返回 `null`，计数返回 `0`，桌型利用率返回空数组。

| 字段 | 类型 | 阶段 | 来源事件 / 数据 |
| --- | --- | --- | --- |
| `group_same_table_rate` | `number/null` | `P2_planned` | `seat_assigned` 或带 `group_id` 的 `eating_started` |
| `completed_group_count` | `integer` | `P2_planned` | 完整同行组座位分配 |
| `same_table_group_count` | `integer` | `P2_planned` | 完整同行组且 `table_id` 相同 |
| `table_type_utilization` | `array<TableTypeUtilizationStats>` | `P2_planned` | `table_type_registered`、`eating_started`、`eating_finished` |

`TableTypeUtilizationStats`：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `table_type` | `string` | `P2_planned` | 桌型 |
| `seat_count` | `integer` | `P2_planned` | 该桌型总座位数 |
| `utilization` | `number/null` | `P2_planned` | 该桌型占用总时长 / 该桌型总座位时长 |

---

## 6. P3 计划接口

P3 目标是引入多入口、多出口、空间配置、障碍物和全平面路径规划。

### 6.1 顶层空间字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `entrances` | `array<EntranceFrame>` | `P3_planned` | 入口区域列表 |
| `exits` | `array<ExitFrame>` | `P3_planned` | 出口区域列表 |
| `obstacles` | `array<RectFrame>` | `P3_planned` | 障碍物矩形 |

兼容说明：

- `door` 是 `v0_current` 的单入口坐标。
- `exit` 是 `v0_current` 的单出口坐标。
- P3 后建议前端优先使用 `entrances` 和 `exits`。

### 6.2 入口 `EntranceFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `P3_planned` | 入口编号 |
| `x` | `number` | `P3_planned` | 中心横坐标 |
| `y` | `number` | `P3_planned` | 中心纵坐标 |
| `width` | `number` | `P3_planned` | 区域宽度 |
| `height` | `number` | `P3_planned` | 区域高度 |
| `weight` | `number` | `P3_planned` | 生成流量权重 |

### 6.3 出口 `ExitFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `P3_planned` | 出口编号 |
| `x` | `number` | `P3_planned` | 中心横坐标 |
| `y` | `number` | `P3_planned` | 中心纵坐标 |
| `width` | `number` | `P3_planned` | 区域宽度 |
| `height` | `number` | `P3_planned` | 区域高度 |
| `is_congested` | `boolean` | `P3_planned` | 是否拥堵 |

### 6.4 障碍物 `RectFrame`

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `left` | `number` | `P3_planned` | 左边界 |
| `top` | `number` | `P3_planned` | 上边界 |
| `right` | `number` | `P3_planned` | 右边界 |
| `bottom` | `number` | `P3_planned` | 下边界 |
| `kind` | `string` | `P3_planned` | 障碍物类型 |

### 6.5 P3 统计字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `entrance_flow` | `array<FlowStats>` | `P3_planned` | 各入口流量 |
| `exit_flow` | `array<FlowStats>` | `P3_planned` | 各出口流量 |
| `path_congestion_stats` | `PathCongestionStats` | `P3_planned` | 路径拥堵统计 |

### 6.6 P3 后端 -> 数据处理：事件记录扩展

P3 在 P0/P1/P2 事件记录基础上增加入口、出口、路径和障碍物字段。数据处理模块已按这些字段计算入口流量、出口流量和路径拥堵指标。

新增事件字段：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `entrance_id` | `integer/null` | `P3_planned` | 入口编号 |
| `exit_id` | `integer/null` | `P3_planned` | 出口编号 |
| `obstacle_id` | `integer/null` | `P3_planned` | 障碍物编号 |
| `obstacle_kind` | `string/null` | `P3_planned` | 障碍物类型 |
| `path_id` | `string/null` | `P3_planned` | 路径编号 |
| `path_length` | `number/null` | `P3_planned` | 路径长度 |
| `path_duration` | `number/null` | `P3_planned` | 路径耗时 |
| `path_congestion_index` | `number/null` | `P3_planned` | 路径拥堵指数，建议范围 `0.0 ~ 1.0` |
| `path_blocked` | `boolean/null` | `P3_planned` | 路径是否被阻断或需要明显绕行 |

P3 事件类型枚举：

| 值 | 阶段 | 说明 | 用于指标 |
| --- | --- | --- | --- |
| `entrance_used` | `P3_planned` | 学生从某入口进入 | 入口流量 |
| `exit_used` | `P3_planned` | 学生从某出口离场 | 出口流量 |
| `path_planned` | `P3_planned` | 生成一条路径 | 平均路径长度 |
| `path_completed` | `P3_planned` | 完成一条路径 | 平均路径长度、平均路径耗时 |
| `path_congestion_sample` | `P3_planned` | 路径拥堵采样 | 平均路径拥堵指数、阻断次数 |
| `obstacle_registered` | `P3_planned` | 障碍物登记 | 障碍物复盘和联调校验 |

### 6.7 P3 数据处理 -> 前端：统计输出扩展

P3 统计字段继续放在 `frame["stats"]` 中，缺少 P3 事件时流量返回空数组，路径拥堵统计中的均值返回 `null`，计数返回 `0`。

`FlowStats`：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `id` | `integer` | `P3_planned` | 入口或出口编号 |
| `flow_count` | `integer` | `P3_planned` | 累计流量 |

`PathCongestionStats`：

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `avg_path_length` | `number/null` | `P3_planned` | `path_planned` 和 `path_completed` 中路径长度均值 |
| `avg_path_duration` | `number/null` | `P3_planned` | `path_completed` 中路径耗时均值 |
| `avg_path_congestion_index` | `number/null` | `P3_planned` | 路径拥堵采样均值 |
| `path_sample_count` | `integer` | `P3_planned` | 路径拥堵采样次数 |
| `completed_path_count` | `integer` | `P3_planned` | 完成路径数 |
| `blocked_path_count` | `integer` | `P3_planned` | `path_blocked = true` 的事件次数 |

---

## 7. P4 计划接口

P4 目标是支持主动离场、放弃等待、提前离场和更细的统计分析。

### 7.1 学生行为字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `leave_reason` | `string/null` | `P4_planned` | 离场原因 |
| `wait_timeout_at` | `number/null` | `P4_planned` | 等座超时时间 |

离场原因枚举：

| 值 | 阶段 | 说明 |
| --- | --- | --- |
| `finished` | `P4_planned` | 正常完成就餐 |
| `left_after_deciding` | `P4_planned` | 思考后直接离场 |
| `seat_timeout` | `P4_planned` | 等座超时离场 |
| `early_leave` | `P4_planned` | 就餐中提前离场 |

### 7.2 P4 统计字段

| 字段 | 类型 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `lost_students` | `integer` | `P4_planned` | 流失人数 |
| `avg_active_students_by_period` | `array<object>` | `P4_planned` | 指定时段平均在场人数 |
| `avg_queue_length` | `array<object>` | `P4_planned` | 各窗口平均队列长度 |

---

## 8. 前端重写建议

如果当前前端准备重写，建议前端按以下策略消费接口：

1. 第一版支持 `v0_current` 和 `P0_current` 字段，保证能跑当前程序。
2. 前端数据层保留适配层，把 `door` 适配成单个入口，把 `exit` 适配成单个出口。
3. 前端座位展示优先使用 `seat_frames`，缺失时回退到 `seats: array<integer/null>`。
4. 学生状态展示同时兼容旧 `moving_to_table` 和当前 `moving_to_seat`。
5. 后续每完成一个阶段，只扩展适配层，不重写画布主逻辑。

## 9. 当前接口与目标接口关系

| 当前字段 | 后续目标字段 | 阶段 |
| --- | --- | --- |
| `door` | `entrances` | `P3_planned` |
| `exit` | `exits` | `P3_planned` |
| `meat_pref`, `veg_pref` | `preferences` | `P1_planned` |
| `meat_ratio`, `veg_ratio` | `dishes[].features` | `P1_planned` |
| `cook_time` | `dishes[].cook_time` | `P1_planned` |
| `ready_times` | `orders` | `P1_planned` |
| `tables[].seats: array<integer/null>` | `tables[].seat_frames: array<SeatFrame>` | `P0_current` |
| `moving_to_table` | `searching_seat`, `moving_to_seat` | `P0_current` |
