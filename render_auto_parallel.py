import boto3
import os
import subprocess
import math
import time
from jinja2 import Template

S3_BUCKET = "your-bucket-name"
BLEND_FILE = "scene.blend"
WORK_DIR = "./work"
TEMPLATE_FILE = "docker-compose-template.yml.j2"
COMPOSE_FILE = "docker-compose.yml"

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
        "docker", "run", "--rm",
        "-v", f"{os.path.abspath(WORK_DIR)}:/work",
        "nvidia/cuda:12.1.0-base-ubuntu22.04",
        "bash", "-c",
        "apt-get update && apt-get install -y blender > /dev/null && "
        "blender -b /work/scene.blend --python-expr \"import bpy; "
        "print(f'{bpy.context.scene.frame_start}-{bpy.context.scene.frame_end}')\""
    ]
    result = subprocess.check_output(cmd, text=True)
    line = [l for l in result.splitlines() if "-" in l][-1]
    start, end = map(int, line.strip().split("-"))
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
        services.append({"name": f"frame{i+1}", "start": s, "end": e})
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

# 🔹 5. 結果をS3へアップロード
def upload_results():
    print("⬆️ Uploading rendered frames to S3...")
    s3 = boto3.client("s3")
    for f in os.listdir(WORK_DIR):
        if f.startswith("output_") and f.endswith(".png"):
            s3.upload_file(f"{WORK_DIR}/{f}", S3_BUCKET, f"results/{f}")
            print(f"✅ Uploaded {f}")

# 🔹 6. 後処理
def cleanup_and_shutdown():
    print("🧹 Cleaning up containers...")
    subprocess.run(["docker-compose", "down"])
    print("💤 Shutting down instance...")
    os.system("sudo shutdown -h now")

if __name__ == "__main__":
    download_blend()
    start, end = get_frame_range()
    generate_compose(start, end, segments=3)
    run_compose()
    upload_results()
    cleanup_and_shutdown()
