#!/bin/bash
# 解压
tar -xvf percona-xtrabackup-8.0.35-30-Linux-x86_64.glibc2.17.tar.gz

# 改名
mv percona-xtrabackup-8.0.35-30-Linux-x86_64.glibc2.17 xtrabackup-8.0.35

# 设置环境变量
export PATH="$(pwd)/xtrabackup-8.0.35/bin:$PATH"
echo 'export PATH='"\"$(pwd)/xtrabackup-8.0.35/bin:\$PATH\"" >> ~/.bashrc