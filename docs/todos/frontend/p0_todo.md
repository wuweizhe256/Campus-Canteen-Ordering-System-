# 前端 P0 阶段 TODO

## 1. P0 目标

前端 P0 目标是基于当前可用接口先跑通展示，同时为 P0 新增状态和基础统计预留稳定展示结构。

参考文档：

- `docs/business_logic_draft.md`
- `docs/realtime_frame_interface.md`
- `docs/frontend_backend_integration_test_plan.md`

## 2. 输入接口

### 2.1 当前必须兼容的接口

前端第一版必须能消费 `realtime_frame_interface.md` 中的 `v0_current`：

- 顶层字段：
  - `game_time`
  - `duration`
  - `time_scale`
  - `spawned_students`
  - `served_students`
  - `active_students`
  - `door`
  - `exit`
  - `width`
  - `height`
  - `walk_paths`
  - `stalls`
  - `tables`
  - `students`

- 学生字段：
  - `id`
  - `x`
  - `y`
  - `target_x`
  - `target_y`
  - `path`
  - `state`
  - `meat_pref`
  - `veg_pref`
  - `stall_id`

- 窗口字段：
  - `id`
  - `x`
  - `y`
  - `meat_ratio`
  - `veg_ratio`
  - `cook_time`
  - `cook_remaining`
  - `cook_progress`
  - `queue_count`

- 餐桌字段：
  - `id`
  - `x`
  - `y`
  - `occupied`
  - `seats`

### 2.2 P0 需要准备展示的接口

P0 后端完成后，前端需要展示：

- `tray_return_points`
- `stats`
- `students[].table_id`
- `students[].seat_index`
- `students[].state = searching_seat`
- `students[].state = moving_to_seat`
- `students[].state = moving_to_tray_return`
- `tables[].seats[] = SeatFrame`

## 3. 必做任务

### 3.1 重写画布数据适配层

- 建立前端 frame 适配层，先支持 `v0_current`。
- 将 `door` 适配为单个入口展示。
- 将 `exit` 适配为单个出口展示。
- 支持 `walk_paths` 路径调试展示。
- 学生列表为空时画布不能报错。
- 路径 `path` 为空数组时画布不能报错。

### 3.2 学生状态展示

必须支持当前状态：

- `deciding`
- `moving_to_queue`
- `queued`
- `waiting_seat`
- `moving_to_table`
- `eating`
- `leaving`

P0 预留并支持：

- `searching_seat`
- `moving_to_seat`
- `moving_to_tray_return`

要求：

- 不同学生状态要能在画布上区分。
- 未识别状态要有兜底展示。
- 当前 `moving_to_table` 和后续 `moving_to_seat` 都要兼容。

### 3.3 窗口展示

- 展示窗口编号。
- 展示窗口当前位置。
- 展示 `queue_count`。
- 展示 `cook_progress`。
- 展示 `cook_remaining`。
- P0 暂不要求展示菜品、价格、库存、售罄。

### 3.4 餐桌和座位展示

当前必须支持：

- `tables[].seats` 为 `array<integer/null>`。
- `null` 表示空闲。
- `student.id` 表示当前代码里的占用。

P0 预留并支持：

- `tables[].seats` 为 `array<SeatFrame>`。
- `status = free`
- `status = reserved`
- `status = occupied`

要求：

- 空闲、预留、占用必须视觉可区分。
- 座位状态字段缺失时要兼容当前 v0 格式。

### 3.5 碗筷收集点展示

P0 后端提供 `tray_return_points` 后：

- 在画布上展示碗筷收集点。
- 学生状态为 `moving_to_tray_return` 时能展示为前往收集点。
- 收集点列表为空时不能报错。

### 3.6 基础统计展示

P0 需要展示 `StatsFrameP0`：

- `avg_wait_time`
- `avg_total_time`
- `max_active_students`
- `stall_queue_stats[].max_queue_length`
- `seat_utilization`

要求：

- 指标为 `null` 时显示为空状态，不显示错误值。
- 单位需要明确，时间按秒或格式化为分秒。
- 统计面板字段名要和接口文档一致。

## 4. 暂不做

P0 前端暂不做：

- 菜品列表展示。
- 订单列表展示。
- 菜品价格、库存、售罄展示。
- 多入口 / 多出口展示。
- 多桌型专门展示。
- 同行关系展示。
- 各入口 / 各出口流量展示。
- 各桌型利用率展示。

## 5. 联调验收

前端 P0 联调通过标准：

- 能渲染当前 `v0_current` frame。
- 能兼容 P0 后端新增字段。
- 不因 `tray_return_points`、`stats`、`SeatFrame` 缺失而崩溃。
- 能展示新增学生状态。
- 能区分座位空闲 / 预留 / 占用。
- 能展示碗筷收集点。
- 能展示 P0 基础统计指标。
