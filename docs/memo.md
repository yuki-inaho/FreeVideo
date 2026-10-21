# ローカル実行メモ

Python 3.12 / uv。`.venv` はコマンド・ランチャー用、公式インストーラーが
uvで作る `envs/unified` はCUDA・ComfyUI・モデル実行用。

```sh
cd FreeVideo
just                 # コマンド一覧
just start           # UIを起動
just status
just stop
just resources       # 他の作業によるGPU/RAM使用量を確認
just e2e             # サンプル文章から2秒のMP4を生成
just e2e examples/prompt.txt outputs/custom.mp4 5
just generate "A fox walks through a forest, with soft birdsong."
just generate "A fox walks through a forest." outputs/fox.mp4 5
just test            # 公式quick検証（複数動画を生成）
```

`just e2e` はテキストのエンコード、動画サンプリング、デコード、MP4保存まで実行。
出力は既定で `outputs/e2e.mp4`。初回はカーネルのコンパイルで時間がかかる。
プロンプトは `examples/prompt.txt` を編集するか、別のUTF-8ファイルを渡す。

## CUIで生成する

`just generate` と `just e2e` はブラウザーやComfyUIサーバーを起動せず、
インストール済みのモデルを直接実行する。ComfyUIのエンコーダーライブラリは利用する。
UIが起動している場合は `just stop` してGPUを空けてから実行する。
Pythonスクリプトから解像度・seedなどを指定することもできる。

```sh
uv run --no-sync python scripts/generate_video.py \
  --prompt "A fox walks through a forest, with soft birdsong." \
  --out outputs/fox.mp4 --seconds 2 --width 768 --height 448 --seed 42
uv run --no-sync python scripts/generate_video.py --help
```

スクリプトを直接呼ぶ場合は `just check-idle` でGPU/RAMの空きを先に確認する。
初回は `just sync` と `just setup` が必要。モデル取得後はネットワーク上の生成APIを
使わずローカルで処理する。終了コードは生成プロセスの結果を引き継ぐ。

生成前にGPU使用量1 GiB未満・使用率5%未満・空きRAM 80 GiB以上を確認し、
満たさなければ停止する。他エージェントとの排他制御ではないので、開始後に
別ジョブが動き出さないようタイミングを合わせる。
GPUの閾値には、待機中のComfyUIが使うCUDAコンテキスト分を含む。
VRAM 24 GiB・RAM 64 GiBはプランナーの予算で、OSによるハード制限ではない。

```sh
just sync            # .venvの再構築（uv.lockを使用）
just setup-plan      # インストール計画を確認
just doctor          # 依存関係の診断
just setup           # 公式ソースからセットアップ／再開
```

最後のコマンドは公式セットアップの再開用。モデル・CUDA環境の取得を含む。
セットアップの詳細ログは `setup-runs/` に保存される。
モデルや実行環境はこのチェックアウト内に保存される。
`setup-runs/` や `machine.json` などの実行時ファイルには環境情報が含まれるため、
Git管理対象外。共有するメモ・justfileには個人情報や絶対パスを記載しない。
ローカル認証情報の `agent/`、診断用の `logs/` と `kernel-capabilities.json` も
Git管理対象外にしている。

環境構築・モデル取得・小規模GPU検査・UIのHTTP応答まで確認済み。
動画生成の実走は未実施。他のGPU作業が空いたタイミングで `just e2e` を実行する。
UI起動後にも自動プリコンパイルがGPUを使うことがあるため、`just start` も
他のGPU作業が空いたタイミングで実行する。初回の起動確認後は停止済み。
