#!/usr/bin/env bash
#
# 一鍵重新打包並更新 AgentCore Runtime。
#
# 元件：orchestrator / repair / taxi / medical
#
# 用法：
#   scripts/deploy.sh                  # 部署全部四個元件
#   scripts/deploy.sh orchestrator     # 只部署 orchestrator
#   scripts/deploy.sh repair taxi      # 部署指定元件
#   scripts/deploy.sh --dry-run all    # 只打包與檢查，不上傳 / 不更新
#
# 前置需求：
#   - AWS CLI 已設定好具備下列權限的 credentials：
#       s3:PutObject、bedrock-agentcore-control:GetAgentRuntime / UpdateAgentRuntime
#   - uv（下載 ARM64 wheels）、python3、zip、unzip
#
# 行為說明：
#   - 從既有 Runtime 讀取目前的 artifact（S3 位置）、role、network、protocol、
#     environmentVariables，更新時原樣沿用，只換掉程式碼；不會清空環境變數。
#   - 依賴會快取在 /tmp/deploy-<元件>-deps，重跑很快；要強制重建設 FORCE_DEPS=1。
#   - 前端（frontend/server.py 與 web/index.html）不是 Runtime，不由本腳本處理，
#     只要重啟前端 process 即可。
#
set -euo pipefail

# ---- 可覆寫設定 ----------------------------------------------------------
REGION="${AWS_REGION:-us-west-2}"
PY_VERSION="${PY_VERSION:-3.11}"
PY_PLATFORM="${PY_PLATFORM:-aarch64-manylinux2014}"

ORCH_RUNTIME_ID="${ORCH_RUNTIME_ID:-orchestrator-B7uJuFGYRT}"
REPAIR_RUNTIME_ID="${REPAIR_RUNTIME_ID:-repair_specialist-WCdztwHnmX}"
TAXI_RUNTIME_ID="${TAXI_RUNTIME_ID:-taxi_specialist-mKAjnDD2q2}"
MEDICAL_RUNTIME_ID="${MEDICAL_RUNTIME_ID:-medical_specialist-UvOi1ZGIfR}"

FORCE_DEPS="${FORCE_DEPS:-0}"
DRY_RUN=0
# -------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log()  { printf '\033[1;36m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[deploy]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[deploy] 錯誤：\033[0m %s\n' "$*" >&2; exit 1; }

require_tool() { command -v "$1" >/dev/null 2>&1 || die "找不到必要工具：$1"; }

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# 解析參數
COMPONENTS=()
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage 0 ;;
    --dry-run) DRY_RUN=1 ;;
    all)       COMPONENTS=(orchestrator repair taxi medical) ;;
    orchestrator|repair|taxi|medical) COMPONENTS+=("$arg") ;;
    *) die "未知參數：$arg（可用：orchestrator repair taxi medical all --dry-run --help）" ;;
  esac
done
# 沒指定元件就部署全部
if [ "${#COMPONENTS[@]}" -eq 0 ]; then
  COMPONENTS=(orchestrator repair taxi medical)
fi

require_tool aws
require_tool python3
[ "$DRY_RUN" -eq 1 ] || require_tool uv
[ "$FORCE_DEPS" -eq 1 ] && require_tool uv

# 每個元件的設定：runtime id、requirements、entryPoint（zip 內路徑）、要複製的來源
component_config() {
  case "$1" in
    orchestrator)
      RUNTIME_ID="$ORCH_RUNTIME_ID"
      REQ_FILE="apps/orchestrator/requirements.txt"
      ENTRYPOINT="apps/orchestrator/main.py"
      ;;
    repair)
      RUNTIME_ID="$REPAIR_RUNTIME_ID"
      REQ_FILE="agents/repair/requirements.txt"
      ENTRYPOINT="agents/repair/main.py"
      ;;
    taxi)
      RUNTIME_ID="$TAXI_RUNTIME_ID"
      REQ_FILE="agents/taxi/requirements.txt"
      ENTRYPOINT="agents/taxi/main.py"
      ;;
    medical)
      RUNTIME_ID="$MEDICAL_RUNTIME_ID"
      REQ_FILE="agents/medical/requirements.txt"
      ENTRYPOINT="agents/medical/main.py"
      ;;
    *) die "未知元件：$1" ;;
  esac
}

# 把該元件的原始碼複製進 build root
copy_sources() {
  local comp="$1" build="$2"
  case "$comp" in
    orchestrator)
      cp -r apps shared adapters "$build/"
      ;;
    repair|taxi|medical)
      mkdir -p "$build/agents"
      cp agents/__init__.py "$build/agents/"
      cp -r "agents/$comp" "$build/agents/"
      cp -r shared "$build/"
      ;;
  esac
  # 移除 __pycache__，避免打包多餘檔案
  find "$build" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
}

# 讀取既有 Runtime 設定，寫出 update 需要的 JSON 檔，並回填 S3 bucket/prefix
read_current_runtime() {
  local runtime_id="$1" meta="$2"
  local raw
  raw="$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$runtime_id" --region "$REGION" 2>/dev/null)" \
    || die "讀取 Runtime 失敗：$runtime_id（確認 ID 與 AWS 權限）"

  RUNTIME_META="$raw" python3 - "$meta" <<'PY'
import json, os, sys
meta = sys.argv[1]
data = json.loads(os.environ["RUNTIME_META"])

artifact = data.get("agentRuntimeArtifact") or {}
code = (artifact.get("codeConfiguration") or {}).get("code") or {}
s3 = code.get("s3") or {}
bucket, prefix = s3.get("bucket"), s3.get("prefix")
if not bucket or not prefix:
    sys.stderr.write("此 Runtime 不是 S3 CodeZip 部署，無法用本腳本更新程式碼。\n")
    sys.exit(3)

def dump(name, obj):
    with open(os.path.join(meta, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)

dump("artifact.json", artifact)
if data.get("roleArn"):
    open(os.path.join(meta, "role_arn.txt"), "w").write(data["roleArn"])
if data.get("networkConfiguration"):
    dump("network.json", data["networkConfiguration"])
if data.get("protocolConfiguration"):
    dump("protocol.json", data["protocolConfiguration"])
if data.get("environmentVariables"):
    dump("env.json", data["environmentVariables"])

open(os.path.join(meta, "s3_bucket.txt"), "w").write(bucket)
open(os.path.join(meta, "s3_prefix.txt"), "w").write(prefix)
PY

  S3_BUCKET="$(cat "$meta/s3_bucket.txt")"
  S3_PREFIX="$(cat "$meta/s3_prefix.txt")"
}

deploy_component() {
  local comp="$1"
  component_config "$comp"

  local deps_dir="/tmp/deploy-${comp}-deps"
  local build_dir="/tmp/deploy-${comp}-build"
  local zip_path="/tmp/deploy-${comp}.zip"
  local meta_dir="/tmp/deploy-${comp}-meta"

  log "===== ${comp}（runtime=${RUNTIME_ID}）====="

  # 1) 依賴（快取）
  if [ "$FORCE_DEPS" -eq 1 ] || [ ! -d "$deps_dir" ] || [ -z "$(ls -A "$deps_dir" 2>/dev/null)" ]; then
    if [ "$DRY_RUN" -eq 1 ] && ! command -v uv >/dev/null 2>&1; then
      warn "dry-run 且無 uv，略過依賴安裝；zip 內不含第三方套件。"
      mkdir -p "$deps_dir"
    else
      log "安裝 ARM64 依賴 -> $deps_dir"
      rm -rf "$deps_dir"; mkdir -p "$deps_dir"
      UV_CACHE_DIR="/tmp/deploy-${comp}-uvcache" uv pip install \
        --target "$deps_dir" \
        --python-platform "$PY_PLATFORM" \
        --python-version "$PY_VERSION" \
        --only-binary=:all: \
        -r "$REQ_FILE"
    fi
  else
    log "重用已快取依賴：$deps_dir（FORCE_DEPS=1 可重建）"
  fi

  # 2) 組裝 build root = 依賴 + 最新原始碼
  log "組裝 build root -> $build_dir"
  rm -rf "$build_dir"; mkdir -p "$build_dir"
  cp -r "$deps_dir/." "$build_dir/" 2>/dev/null || true
  find "$build_dir" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  copy_sources "$comp" "$build_dir"

  # 3) 確認 entrypoint 存在
  [ -f "$build_dir/$ENTRYPOINT" ] || die "build root 缺少 entrypoint：$ENTRYPOINT"

  # 4) 打包（使用 python zipfile，免 zip/unzip CLI）並驗證 entrypoint
  log "打包 -> $zip_path"
  rm -f "$zip_path"
  local zsize
  zsize="$(python3 - "$build_dir" "$zip_path" "$ENTRYPOINT" <<'PY'
import os, sys, zipfile
build, zippath, entry = sys.argv[1:4]
with zipfile.ZipFile(zippath, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(build):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".pyc"):
                continue
            full = os.path.join(root, name)
            z.write(full, os.path.relpath(full, build))
    names = set(z.namelist())
if entry not in names:
    sys.stderr.write("entrypoint missing in zip: %s\n" % entry)
    sys.exit(4)
print(os.path.getsize(zippath))
PY
)" || die "打包失敗或 zip 內找不到 entrypoint：$ENTRYPOINT"
  log "zip 完成：$(( zsize / 1024 )) KB，entrypoint=$ENTRYPOINT"

  if [ "$DRY_RUN" -eq 1 ]; then
    warn "dry-run：略過讀取 Runtime、S3 上傳與 update-agent-runtime。"
    return 0
  fi

  # 5) 讀取既有 Runtime 設定（保留 role/network/protocol/env）
  rm -rf "$meta_dir"; mkdir -p "$meta_dir"
  log "讀取既有 Runtime 設定…"
  read_current_runtime "$RUNTIME_ID" "$meta_dir"
  log "目標 S3：s3://${S3_BUCKET}/${S3_PREFIX}"

  # 6) 上傳程式碼
  log "上傳 zip 到 S3…"
  aws s3 cp "$zip_path" "s3://${S3_BUCKET}/${S3_PREFIX}" --region "$REGION"

  # 7) 更新 Runtime（沿用現有設定）
  local args=( --agent-runtime-id "$RUNTIME_ID"
               --agent-runtime-artifact "file://$meta_dir/artifact.json"
               --region "$REGION" )
  [ -f "$meta_dir/role_arn.txt" ] && args+=( --role-arn "$(cat "$meta_dir/role_arn.txt")" )
  [ -f "$meta_dir/network.json" ] && args+=( --network-configuration "file://$meta_dir/network.json" )
  [ -f "$meta_dir/protocol.json" ] && args+=( --protocol-configuration "file://$meta_dir/protocol.json" )
  [ -f "$meta_dir/env.json" ] && args+=( --environment-variables "file://$meta_dir/env.json" )

  log "呼叫 update-agent-runtime…"
  local out
  out="$(aws bedrock-agentcore-control update-agent-runtime "${args[@]}")" \
    || die "update-agent-runtime 失敗：$comp"
  local ver
  ver="$(printf '%s' "$out" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("agentRuntimeVersion","?"))' 2>/dev/null || echo '?')"
  log "✅ ${comp} 更新完成，新版本：${ver}"
}

log "區域=$REGION｜元件=${COMPONENTS[*]}｜dry-run=$DRY_RUN"
for comp in "${COMPONENTS[@]}"; do
  deploy_component "$comp"
done

log "全部完成。建議接著執行： .venv/bin/python -u verify_remote.py"
log "並確認回應的 specialist_backend=agentcore（非 fake-fallback）。"
