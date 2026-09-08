#!/bin/bash
# 通用 LSF -> MPI 调度器: lsf_bench.sh <BTIO|MADbench|s3d_io|HACC_OPEN_CLOSE|HACC_IO>
BENCH=$1
export MPI_HOME=/usr/lib64/openmpi
export PATH=$MPI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$MPI_HOME/lib:$LD_LIBRARY_PATH
INSTALL_PATH=/data/hpc/hpc-bench-main

HF=/tmp/hf.$LSB_JOBID; : > $HF
set -- $LSB_MCPU_HOSTS
while [ $# -ge 2 ]; do echo "$1 slots=$2" >> $HF; shift 2; done
NP=$(awk -F"slots=" '{s+=$2} END{print s}' $HF)
OUT=/data/hpc/test_out/lsf_$BENCH/$LSB_JOBID
mkdir -p $OUT
echo "=== LSF job $LSB_JOBID bench=$BENCH NP=$NP hosts: $LSB_MCPU_HOSTS"

case $BENCH in
  BTIO)            mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP $INSTALL_PATH/bin/BTIO -m w -t 0 -g 32,32,32 -i 1 -o $OUT ;;
  MADbench)        mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP $INSTALL_PATH/bin/MADbench 512 $NP 1 UNIQUE $OUT ;;
  s3d_io)          mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP $INSTALL_PATH/bin/s3d_io -g 32,32,32 -p 2,2,2 -i 1 -d $OUT ;;
  HACC_OPEN_CLOSE) mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP $INSTALL_PATH/bin/HACC_OPEN_CLOSE 1000000 $OUT ;;
  MIXED)           exec /data/hpc/lsf_mixed.sh ;; # 混合应用
  STRESS)          exec /data/hpc/lsf_stress.sh ;; # 压力测试
  HACC_IO)         mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP $INSTALL_PATH/bin/HACC_IO 1000000 $OUT -w ;;
esac
RC=$?; rm -f $HF
echo "=== $BENCH exit=$RC"
exit $RC

