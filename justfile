set positional-arguments

fv := "uv run --no-sync python -m freevideo_engine.managed"

default:
    @just --list

# uvのコマンド・ランチャー環境を復元
sync:
    uv sync --python 3.12 --extra launcher --extra runtime

# ブラウザーUIを起動
start: check-idle
    {{fv}} open

status:
    {{fv}} status

stop:
    {{fv}} stop

# GPU/RAMの現在の使用状況
resources:
    nvidia-smi
    free -h

# 他のGPU処理が動いている場合は生成を開始しない（排他ロックではない）
check-idle:
    @uv run --no-sync python -c 'import subprocess, psutil; rows=subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True).strip().splitlines(); used,util=map(int,rows[0].split(",")); ram=psutil.virtual_memory().available/2**30; print(f"GPU: {used} MiB / {util}%, available RAM: {ram:.1f} GiB"); assert used<1024 and util<5 and ram>=80, "GPU使用中またはRAM不足です。空いてから再実行してください。"'

# プロンプト入力→動画・音声を含むMP4出力（省略時は2秒の短い動画）
e2e prompt="examples/prompt.txt" out="outputs/e2e.mp4" seconds="2": check-idle
    uv run --no-sync python scripts/generate_video.py --prompt-file "$1" --out "$2" --seconds "$3"

# CUIだけで文章からMP4を生成（ブラウザー・サーバー不要）
generate prompt out="outputs/video.mp4" seconds="2": check-idle
    uv run --no-sync python scripts/generate_video.py --prompt "$1" --out "$2" --seconds "$3"

# 公式の複数ケース検証。e2eより長時間GPUを使用
test: check-idle
    {{fv}} test --suite quick --plain --vram-gib 24 --ram-gib 64

# GPUを使わずインストール計画を確認
setup-plan:
    {{fv}} setup --plan --network official --ram-gib 64 --vram-gib 24

# 公式ソースからセットアップ／再開（計画・ライセンス確認あり）
setup:
    {{fv}} setup --network official --ram-gib 64 --vram-gib 24

doctor:
    {{fv}} doctor
