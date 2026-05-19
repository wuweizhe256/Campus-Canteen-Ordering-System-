# 北京交通大学就餐仿真系统

基于 PyQt6 的校园食堂就餐仿真桌面应用，模拟学生排队取餐、就餐、离场等流程，实时展示仿真状态与统计结果。

## 环境配置

- Python 3.10
- PyQt6 >= 6.7, < 7

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Git 协作规范

### 分支与分工

| 分支 | 负责人 | 职责 |
| --- | --- | --- |
| `wuweizhe` | 杨溢鑫 | 前端界面与可视化 |
| `TianZhiJiu-state-flow` | 郝欣冉 | 后端仿真模型与业务逻辑 |
| `thunder` | 汪振龙 | 数据处理、文档编写、项目总览 |
| `dev` | 汪振龙 | 联调测试、分支整合 |
| `main` | — | 最终稳定版本，禁止直接开发 |

### 工作流程

1. 在自己的分支上开发，完成后 push 到远程
2. 由 thunder 在 `dev` 分支上合并各开发分支并进行联调测试
3. 测试通过后合并 `dev` → `main`

### 基本操作

```bash
# 拉取最新代码
git checkout 自己的分支
git pull origin 自己的分支

# 提交代码
git add . 或 git add 要提交的额文件路径
git commit -m "type(scope): 中文说明修改内容"
```

提交信息需要符合 Conventional Commit 规范，格式如下：

| 部分 | 是否必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `type` | 是 | 提交类型，说明本次变更的类别 | `feat`、`fix`、`docs` |
| `scope` | 否 | 影响范围，通常填写模块、页面或文件名 | `models`、`views`、`README` |
| `subject` | 是 | 冒号后面的提交说明必须使用中文，简短说明本次修改内容 | `添加订单状态更新` |

常用提交类型：

| 类型 | 含义 | 示例 |
| --- | --- | --- |
| `feat` | 新增功能 | `feat(order): 添加取餐码` |
| `fix` | 修复问题 | `fix(ui): 修正按钮布局` |
| `docs` | 文档修改 | `docs(readme): 添加提交规范说明` |
| `style` | 代码格式调整，不影响逻辑 | `style(models): 格式化导入语句` |
| `refactor` | 重构代码，不新增功能或修复问题 | `refactor(engine): 简化仿真流程` |
| `test` | 新增或修改测试 | `test(order): 添加队列测试` |
| `chore` | 构建、依赖、配置等杂项修改 | `chore(deps): 更新依赖配置` |

```bash
git push origin 自己的分支

# 同步 dev 最新内容到自己的分支
git merge origin/dev
```

### 注意事项

- 不要直接在 `main` 或 `dev` 上开发
- 优先修改自己负责的目录，减少冲突
- 新增依赖写入 `requirements.txt`
- 不要提交虚拟环境、缓存、IDE 配置等临时文件

## 项目结构

```
├── models/        # 仿真模型与业务逻辑
├── controllers/   # 控制器与线程调度
├── views/         # PyQt6 界面组件
├── utils/         # 通用工具函数
├── config/        # 配置文件
├── tests/         # 单元测试
├── scripts/       # 辅助脚本
├── docs/          # 项目文档
└── main.py        # 应用入口
```

## 测试

```bash
python -m unittest discover -s tests
```
