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
| `wuweizhe` | wuweizhe | 前端界面与可视化 |
| `TianZhiJiu-state-flow` | TianZhiJiu | 后端仿真模型与业务逻辑 |
| `thunder` | thunder | 数据处理、文档编写、项目总览 |
| `dev` | thunder | 联调测试、分支整合 |
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
git add .
git commit -m "简要说明修改内容"
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
