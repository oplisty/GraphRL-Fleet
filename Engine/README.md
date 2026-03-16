# task_B（B组协作整理版）

这个目录集中放置已开发完成的 B 组资源，原工程保持不动。

## 目录

- `Framework/`：仿真内核、调度、示例脚本、YAML 配置
- `Map Resource/`：番禺地图、预处理数据、处理脚本、分析结果
- `docs/`：精简文档

## 推荐运行

先安装依赖：

```bash
pip install -r Engine/requirements.txt
```

在仓库根目录运行：

```bash
python -m task_B.Framework.examples.run_panyu_processed_baseline \
  --config "task_B/Framework/configs/panyu_processed_baseline.yaml"
```

或者进入 `task_B` 后运行：

```bash
cd task_B
python -m Framework.examples.run_panyu_processed_baseline \
  --config "Framework/configs/panyu_processed_baseline.yaml"
```

## 说明

- 保留了 `Framework/output/experiment_matrix/summary.*` 作为现成对比结果。
- 其他大量中间输出不复制，避免目录臃肿。
- 默认基线仍是单车单任务（`collaborative_task_ratio=0.0`），协同任务为可选扩展。
