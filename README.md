# parallender

Blenderの並列レンダリングシステム

1. `.blender`からフレーム数を取得する
2. フレーム数を何等分かに分ける
3. コンテナを複数作り並列でレンダリング(画像で)
4. レンダリングした画像を動画にする

をやってくれる 便利

# 使い方

1. .envの設定
    ```.env
    S3_BUCKET = "S3バケットの名前"
    BLEND_FILE = ".blendのファイル名"
    WORK_DIR = "./work"
    TEMPLATE_FILE = "docker-compose-template.yml.j2"
    COMPOSE_FILE = "docker-compose.yml"
    BLENDER_VERSION = "Blenderのversion"
    ```
2. `work`ディレクトリの作成
    ```
    parallender/
    ├── render_auto_parallel.py
    ├── docker-compose-template.yml.j2
    └── work/

    ```
3. `.blender`の作成
4. `render_auto_parallel.py`の実行

# localで試したい場合

## `render_auto_parallel.py`
1. `download_blend`を以下に変更
    ```python
    def download_blend():
        print("📁 Local mode: using ./work/scene.blend directly.")
        local_path = f"{WORK_DIR}/{BLEND_FILE}"
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"{local_path} not found")
    ```
2. `upload_results`を以下に変更
    ```python
    def upload_results():
    print("⬆️ Uploading rendered frames and video to S3...")
    s3 = boto3.client("s3")
    for f in os.listdir(WORK_DIR):
        if f.startswith("output") and (f.endswith(".png") or f.endswith(".mp4")):
            # s3.upload_file(f"{WORK_DIR}/{f}", S3_BUCKET, f"results/{f}")
            print(f"✅ Uploaded {f}")
    ```
3. `if __name__ == "__main__":`の前に以下を記述
    ```python
    S3_BUCKET = None
    ```