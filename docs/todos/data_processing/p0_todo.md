# 数据处理 P0 阶段 TODO

## 1. P0 目标

数据处理 P0 目标是接收后端事件记录，计算 P0 基础统计指标，并将统计结果提供给前端展示。

参考文档：

- `docs/business_logic_draft.md`
- `docs/realtime_frame_interface.md`
- `docs/frontend_backend_integration_test_plan.md`

## 2. 输入接口

P0 输入来自后端事件记录 `EventRecordP0`。

字段：

- `event_type`
- `game_time`
- `student_id`
- `stall_id`
- `table_id`
- `seat_index`
- `from_state`
- `to_state`

P0 事件类型：

- `student_spawned`
- `queue_started`
- `food_ready`
- `eating_started`
- `eating_finished`
- `student_left`

## 3. 输出接口

P0 输出给前端的统计结果使用 `StatsFrameP0`。

字段：

- `avg_wait_time`
- `avg_total_time`
- `max_active_students`
- `stall_queue_stats`
- `seat_utilization`

`stall_queue_stats` 当前只要求：

- `stall_id`
- `max_queue_length`

## 4. 必做任务

### 4.1 事件接收和缓存

- 接收后端传来的 `EventRecordP0`。
- 按 `student_id` 组织学生生命周期事件。
- 按 `stall_id` 组织窗口排队相关事件。
- 按 `table_id + seat_index` 组织座位占用相关事件。
- 事件按 `game_time` 排序或保证写入顺序可追踪。

验收：

- 能查询某个学生的完整事件链。
- 缺失事件时能识别并跳过该样本，不让统计崩溃。

### 4.2 平均等待时间

定义：

- 从“进入窗口队列”开始。
- 到“完成出餐”结束。

计算方式：

- 对同一 `student_id` 匹配 `queue_started` 和 `food_ready`。
- 单个学生等待时间 = `food_ready.game_time - queue_started.game_time`。
- 平均等待时间 = 所有有效学生等待时间的平均值。

输出：

- `avg_wait_time`

### 4.3 平均就餐总耗时

定义：

- 从“学生入场”开始。
- 到“学生离场”结束。

计算方式：

- 对同一 `student_id` 匹配 `student_spawned` 和 `student_left`。
- 单个学生总耗时 = `student_left.game_time - student_spawned.game_time`。
- 平均就餐总耗时 = 所有有效学生总耗时的平均值。

输出：

- `avg_total_time`

### 4.4 最大在场人数

计算方式：

- `student_spawned` 事件使在场人数 +1。
- `student_left` 事件使在场人数 -1。
- 扫描事件时间线，记录最大值。

输出：

- `max_active_students`

### 4.5 各窗口最大队列长度

P0 业务文档要求统计各窗口最大队列长度。

数据来源可二选一：

- 后端直接在事件或 frame 中提供队列长度采样。
- 数据处理根据 `queue_started` 和 `food_ready` / 离队事件推导。

输出：

- `stall_queue_stats[].stall_id`
- `stall_queue_stats[].max_queue_length`

注意：

- P0 只要求最大队列长度。
- 平均队列长度不作为 P0 必做。

### 4.6 座位利用率

定义：

- 座位被占用总时长 / 总座位时长。

计算方式：

- 使用 `eating_started` 和 `eating_finished` 作为座位占用时间区间。
- 对每个座位累计占用时长。
- 总座位时长 = 座位数量 * 仿真总时长。
- 座位利用率 = 总占用时长 / 总座位时长。

输出：

- `seat_utilization`

## 5. 异常和缺失数据处理

- 指标无法计算时输出 `null`。
- 单个学生缺失配对事件时，不计入对应平均值。
- 出现负时长时，丢弃该样本并记录问题。
- 没有窗口数据时，`stall_queue_stats` 输出空数组。
- 没有座位数据时，`seat_utilization` 输出 `null`。

## 6. 暂不做

P0 数据处理暂不做：

- `lost_students`
- 平均队列长度 `avg_queue_length`
- 指定时段平均在场人数
- 各入口流量
- 各出口流量
- 各桌型利用率
- 菜品销量
- 菜品库存分析
- 订单处理时间分析

## 7. 联调验收

数据处理 P0 联调通过标准：

- 能接收后端 `EventRecordP0`。
- 能输出 `StatsFrameP0`。
- 前端能展示 `StatsFrameP0`。
- 固定 `seed` 下统计结果可复现。
- 统计口径和 `business_logic_draft.md` 一致。
