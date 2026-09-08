#!/bin/bash
# 混合 HPC 应用: lsf_mixed.sh —— 一个 LSF 作业内串行/MPI/IO/数组式/依赖链多形态混合负载
# 总时长约 30 分钟，每 60s 输出心跳进度，便于 demo 页面观察
# 用法: 由 /data/hpc/lsf_bench.sh MIXED 调度（bsub -n 8 -R span[ptile=2]）

BENCH=MIXED
T0=$(date +%s)
export MPI_HOME=/usr/lib64/openmpi
export PATH=$MPI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$MPI_HOME/lib:$LD_LIBRARY_PATH
INSTALL_PATH=/data/hpc/hpc-bench-main

HF=/tmp/hf.$LSB_JOBID; : > $HF
set -- $LSB_MCPU_HOSTS
while [ $# -ge 2 ]; do echo "$1 slots=$2" >> $HF; shift 2; done
NP=$(awk -F"slots=" '{s+=$2} END{print s}' $HF)
OUT=/data/hpc/test_out/lsf_MIXED/$LSB_JOBID
mkdir -p $OUT

log() { echo "[$(date '+%F %T')] [MIXED] $*"; }
elapsed() { echo $(( $(date +%s) - T0 )); }
RC=0

echo "=== LSF job $LSB_JOBID bench=MIXED NP=$NP hosts: $LSB_MCPU_HOSTS"
log "混合 HPC 应用启动: NP=$NP OUT=$OUT 目标时长 1800s"

# ---------- 阶段1: 串行预处理 (120s) ----------
log "PHASE 1/6 串行预处理: 单进程 CPU 计算 + 数据准备 (120s)"
end=$(( $(date +%s) + 120 ))
i=0
while [ $(date +%s) -lt $end ]; do
  i=$(( i + 1 ))
  head -c 4M /dev/urandom | cksum > /dev/null
done
log "PHASE 1/6 完成: $i 轮串行计算, elapsed=$(elapsed)s"

# ---------- 阶段2: MPI 并行计算 (~60s) ----------
log "PHASE 2/6 MPI 并行计算: HACC_OPEN_CLOSE $NP rank"
mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
  $INSTALL_PATH/bin/HACC_OPEN_CLOSE 1000000 $OUT/phase2 && RC2=0 || RC2=1
[ $RC2 -ne 0 ] && RC=$RC2
log "PHASE 2/6 完成: MPI 计算退出码=$RC2, elapsed=$(elapsed)s"
sleep 30

# ---------- 阶段3: 数组式并行任务组 (4 worker × 480s) ----------
log "PHASE 3/6 数组式并行任务组: 4 个独立 worker 并行 (480s)"
for w in 1 2 3 4; do
  (
    end=$(( $(date +%s) + 480 )); n=0
    while [ $(date +%s) -lt $end ]; do
      n=$(( n + 1 ))
      printf "worker%02d-%03d: %s\n" "$w" "$n" "$(date +%T)" >> $OUT/worker_$w.txt
      sleep 5
    done
  ) &
done
wait
log "PHASE 3/6 完成: 4 worker 输出 $(wc -l < $OUT/worker_*.txt | tail -1), elapsed=$(elapsed)s"

# ---------- 阶段4: MPI IO 阶段 (~150s) ----------
log "PHASE 4/6 MPI 集体 IO: HACC_IO $NP rank"
mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
  $INSTALL_PATH/bin/HACC_IO 1000000 $OUT/phase4 -w && RC4=0 || RC4=1
[ $RC4 -ne 0 ] && RC=$RC4
log "PHASE 4/6 完成: MPI IO 退出码=$RC4, elapsed=$(elapsed)s"

# ---------- 阶段5: 依赖链 chain A→B→C (3×120s) ----------
log "PHASE 5/6 依赖链: chain_A -> chain_B -> chain_C 顺序执行"
for st in chain_A chain_B chain_C; do
  echo "$st start $(date +%T)" >> $OUT/chain.log; sleep 120
  echo "$st done  $(date +%T)" >> $OUT/chain.log
  log "  $st 完成, elapsed=$(elapsed)s"
done

# ---------- 阶段6: 汇总校验 + 补足至 1800s ----------
log "PHASE 6/6 结果校验与收尾"
ls -l $OUT > $OUT/manifest.txt
FILES=$(ls $OUT | wc -l)
log "输出文件数=$FILES (worker_1-4/phase2/phase4/chain.log/manifest)"

REMAIN=$(( 1800 - $(elapsed) ))
if [ $REMAIN -gt 0 ]; then
  log "补足时长: 再等 $REMAIN s 至 30 分钟目标"
  end=$(( $(date +%s) + REMAIN ))
  while [ $(date +%s) -lt $end ]; do
    echo "[$(date '+%F %T')] [MIXED] heartbeat elapsed=$(elapsed)s" 
    sleep 60
  done
fi

rm -f $HF
log "混合 HPC 应用全部完成: 总时长 $(elapsed)s, 退出码=$RC"
echo "=== MIXED exit=$RC"
exit $RC
