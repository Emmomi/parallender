import boto3
import os, shutil
import subprocess
import math
import time
from jinja2 import Template
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

S3_BUCKET = os.environ.get("S3_BUCKET")
BLEND_FILE = os.environ.get("BLEND_FILE")
WORK_DIR = os.environ.get("WORK_DIR")
TEMPLATE_FILE = os.environ.get("TEMPLATE_FILE")
COMPOSE_FILE = os.environ.get("COMPOSE_FILE")
BLENDER_VERSION = os.environ.get("BLENDER_VERSION")


# 🔹 1. S3 から .blend を取得
def download_blend():
    os.makedirs(WORK_DIR, exist_ok=True)
    s3 = boto3.client("s3")
    print("🔽 Downloading .blend file from S3...")
    s3.download_file(S3_BUCKET, BLEND_FILE, f"{WORK_DIR}/{BLEND_FILE}")


# 🔹 2. Blender CLIでフレーム数を取得
def get_frame_range():
    print("📊 Detecting frame range via Blender CLI...")
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.path.abspath(WORK_DIR)}:/work",
        "nvidia/cuda:12.1.0-base-ubuntu22.04",
        "bash",
        "-c",
        "apt-get update && apt-get install -y wget xz-utils libgl1 libxrender1 libxi6 libxxf86vm1 libxkbcommon0 libglib2.0-0 libx11-6 libsm6 libice6 > /dev/null "
        f"&& wget https://download.blender.org/release/Blender{BLENDER_VERSION[:-2]}/blender-{BLENDER_VERSION}-linux-x64.tar.xz > /dev/null "
        f"&& tar -xJf blender-{BLENDER_VERSION}-linux-x64.tar.xz -C /work "
        f"&& cp -rp /work/blender-{BLENDER_VERSION}-linux-x64 /opt/blender "
        "&& ln -s /opt/blender/blender /usr/local/bin/blender "
        f"&& rm blender-{BLENDER_VERSION}-linux-x64.tar.xz "
        "&& apt-get clean && rm -rf /var/lib/apt/lists/* "
        '&& blender -b /work/test_scene.blend --python-expr "import bpy; '
        "print(f'{bpy.context.scene.frame_start}→{bpy.context.scene.frame_end}')\"",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, encoding="utf-8")
    line = [l for l in result.stdout.split("\n") if "→" in l][-1]
    start, end = map(int, line.strip().split("→"))
    print(f"🧮 Frame range detected: {start} → {end}")
    return start, end


# 🔹 3. docker-compose.yml 自動生成
def generate_compose(start, end, segments=3):
    print("🛠 Generating docker-compose.yml dynamically...")
    total_frames = end - start + 1
    frames_per_job = math.ceil(total_frames / segments)

    services = []
    for i in range(segments):
        s = start + i * frames_per_job
        e = min(s + frames_per_job - 1, end)
        services.append(
            {
                "name": f"frame{i+1}",
                "version": BLENDER_VERSION,
                "file": BLEND_FILE,
                "start": s,
                "end": e,
            }
        )
        if e >= end:
            break

    with open(TEMPLATE_FILE) as f:
        template = Template(f.read())
    output = template.render(services=services)

    with open(COMPOSE_FILE, "w") as f:
        f.write(output)

    print(f"✅ Generated {COMPOSE_FILE} with {len(services)} parallel jobs.")
    return len(services)


# 🔹 4. Docker Compose 実行
def run_compose():
    print("🎨 Starting parallel rendering...")
    subprocess.run(["docker-compose", "up", "--build", "-d"], check=True)
    subprocess.run(["docker-compose", "logs", "-f"])


# 🔹 5. Docker Compose 実行
def create_video_from_frames():
    print("🎞️ Combining frames into MP4...")

    # ffmpegコマンド: 画像シーケンスから動画を生成
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{os.path.abspath(WORK_DIR)}:/work",
        "nvidia/cuda:12.1.0-base-ubuntu22.04",
        "bash",
        "-c",
        "apt-get update && apt-get install -y ffmpeg > /dev/null && "
        "ffmpeg -framerate 24 -pattern_type glob -i '/work/output_*.png' "
        "-c:v libx264 -pix_fmt yuv420p /work/output.mp4",
    ]

    subprocess.run(cmd, check=True)
    print("✅ MP4 video created: work/output.mp4")


# 🔹 6. 結果をS3へアップロード
def upload_results():
    print("⬆️ Uploading rendered frames and video to S3...")
    s3 = boto3.client("s3")
    for f in os.listdir(WORK_DIR):
        if f.startswith("output") and (f.endswith(".png") or f.endswith(".mp4")):
            s3.upload_file(f"{WORK_DIR}/{f}", S3_BUCKET, f"results/{f}")
            print(f"✅ Uploaded {f}")


# 🔹 7. 後処理
def cleanup_and_shutdown():
    print("🧹 Cleaning up containers...")
    subprocess.run(["docker-compose", "down"])
    for item in os.listdir(WORK_DIR):
        path = os.path.join(WORK_DIR, item)
        if item.endswith(".blend"):
            continue
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"Deleted directory: {path}")
        elif os.path.isfile(path):
            os.remove(path)
            print(f"Deleted file: {path}")
    print("💤 Shutting down instance...")
    os.system("sudo shutdown -h now")


if __name__ == "__main__":
    download_blend()
    start, end = get_frame_range()
    generate_compose(start, end, segments=3)
    run_compose()
    create_video_from_frames()
    upload_results()
    cleanup_and_shutdown()
