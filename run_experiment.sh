#!/bin/bash
# 实验运行脚本
# 使用方法：./run_experiment.sh <experiment_type> [args...]

set -e

# 获取脚本所在目录（项目根目录）
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# 设置 PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:${PROJECT_ROOT}/Engine:${PROJECT_ROOT}"

# 激活 conda 环境（如果需要）
# conda activate datastructure

case "$1" in
  baseline)
    shift
    python -m Framework.examples.run_baseline "$@"
    ;;
  
  qlearning)
    shift
    python -m policy.gymnasium_qlearning.train_q_learning "$@"
    ;;
  
  milp)
    shift
    python -m policy.offline.god_view_milp "$@"
    ;;
  
  matrix)
    shift
    python -m Framework.examples.run_experiment_matrix "$@"
    ;;
  
  *)
    echo "Usage: $0 <experiment_type> [args...]"
    echo ""
    echo "Experiment types:"
    echo "  baseline   - Run single baseline experiment"
    echo "  qlearning  - Train Q-learning agent"
    echo "  milp       - Run MILP solver"
    echo "  matrix     - Run experiment matrix"
    echo ""
    echo "Examples:"
    echo "  $0 baseline --scale small --scheduler nearest --out experiments/test"
    echo "  $0 qlearning --scale small --episodes 200 --out-dir experiments/qlearning"
    echo "  $0 milp --scale small --solver gurobi --out experiments/milp"
    exit 1
    ;;
esac
