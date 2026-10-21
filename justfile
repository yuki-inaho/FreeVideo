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

# 画像・first/last・seedなど、任意のCUIオプションを渡す
video +args: check-idle
    uv run --no-sync python scripts/generate_video.py "$@"

# 人工的にレンダリングした立方体のfirst/lastから動画を生成
demo-geometry: check-idle
    uv run --no-sync python examples/render_geometry.py
    uv run --no-sync python scripts/generate_video.py --prompt "A single solid orange cube slowly rotates 60 degrees around its vertical axis. Rigid straight edges, soft studio lighting, fixed camera, no cuts, quiet room ambience." --first-frame outputs/geometry-demo/first.png --last-frame outputs/geometry-demo/last.png --out outputs/geometry-demo/interpolation.mp4

# GPUを使わないCUI引数・入力形式の検証
test-cli:
    uv run --no-sync python -m unittest discover -s tests -v

# 金属・影・反射のある画像と参考動画をCPUで作成（Blenderが必要）
render-studio:
    blender --background --threads 4 --python examples/render_studio.py
    uv run --no-sync python examples/encode_studio_guide.py

# render-studioで作った銅の立方体をfirst/last指定で動かす
demo-studio-keyframes: check-idle
    uv run --no-sync python scripts/generate_video.py --prompt "Photorealistic 3D product render of a single solid copper cube with subtly rounded machined edges. The rigid cube starts rotating immediately and rotates at a constant slow speed around its vertical axis through 60 degrees from the first image to the last image. Preserve solid shape and consistent dimensions. Physically based copper reflections, soft studio lights, contact shadows and a matte floor. Locked camera, no cuts, no outlines, no deformation. Quiet room ambience, no music or speech." --first-frame outputs/studio-demo/first.png --last-frame outputs/studio-demo/last.png --out outputs/studio-demo/copper-first-last.mp4 --width 512 --height 320

# 銅リングの画像＋別形状の参考動画から生成
demo-studio-reference: check-idle
    uv run --no-sync python scripts/generate_video.py --prompt "Photorealistic 3D product animation. Preserve the copper torus ring shown in <Picture 1>, including its circular hole, rounded tubular shape and polished metallic material. Use only the steady 60 degree vertical-axis rotation from <Video 1>, not its gray cuboid shape. One copper ring rotates smoothly in place, fixed center and size, resting on the studio floor. Fixed camera and realistic highlights, no cuts, no deformation, no extra objects. Quiet studio ambience." --reference-image outputs/studio-demo/target.png --reference-video outputs/studio-demo/motion-guide.mp4 --out outputs/studio-demo/ring-guided.mp4 --width 512 --height 320

# 剛体回転の比較画像をCPUでレンダリングし、生成動画と並べる
review-studio:
    blender --background --threads 4 --python examples/render_studio.py -- --review-only
    uv run --no-sync python examples/review_studio.py

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
