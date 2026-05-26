#!/bin/bash
# 批量运行所有对比实验
# 使用方法：./run_all_experiments.sh

set -e
set -o pipefail

# 获取脚本所在目录（项目根目录）
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# 设置 PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:${PROJECT_ROOT}/Engine:${PROJECT_ROOT}"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# 分隔线
print_separator() {
    echo -e "${CYAN}================================================================${NC}"
}

print_header() {
    print_separator
    echo -e "${WHITE}$1${NC}"
    print_separator
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 实验计数器
TOTAL_EXPERIMENTS=0
COMPLETED_EXPERIMENTS=0
FAILED_EXPERIMENTS=0

# 记录开始时间
START_TIME=$(date +%s)

print_header "开始批量实验运行"
print_info "项目根目录: $PROJECT_ROOT"
print_info "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ============================================================
# 第一部分：基线对比实验
# ============================================================

print_header "第一部分：基线对比实验（Baseline Comparison）"
echo ""

SCALES=("small" "medium" "large")
SCHEDULERS=("nearest" "earliest_deadline" "heaviest")
SEEDS=(7 8 9 10 11)

for scale in "${SCALES[@]}"; do
    for scheduler in "${SCHEDULERS[@]}"; do
        for seed in "${SEEDS[@]}"; do
            TOTAL_EXPERIMENTS=$((TOTAL_EXPERIMENTS + 1))
            
            print_info "实验 [$TOTAL_EXPERIMENTS]: Scale=$scale, Scheduler=$scheduler, Seed=$seed"
            
            OUT_DIR="experiments/baselines/${scale}_${scheduler}_seed${seed}"
            
            if python -m Framework.examples.run_baseline \
                --scale "$scale" \
                --scheduler "$scheduler" \
                --seed "$seed" \
                --charging-strategy optimal_station \
                --out "$OUT_DIR" 2>&1 | grep -E "(Simulation Summary|total_score|completed|expired)"; then
                
                COMPLETED_EXPERIMENTS=$((COMPLETED_EXPERIMENTS + 1))
                print_success "完成 [$COMPLETED_EXPERIMENTS/$TOTAL_EXPERIMENTS]"
            else
                FAILED_EXPERIMENTS=$((FAILED_EXPERIMENTS + 1))
                print_error "失败 [$TOTAL_EXPERIMENTS]"
            fi
            
            print_separator
            echo ""
        done
    done
done

# ============================================================
# 第二部分：Q-learning 训练
# ============================================================

print_header "第二部分：Q-learning 超启发式训练"
echo ""

# Q-learning Small 规模训练
TOTAL_EXPERIMENTS=$((TOTAL_EXPERIMENTS + 1))
print_info "实验 [$TOTAL_EXPERIMENTS]: Q-learning 训练 (Small, 200 episodes)"

if python -m policy.gymnasium_qlearning.train_q_learning \
    --scale small \
    --episodes 200 \
    --max-steps 180 \
    --seed 7 \
    --out-dir experiments/qlearning/small 2>&1 | tail -20; then
    
    COMPLETED_EXPERIMENTS=$((COMPLETED_EXPERIMENTS + 1))
    print_success "完成 [$COMPLETED_EXPERIMENTS/$TOTAL_EXPERIMENTS]"
else
    FAILED_EXPERIMENTS=$((FAILED_EXPERIMENTS + 1))
    print_error "失败 [$TOTAL_EXPERIMENTS]"
fi

print_separator
echo ""

# Q-learning Medium 规模训练
TOTAL_EXPERIMENTS=$((TOTAL_EXPERIMENTS + 1))
print_info "实验 [$TOTAL_EXPERIMENTS]: Q-learning 训练 (Medium, 300 episodes)"

if python -m policy.gymnasium_qlearning.train_q_learning \
    --scale medium \
    --episodes 300 \
    --max-steps 300 \
    --seed 7 \
    --out-dir experiments/qlearning/medium 2>&1 | tail -20; then
    
    COMPLETED_EXPERIMENTS=$((COMPLETED_EXPERIMENTS + 1))
    print_success "完成 [$COMPLETED_EXPERIMENTS/$TOTAL_EXPERIMENTS]"
else
    FAILED_EXPERIMENTS=$((FAILED_EXPERIMENTS + 1))
    print_error "失败 [$TOTAL_EXPERIMENTS]"
fi

print_separator
echo ""

# Q-learning Mixed 规模训练
TOTAL_EXPERIMENTS=$((TOTAL_EXPERIMENTS + 1))
print_info "实验 [$TOTAL_EXPERIMENTS]: Q-learning 训练 (Mixed Small+Medium, 300 episodes)"

if python -m policy.gymnasium_qlearning.train_q_learning \
    --scale small \
    --train-scales small medium \
    --episodes 300 \
    --max-steps 300 \
    --seed 7 \
    --out-dir experiments/qlearning/mixed 2>&1 | tail -20; then
    
    COMPLETED_EXPERIMENTS=$((COMPLETED_EXPERIMENTS + 1))
    print_success "完成 [$COMPLETED_EXPERIMENTS/$TOTAL_EXPERIMENTS]"
else
    FAILED_EXPERIMENTS=$((FAILED_EXPERIMENTS + 1))
    print_error "失败 [$TOTAL_EXPERIMENTS]"
fi

print_separator
echo ""

# ============================================================
# 第三部分：消融实验 - 充电策略
# ============================================================

print_header "第三部分：消融实验 - 充电策略对比"
echo ""

CHARGING_STRATEGIES=("optimal_station" "nearest_station")

for strategy in "${CHARGING_STRATEGIES[@]}"; do
    for seed in "${SEEDS[@]}"; do
        TOTAL_EXPERIMENTS=$((TOTAL_EXPERIMENTS + 1))
        
        print_info "实验 [$TOTAL_EXPERIMENTS]: Charging=$strategy, Seed=$seed"
        
        OUT_DIR="experiments/ablation/charging/${strategy}_seed${seed}"
        
        if python -m Framework.examples.run_baseline \
            --scale medium \
            --scheduler nearest \
            --seed "$seed" \
            --charging-strategy "$strategy" \
            --out "$OUT_DIR" 2>&1 | grep -E "(total_score|completed|expired)"; then
            
            COMPLETED_EXPERIMENTS=$((COMPLETED_EXPERIMENTS + 1))
            print_success "完成 [$COMPLETED_EXPERIMENTS/$TOTAL_EXPERIMENTS]"
        else
            FAILED_EXPERIMENTS=$((FAILED_EXPERIMENTS + 1))
            print_error "失败 [$TOTAL_EXPERIMENTS]"
        fi
        
        print_separator
        echo ""
    done
done

# Q-learning 充电策略消融
for strategy in "${CHARGING_STRATEGIES[@]}"; do
    TOTAL_EXPERIMENTS=$((TOTAL_EXPERIMENTS + 1))
    
    print_info "实验 [$TOTAL_EXPERIMENTS]: Q-learning Charging=$strategy"
    if [[ "$strategy" == "optimal_station" ]]; then
        ACTION_MODE="best_charge"
    else
        ACTION_MODE="nearest_charge"
    fi
    
    if python -m policy.gymnasium_qlearning.train_q_learning \
        --scale medium \
        --episodes 200 \
        --charging-strategy "$strategy" \
        --charging-action-mode "$ACTION_MODE" \
        --seed 7 \
        --out-dir "experiments/ablation/qlearning_charging/${strategy}" 2>&1 | tail -15; then
        
        COMPLETED_EXPERIMENTS=$((COMPLETED_EXPERIMENTS + 1))
        print_success "完成 [$COMPLETED_EXPERIMENTS/$TOTAL_EXPERIMENTS]"
    else
        FAILED_EXPERIMENTS=$((FAILED_EXPERIMENTS + 1))
        print_error "失败 [$TOTAL_EXPERIMENTS]"
    fi
    
    print_separator
    echo ""
done

# ============================================================
# 第四部分：MILP 上界（可选）
# ============================================================

print_header "第四部分：MILP 上界求解（可选）"
echo ""

TOTAL_EXPERIMENTS=$((TOTAL_EXPERIMENTS + 1))
print_info "实验 [$TOTAL_EXPERIMENTS]: MILP Gurobi (Small)"
print_warning "如果没有 Gurobi license，此步骤会失败，可以忽略"

if python -m policy.offline.god_view_milp \
    --scale small \
    --solver gurobi \
    --time-limit 120 \
    --out experiments/milp/small_gurobi 2>&1 | tail -20; then
    
    COMPLETED_EXPERIMENTS=$((COMPLETED_EXPERIMENTS + 1))
    print_success "完成 [$COMPLETED_EXPERIMENTS/$TOTAL_EXPERIMENTS]"
else
    FAILED_EXPERIMENTS=$((FAILED_EXPERIMENTS + 1))
    print_warning "MILP 求解失败（可能是缺少 Gurobi license），跳过"
fi

print_separator
echo ""

# ============================================================
# 实验总结
# ============================================================

END_TIME=$(date +%s)
ELAPSED_TIME=$((END_TIME - START_TIME))
HOURS=$((ELAPSED_TIME / 3600))
MINUTES=$(((ELAPSED_TIME % 3600) / 60))
SECONDS=$((ELAPSED_TIME % 60))

print_header "实验运行完成"
echo ""
print_info "总实验数: $TOTAL_EXPERIMENTS"
print_success "成功: $COMPLETED_EXPERIMENTS"
if [ $FAILED_EXPERIMENTS -gt 0 ]; then
    print_error "失败: $FAILED_EXPERIMENTS"
fi
print_info "总耗时: ${HOURS}h ${MINUTES}m ${SECONDS}s"
print_info "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

print_header "实验输出目录"
echo ""
echo -e "${CYAN}基线实验:${NC}       experiments/baselines/"
echo -e "${CYAN}Q-learning:${NC}       experiments/qlearning/"
echo -e "${CYAN}消融实验:${NC}         experiments/ablation/"
echo -e "${CYAN}MILP:${NC}             experiments/milp/"
echo ""

print_header "下一步操作"
echo ""
echo -e "${YELLOW}1.${NC} 查看实验结果:"
echo -e "   ls -lh experiments/baselines/"
echo -e "   ls -lh experiments/qlearning/"
echo ""
echo -e "${YELLOW}2.${NC} 汇总实验数据（需要实现 summarize_results.py）:"
echo -e "   python experiments/summarize_results.py"
echo ""
echo -e "${YELLOW}3.${NC} 生成论文图表"
echo ""

print_separator
