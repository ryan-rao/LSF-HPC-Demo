#!/bin/bash
# LSF 集群压力测试: lsf_stress.sh —— 多批次大压力混合负载
# 以一个父作业运行, 每批次提交混合子作业(需求48槽 > 集群40槽, 制造排队压力),
# 等待全部完成后统计, 共 3 批次。输出兼容 demo 门户解析。
# 用法: 由 /data/hpc/lsf_bench.sh STRESS 调度 (bsub -n 2 -R span[ptile=1])

BENCH=STRESS
T0=$(date +%s)
export MPI_HOME=/usr/lib64/openmpi
B=/data/hpc/lsf_bench.sh
LOG=/data/hpc/lsf_logs/stress_child.%J.out

elapsed() { echo $(( $(date +%s) - T0 )); }
log() { echo "[$(date '+%F %T')] [STRESS] $*"; }

echo "=== LSF job $LSB_JOBID bench=STRESS NP=$LSB_JOBID hosts: $LSB_MCPU_HOSTS"
log "压力测试启动: 3 批次, 每批次 7 个子作业共 48 槽需求 (集群 40 槽)"
RC=0; TOTAL=0; DONE_C=0; EXIT_C=0

submit_batch() {  # 提交一个批次的子作业, 输出 jobid 列表
  bsub -J st_HACC_IO_A -n 8 -R "span[ptile=2]" -o $LOG $B HACC_IO
  bsub -J st_HACC_IO_B -n 8 -R "span[ptile=2]" -o $LOG $B HACC_IO
  bsub -J st_HACC_OC_A -n 8 -R "span[ptile=2]" -o $LOG $B HACC_OPEN_CLOSE
  bsub -J st_HACC_OC_B -n 8 -R "span[ptile=2]" -o $LOG $B HACC_OPEN_CLOSE
  bsub -J st_BTIO_A   -n 4 -R "span[ptile=1]" -o $LOG $B BTIO
  bsub -J st_BTIO_B   -n 4 -R "span[ptile=1]" -o $LOG $B BTIO
  bsub -J "st_arr[1-8]" -n 1 -o $LOG bash -c 'i=$LSB_JOBINDEX; end=$(( $(date +%s) + 120 )); n=0; while [ $(date +%s) -lt $end ]; do i=$((i*i)); n=$((n+1)); done; echo arr_$LSB_JOBINDEX n=$n'
}

for batch in 1 2 3; do
  log "BATCH $batch/3 提交 (2×HACC_IO + 2×HACC_OC + 2×BTIO + 1×数组[1-8]), elapsed=$(elapsed)s"
  ids=$(submit_batch 2>&1 | grep -oE "Job <[0-9]+>" | grep -oE "[0-9]+")
  n=$(echo "$ids" | wc -w)
  TOTAL=$((TOTAL + n))
  log "BATCH $batch/3 已提交 $n 个子作业: $(echo $ids | tr '\n' ' ')"
  # 等待本批次全部结束
  while :; do
    pend=0
    for j in $ids; do
      st=$(bjobs -noheader -o "stat" $j 2>/dev/null | awk '{print $1}')
      case "$st" in DONE) ;; EXIT) ;; *) pend=$((pend+1));; esac
    done
    [ $pend -eq 0 ] && break
    log "  BATCH $batch 等待中: $pend 个子作业未完成, elapsed=$(elapsed)s"
    sleep 20
  done
  for j in $ids; do
    st=$(bjobs -noheader -o "stat" $j 2>/dev/null | awk '{print $1}')
    if [ "$st" = "DONE" ]; then DONE_C=$((DONE_C+1)); else EXIT_C=$((EXIT_C+1)); RC=1; fi
  done
  log "BATCH $batch/3 完成: 累计 DONE=$DONE_C EXIT=$EXIT_C, elapsed=$(elapsed)s"
done

log "压力测试汇总: 3 批次共 $TOTAL 个子作业, DONE=$DONE_C EXIT=$EXIT_C, 总时长 $(elapsed)s, 吞吐 $(echo "scale=2; $TOTAL*3600/$(elapsed)" | bc) jobs/hour"
echo "=== STRESS exit=$RC"
exit $RC
