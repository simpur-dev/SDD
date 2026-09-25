#!/usr/bin/env bash
set -e
echo "##### 1) 准备 powercontext v1.1.0 源码 #####"
bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/prep_powercontext.sh
echo "##### 2) 用官方 Dockerfile 构建 #####"
bash /mnt/e/2026ob_projects/SDD/specweaver/deploy/wsl/build.sh
echo UPGRADE_BUILD_DONE
