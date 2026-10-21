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

### 画像を引数で渡す

開始・終了画像を指定して、その間の動きをテキストで指示する。
JSONやプロンプトファイルを自分で作る必要はない。

```sh
just video --prompt "The orange cube rotates slowly, fixed camera." \
  --first-frame inputs/first.png --last-frame inputs/last.png \
  --out outputs/first-last.mp4 --seconds 2
```

開始画像のみ・終了画像のみも指定でき、タスクは自動判定される。
一般的な画像ガイダンスは、参照画像の一覧または引数の繰り返しで渡す。
これはfirst/lastの時刻指定とは別の入力形式。

```sh
just video --prompt "A scene guided by these reference images." \
  --reference-image inputs/shape.png inputs/material.png \
  --reference-image "inputs/lighting reference.png" --out outputs/guided.mp4
```

参照画像は実装上、合計32枚まで。これは受理上限であり、32枚での生成を
実測した保証ではない。枚数・画素数に応じてメモリーと処理時間が増える。
first/lastと参照画像リストは同じリクエストには混在できない。
全パスは呼び出し元のカレントディレクトリ基準で、空白を含むパスは引用符で囲む。
ワイルドカードはシェルが展開するため、`--reference-image inputs/ref-*.png` も使える。

標準入力やインラインJSONを使う場合：

```sh
printf '%s\n' 'A slowly rotating cube.' | just video --prompt-stdin \
  --first-frame inputs/first.png --last-frame inputs/last.png
just video --prompt "A rotating cube." \
  --media-json '{"version":1,"first":"inputs/first.png","last":"inputs/last.png"}'
```

既存の `--media inputs/media.json` も利用できる。この場合だけ画像パスは
JSONファイルの場所を基準にする。`--media-json` と画像引数はカレント基準。
`--media` / `--media-json` と画像引数は併用しない。
画像引数から必要な内部入力ファイルを一時生成し、終了時に削除する。

### 別の形状の参考動画を使う

外観を示す画像と、動きを示す動画を同じ参照リストに渡せる。
タグは種類ごとに番号が付き、画像は `<Picture 1>`、動画は `<Video 1>`。

```sh
just video --prompt 'Preserve the copper ring in <Picture 1>. Use only the steady rotation from <Video 1>, not its cuboid shape. Locked camera, realistic studio rendering.' \
  --reference-image outputs/studio-demo/target.png \
  --reference-video outputs/studio-demo/motion-guide.mp4 \
  --out outputs/studio-demo/ring-guided.mp4 --width 512 --height 320
```

`--reference-video` は一覧と繰り返し指定に対応する。画像＋動画の合計上限は32。
動画の音声は既定では参照せず、必要なときだけ `--reference-video-sound` を付ける。
動画は24fpsへ正規化され、生成する長さと15秒の短い方まで使われる。
短すぎる動画は使えないため、少なくとも1秒程度の素材を用意する。
first/lastとの混在は不可。これは生成モデルへの参考入力であり、
形状や動きの完全な分離・厳密なモーション転写を保証するものではない。

入力のCPUレンダリング（Blenderが必要）：

```sh
just render-studio
just demo-studio-keyframes  # 金属の立方体をfirst/last指定で生成
just demo-studio-reference  # リング画像＋直方体の参考動画で生成
```

CyclesをCPU・4スレッドに固定し、金属の材質、面光源、影と反射を持つシーンを作る。
`outputs/studio-demo/guide-frames/` に参考動画用の56枚を出力する。
続いてPyAVで24fpsの無音参考動画 `motion-guide.mp4` にまとめる。

### 3Dレンダリング風の生成物レビュー

銅の立方体のfirst/last生成と、銅リング画像＋灰色直方体の参考動画での生成を
どちらも実走し、512×320・56フレーム・約2.33秒のMP4を確認した。
`just review-studio` で比較用の剛体回転をCPUで描き、抜き出しフレームと並べられる。

- `copper-first-last.mp4`：輪郭線のない金属の材質、ハイライト、接地影を維持。
  開始・終了画像との平均絶対画素差はそれぞれ約2.09・2.08（0〜255）。
  等角速度のレンダリングと比べ、確認した中間フレームの姿勢も近い。
  ただし、面の陰影や輪郭には描き直しによる差があり、厳密な剛体再現ではない。
- `ring-guided.mp4`：画像と動画が参照として受理され、リングの穴と銅の質感を
  保った回転動画を生成できた。参考動画の直方体への置換や物体の増殖は、
  抜き出したフレームでは見られない。前半の姿勢変化は小さく、後半で大きくなる。
- 参考動画を除いた比較はしていない。回転はテキストでも指示しているため、
  参考動画だけの効果、正確な角速度の転写ができたとは結論しない。
- 以前の平坦な絵のデモとは材質だけでなく解像度・形状・視点・プロンプトも違う。
  立体感のある見た目は確認できたが「この質感なら生成が容易になる」という
  因果的な改善比較は行っていない。

比較画像は `copper-first-last-review.png`、`ring-guided-review.png`、
数値は `review.json`。いずれも `outputs/studio-demo/` 内でGit管理対象外。
音声は聴感評価していない。

### 生成時間・VRAM・実行GPU

実行GPUは全件 **NVIDIA GeForce RTX 5090**。
実ログの環境はPyTorch `2.13.0+cu130`、CUDA `13.0`、ドライバー `595.99.02`。
共通設定はseed `2026090901`、int8演算、SageAttention 2、8ステップ＋3ステップの仕上げ。
出力は全件56フレーム・24fps・約2.33秒。各行は異なる入力の実測1回で、平均値ではない。

| 生成物 | 解像度 | 全体時間 | エンコーダー処理 | 動画処理 | エンコーダーのPyTorch予約ピーク | 動画処理中のデバイスVRAMピーク |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 平坦な立方体・first/last (`interpolation`) | 768×448 | 58.28秒 | 10.20秒 | 42.18秒 | 15.12 GiB | 7.30 GiB |
| 金属の立方体・first/last (`copper-first-last`) | 512×320 | 43.27秒 | 7.37秒 | 29.51秒 | 14.98 GiB | 6.61 GiB |
| 銅リング画像＋直方体の参考動画 (`ring-guided`) | 512×320 | 43.10秒 | 10.02秒 | 27.18秒 | 15.04 GiB | 6.97 GiB |

全体時間は `.request.json` の `request_seconds` で、エンコード・モデル読み込み・
サンプリング・デコード・保存・処理間の制御を含む。入力のCPUレンダリング、
モデル取得とセットアップ、シェル起動からの時間は含まない。
エンコーダー処理と動画処理はそれぞれ `.encoding.json` / `.engine.json` の
`work_seconds`。全体には別の制御時間もあるため、2列の合計とは一致しない。

VRAMの2列は異なる計測なので合算しない。
エンコーダー側は `.encoding.json` の `torch_peak_reserved_bytes` で、
PyTorch以外のCUDA使用量を含まない。動画処理側は `.engine.gpu.json` の
`gpu_peak_bytes` で、約50ms間隔で観測したデバイス全体の使用量。
開始時の使用量を差し引いておらず、観測間隔より短いピークは捉えられない。
動画処理側の観測窓はエンコーダー期間を含まないため、**全工程にわたる
デバイスVRAMピークは未計測**。6〜7 GiBで全工程が動く、という意味ではない。
GiBは `bytes / 2^30`。

動画処理中の他プロセスGPU使用率の観測ピークは全件0%だったが、
エンコーダー期間は同じデバイス監視を行っていない。
conditioningと常駐エンコーダー・動画モデルのキャッシュは全件miss。
コンパイルキャッシュとOSキャッシュの温まり具合は未統制で、
解像度・入力・プロンプトも異なるため、行間の速度差を改善率として比較しない。

機械可読の値・元ログの相対パス・出力MP4のSHA-256は
[`demo_measurements.json`](demo_measurements.json) に保存した。
実ログと生成物はGit管理対象外のまま、公開ファイルにはGPU UUID・個人情報・
絶対パスを含めない。

### 人工的な3Dレンダリング画像のデモ

```sh
just demo-geometry
```

CPUで立方体を2方向からレンダリングし、テキスト＋first/lastで動画を生成する。
出力は `outputs/geometry-demo/` の `first.png`、`last.png`、`interpolation.mp4`。
レンダリングだけなら `uv run --no-sync python examples/render_geometry.py`。
生成された入力や動画はGit管理対象外。
first/lastを使った生成を実走し、768×448・56フレーム・約2.33秒のMP4を確認済み。
2秒指定はモデルのフレーム数制約に合わせて切り上げられる。
`just test-cli` で引数の受け渡し・32枚の上限・形式の併用制約・一時ファイル削除を
GPUを使わず検証できる。参照画像を複数使った生成の実走は未実施。

### デモ生成物の自己レビュー

`outputs/geometry-demo/review-comparison.png` の上段が生成動画から抜き出した
0・14・28・42・55フレーム、下段が同じ時刻に等角速度で回した剛体レンダリング。
下段の角度は比較用の目標値で、生成動画から推定した角度ではない。

- 開始・終了画像への追従は良好。RGBの平均絶対画素差は開始2.26、終了2.30
  （各チャンネル0〜255）。ただし圧縮差や描き直しも含む数値で、品質スコアではない。
- 抜き出したフレームでは単一の立方体・背景・影がおおむね維持され、
  目立つ物体の増殖やシーン切り替えは見られない。
- 等角速度の回転にはなっていない。14フレーム目は開始姿勢に近く、
  中盤以降に回転が進む。中間の輪郭や面の見え方も剛体レンダリングと一致しない。
  「両端画像をつないだ生成動画」としては成立するが、正確な3D回転の再現とは区別する。
- 2秒指定に対して実出力は56フレーム・約2.33秒。音声ストリームも含む。
  今回は音の内容を聴感評価していない。

以後も入力・中間・終端を比較し、見た目の成功と未達を分けて記録する。
回転の均一さを改善する場合は、一定速度・開始直後から動く指示を追加して
同じ入力・seed・解像度で比較する。幾何学的に正確な中間姿勢が必要なら、
モデルへの指示だけに頼らず3Dレンダラーで各フレームを生成する。

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
first/last付き動画生成の実走も確認済み。他のGPU作業が空いたタイミングで実行する。
UI起動後にも自動プリコンパイルがGPUを使うことがあるため、`just start` も
他のGPU作業が空いたタイミングで実行する。初回の起動確認後は停止済み。
