# 后端 P0 阶段 TODO

## 1. P0 目标

后端 P0 目标是稳定主流程，补齐座位状态、学生状态、碗筷收集处、事件记录和 P0 数据输出接口。

参考文档：

- `docs/business_logic_draft.md`
- `docs/realtime_frame_interface.md`
- `docs/frontend_backend_integration_test_plan.md`

## 2. 必做任务

### 2.1 配置：修正最大同时在场人数

- 将 `max_active_students` 改为独立配置字段。
- 默认值参考业务文档：`120`。
- 不再使用 `max(55, total_students)`。
- 前端配置传入时，后端按传入值控制入场限流。

验收：

- 学生总数大于 `55` 时，仍受 `max_active_students` 限制。
- 固定配置下仿真结果可复现。

### 2.2 学生状态机：拆分找座状态

新增状态：

- `SEARCHING_SEAT`
- `MOVING_TO_SEAT`

处理规则：

- `SEARCHING_SEAT` 负责选座。
- `MOVING_TO_SEAT` 负责移动到座位。
- 当前 `MOVING_TO_TABLE` 逻辑拆分到上述两个状态。
- 在过渡期间，实时 `frame` 可继续兼容旧状态，但最终应输出新状态。

验收：

- 学生完成出餐后不再直接混用“找座”和“前往座位”。
- 无空座时进入 `WAITING_SEAT`。
- 有空座时进入 `MOVING_TO_SEAT`。

### 2.3 座位状态：增加 reserved

新增座位状态：

- `free`
- `reserved`
- `occupied`

处理规则：

- 分配座位后先标记为 `reserved`。
- 学生到达座位后切换为 `occupied`。
- 学生结束就餐后释放为 `free`。

验收：

- 一个座位不能同时被多个学生预留或占用。
- `reserved` 座位不会被其他学生再次分配。
- 前端 frame 能拿到座位状态。

### 2.4 碗筷收集处流程

新增对象：

- 碗筷收集点 `tray_return_points`

新增状态：

- `MOVING_TO_TRAY_RETURN`

流程规则：

- 学生结束就餐后先释放座位。
- 生成前往碗筷收集处的路径。
- 学生到达碗筷收集处后，再生成前往出口的路径。
- 离场前必须完成“到达碗筷收集处”事件。

验收：

- 学生不会从 `EATING` 直接进入出口路径。
- 学生路径顺序为座位 -> 碗筷收集处 -> 出口。
- `frame` 输出 `tray_return_points`。

### 2.5 事件记录模块

补充 `models/data_recorder.py`。

P0 至少记录事件：

- `student_spawned`
- `queue_started`
- `food_ready`
- `eating_started`
- `eating_finished`
- `student_left`

事件字段按接口文档 `EventRecordP0`：

- `event_type`
- `game_time`
- `student_id`
- `stall_id`
- `table_id`
- `seat_index`
- `from_state`
- `to_state`

验收：

- 每个学生至少能串起入场、排队、出餐、就餐、离场事件。
- 事件时间单调合理。
- 数据处理模块可基于事件计算 P0 指标。

### 2.6 P0 统计输出

后端需要提供或支持数据处理生成以下指标：

- 平均等待时间：从“进入窗口队列”到“完成出餐”。
- 平均就餐总耗时：从“学生入场”到“学生离场”。
- 最大在场人数。
- 各窗口最大队列长度。
- 座位利用率：座位被占用总时长 / 总座位时长。

验收：

- `frame.stats` 或数据处理输出中包含 `StatsFrameP0` 字段。
- 指标无法计算时使用 `null`，不要输出错误默认值。

### 2.7 实时 frame 输出

保持兼容当前 `v0_current` 字段，同时补充 P0 字段。

当前必须保留：

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

P0 新增：

- `tray_return_points`
- `stats`
- `students[].table_id`
- `students[].seat_index`
- `tables[].seats[]` 可升级为 `SeatFrame`

验收：

- 当前前端或新前端可继续使用 v0 字段。
- P0 新字段符合 `docs/realtime_frame_interface.md`。

## 3. 暂不做

P0 后端暂不做：

- 菜品表、价格、库存。
- 菜品级出餐时间。
- 订单对象列表。
- 窗口售罄状态。
- 多维偏好向量。
- 同行关系。
- 多入口、多出口。
- 多桌型。
- 全平面网格寻路。
- 直接离场 / 提前离场 / 等待超时。

## 4. 联调验收

后端 P0 联调通过标准：

- 固定 `seed` 下可复现。
- 学生状态流转符合业务主流程。
- 座位 `reserved` 和 `occupied` 不混淆。
- 碗筷收集处是离场前必经流程。
- 事件记录能计算 P0 指标。
- `frame` 同时兼容 `v0_current` 和 P0 新字段。
