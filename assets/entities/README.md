# Entity Image Asset Spec

本目录用于存放仿真画布里的实体图片。当前任务只替换/美化展示资源，不改后端状态机和业务逻辑。

所有图片建议使用透明背景 PNG，伪 3D / 等距视角，光源方向统一为左上，阴影方向统一向右下。画面风格要和食堂平面仿真保持一致：明亮、可爱、清晰，俯视偏 3/4 视角，不要完全扁平。

## 目录

- `students/`：学生小猪图片
- `stalls/`：打饭窗口图片
- `tables/`：餐桌和座位图片

## 通用要求

- 格式：PNG
- 背景：透明
- 色彩：明亮、低饱和一点，避免纯黑粗描边
- 视角：伪 3D / isometric / 3/4 top-down
- 边缘：干净，不要带白底、黑底或裁切残边
- 文件名：全部小写英文，下划线分隔
- 不要把状态文字写死在学生图片里；窗口的 `sold_out` 可以挂英文 `SOLD OUT` 牌，因为这是画面元素

## 学生 students

代码状态来自 `models.entities.StudentState`，当前共有 10 个状态。

建议生成尺寸：`128x128`，透明 PNG。画布实际显示会缩放到约 `44x56` 附近，所以主体必须居中、轮廓清楚。建议锚点为底部中心，脚底/座位接触点在图片底部中央附近。

| 状态值 | 中文含义 | 文件名 | 画面要求 |
| --- | --- | --- | --- |
| `deciding` | 决策/选择中 | `student_deciding.png` | 站立小猪，轻微歪头，旁边可有小问号/菜单小气泡，不要太大 |
| `moving_to_queue` | 前往窗口 | `student_moving_to_queue.png` | 走路姿态，手里可以拿手机或饭卡，身体朝右前方 |
| `queued` | 排队取餐 | `student_queued.png` | 站立等待，手持托盘或饭卡，表情期待 |
| `searching_seat` | 寻找座位 | `student_searching_seat.png` | 端着餐盘张望，可有小座位图标/视线方向 |
| `waiting_seat` | 等待空座 | `student_waiting_seat.png` | 站着端餐盘等待，表情稍微无奈，但不要沮丧 |
| `moving_to_seat` | 前往座位 | `student_moving_to_seat.png` | 端着餐盘走向座位，动作比排队状态更明确 |
| `eating` | 吃饭中 | `student_eating.png` | 坐姿小猪，面前有餐盘/碗筷，适合叠在餐桌旁 |
| `moving_to_tray_return` | 前往餐盘回收处 | `student_moving_to_tray_return.png` | 走路姿态，手里拿空托盘/碗筷 |
| `leaving` | 离场中 | `student_leaving.png` | 轻松离开，手空着或挥手，表情满足 |
| `done` | 已离场 | `student_done.png` | 通常不会在活跃画布中显示，可做淡化/半透明离场小猪兜底 |

补充建议：学生图可以做一套统一小猪模板，只改变姿态和手持物。`moving_to_queue`、`moving_to_seat`、`moving_to_tray_return` 可以共享走路基础姿态，但手持物必须不同，避免状态看起来一样。

## 打饭窗口 stalls

代码里的窗口营业状态来自 `models.entities.StallStatus`，共有 3 个：`pending`、`open`、`sold_out`。另外订单状态里有 `cooking`，画布也有 `cook_progress/cook_remaining`，因此图片建议额外准备一个视觉状态 `cooking`，用于前端后续在营业中且正在出餐时优先显示。

建议生成尺寸：`192x192`，透明 PNG。窗口主体建议占中下部，顶部可以留给招牌/菜单板。当前点击热区约 `104x132`，图片不要把关键元素放得太靠边。

| 状态值 | 中文含义 | 文件名 | 画面要求 |
| --- | --- | --- | --- |
| `pending` | 待营业/未开始 | `stall_pending.png` | 窗口灯暗一点，卷帘半开或准备中，菜单板可空白，柜台整洁 |
| `open` | 营业中/等待学生 | `stall_open.png` | 明亮窗口，有厨师小猪在柜台后，展示菜品托盘、菜单牌、热气 |
| `cooking` | 正在做饭/出餐中 | `stall_cooking.png` | 在 `open` 基础上增加锅、蒸汽、火苗/计时感，厨师小猪忙碌 |
| `sold_out` | 已售罄 | `stall_sold_out.png` | 挂 `SOLD OUT` 牌，菜盘空了，厨师小猪可摊手或擦汗，颜色稍灰但仍美观 |

补充建议：窗口图片元素可以丰富一些：柜台、玻璃展示柜、菜盘、菜单小牌、厨师帽小猪、蒸汽、灯箱。`sold_out` 不要只把普通窗口变灰，要让“售罄”一眼可见。

## 餐桌 tables

代码里的座位状态来自 `models.entities.SeatStatus`，共有 3 个：`free`、`reserved`、`occupied`。餐桌类型当前支持 2 人桌、4 人桌、6 人桌，来自 `Table.table_type/seat_count`。

建议餐桌主体按类型生成，座位状态可以用同一张桌子叠加不同座位状态，也可以直接生成组合图。为了方便前端替换，先按“桌型 + 整桌占用状态”准备基础图。

| 桌型/状态 | 文件名 | 建议尺寸 | 画面要求 |
| --- | --- | --- | --- |
| 2 人桌空闲 | `table_two_free.png` | `128x96` | 小桌 + 两把椅子，桌面干净 |
| 2 人桌预留 | `table_two_reserved.png` | `128x96` | 椅子或桌面有预留小卡片/黄色提示 |
| 2 人桌占用 | `table_two_occupied.png` | `128x96` | 桌面有餐盘/碗筷，座位有使用痕迹，但不要画具体学生以免和学生图重复 |
| 4 人桌空闲 | `table_four_free.png` | `144x128` | 四把椅子，桌面干净 |
| 4 人桌预留 | `table_four_reserved.png` | `144x128` | 部分座位有预留卡/黄色餐巾，整体仍清晰 |
| 4 人桌占用 | `table_four_occupied.png` | `144x128` | 桌面有多套餐具/餐盘 |
| 6 人桌空闲 | `table_six_free.png` | `160x144` | 长桌或大桌 + 六把椅子 |
| 6 人桌预留 | `table_six_reserved.png` | `160x144` | 多个座位可有预留提示 |
| 6 人桌占用 | `table_six_occupied.png` | `160x144` | 桌面更丰富，有餐盘、纸巾、小碗等 |

如果图片 agent 能做更细，可以额外生成单座位贴片：

| 座位状态 | 文件名 | 建议尺寸 | 画面要求 |
| --- | --- | --- | --- |
| `free` | `seat_free.png` | `48x48` | 空椅子 |
| `reserved` | `seat_reserved.png` | `48x48` | 椅子上有预留牌/黄色标记 |
| `occupied` | `seat_occupied.png` | `48x48` | 椅子有餐盘或占用标记，不画完整学生 |

## 给图片生成 Agent 的总提示词

为校园食堂仿真系统生成一套透明背景 PNG 游戏资产，风格为可爱明亮的伪 3D / isometric / 3/4 top-down，光源来自左上，柔和阴影向右下，适合 PyQt 仿真画布小尺寸显示。主体要居中，边缘干净，不能有白底或黑底。学生是小猪角色，窗口和餐桌也是同一食堂风格，整体统一、细节丰富但小尺寸可辨认。

## 验收清单

- 缩小到 40-60 px 时仍能辨认状态
- 透明背景无残边
- 同类图片大小和视角一致
- 学生 `eating` 明确是坐姿，其他等待/移动状态明确是站姿或走姿
- 窗口 `open/cooking/sold_out` 差异明显
- 桌子不画完整学生，避免和学生实体叠在一起混乱
- 文件名和上表完全一致
