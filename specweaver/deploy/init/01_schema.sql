-- ============================================================================
-- SpecWeaver · seekdb 参考 Schema（与《架构设计说明书》第 4 章一致）
-- 说明：
--   1. seekdb 兼容 MySQL 语法并扩展 VECTOR / FULLTEXT / HNSW；堆表 ORGANIZATION HEAP。
--   2. 本脚本为“参考/手动初始化”用途；正式流程中由 SpecWeaver 后端适配器在
--      `specweaver init` 时自动执行，无需手动跑。
--   3. VECTOR 维度（示例 1024）需与所用 Embedding 模型实际维度保持一致。
-- ============================================================================

CREATE DATABASE IF NOT EXISTS specweaver;
USE specweaver;

-- 项目表 ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sw_project (
  project_id    VARCHAR(64) PRIMARY KEY,
  name          VARCHAR(255),
  root_uri      VARCHAR(1024),
  current_ref   VARCHAR(255),
  created_at    DATETIME
) ORGANIZATION HEAP;

-- 工程要素主表（五类统一）----------------------------------------------------
CREATE TABLE IF NOT EXISTS sw_artifact (
  artifact_id     VARCHAR(96) PRIMARY KEY,
  project_id      VARCHAR(64),
  type            VARCHAR(16),
  module          VARCHAR(64),
  title           VARCHAR(512),
  content         TEXT,
  version         VARCHAR(32),
  status          VARCHAR(16),
  effective_from  DATETIME,
  effective_to    DATETIME,
  applies_to_ref  VARCHAR(255),
  supersedes      VARCHAR(96),
  superseded_by   VARCHAR(96),
  source_uri      VARCHAR(1024),
  source_locator  VARCHAR(128),
  checksum        VARCHAR(128),
  tags            VARCHAR(512),
  embedding       VECTOR(1024),
  created_at      DATETIME,
  updated_at      DATETIME,
  FULLTEXT INDEX ft_artifact_title(title),
  FULLTEXT INDEX ft_artifact_content(content),
  VECTOR INDEX idx_artifact_emb(embedding)
      WITH (distance=l2, type=hnsw, lib=vsag)
) ORGANIZATION HEAP;

-- 关联图谱（边表）------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sw_relation (
  id          BIGINT PRIMARY KEY,
  project_id  VARCHAR(64),
  src_id      VARCHAR(96),
  src_type    VARCHAR(16),
  dst_id      VARCHAR(96),
  dst_type    VARCHAR(16),
  relation    VARCHAR(32),
  confidence  DOUBLE,
  evidence    VARCHAR(1024),
  created_at  DATETIME
) ORGANIZATION HEAP;

-- 开发任务 -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sw_task (
  task_id     VARCHAR(64) PRIMARY KEY,
  project_id  VARCHAR(64),
  title       VARCHAR(512),
  objective   TEXT,
  status      VARCHAR(16),
  branch      VARCHAR(255),
  base_ref    VARCHAR(255),
  handoff_rev VARCHAR(128),
  created_at  DATETIME,
  closed_at   DATETIME
) ORGANIZATION HEAP;

-- 任务事件 / 操作日志 ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS sw_event (
  event_id    BIGINT PRIMARY KEY,
  task_id     VARCHAR(64),
  phase       VARCHAR(32),
  action      VARCHAR(64),
  payload     JSON,
  citations   JSON,
  ts          DATETIME
) ORGANIZATION HEAP;

-- 变更集 ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sw_change_set (
  change_id       VARCHAR(64) PRIMARY KEY,
  task_id         VARCHAR(64),
  diff_uri        VARCHAR(1024),
  files_changed   JSON,
  test_run_id     VARCHAR(64),
  base_checksum   VARCHAR(128),
  head_checksum   VARCHAR(128),
  ts              DATETIME
) ORGANIZATION HEAP;

-- 测试运行结果 ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sw_test_run (
  test_run_id VARCHAR(64) PRIMARY KEY,
  task_id     VARCHAR(64),
  command     VARCHAR(1024),
  total       INT,
  passed      INT,
  failed      INT,
  skipped     INT,
  report_uri  VARCHAR(1024),
  commit_ref  VARCHAR(255),
  ts          DATETIME
) ORGANIZATION HEAP;
