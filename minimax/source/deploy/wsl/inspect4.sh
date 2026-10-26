#!/usr/bin/env bash
echo "== 相关镜像（含 dangling）=="
docker images -a | grep -iE "powercontext|powermem|REPOSITORY"
echo
echo "== tag powercontext-server:local 指向 =="
docker image inspect powercontext-server:local --format 'Id={{.Id}}|Created={{.Created}}|Entrypoint={{.Config.Entrypoint}}|Cmd={{.Config.Cmd}}' 2>&1
echo "== 旧镜像 325fb631 =="
docker image inspect 325fb631 --format 'Id={{.Id}}|Created={{.Created}}|Tags={{.RepoTags}}|Entrypoint={{.Config.Entrypoint}}' 2>&1
echo "== 新构建 c7852cb4 =="
docker image inspect c7852cb4 --format 'Id={{.Id}}|Created={{.Created}}|Tags={{.RepoTags}}|Entrypoint={{.Config.Entrypoint}}' 2>&1
echo INSPECT4_DONE
