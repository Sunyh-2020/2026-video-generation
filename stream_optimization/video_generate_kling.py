import os
import json
import time
import base64
import requests
import jwt


# ================== 基础配置 ==================
AK = ""
SK = ""

JSON_PATH = "generated_prompts_30.json"
OUTPUT_DIR = "kling_videos"

MODEL_NAME = "kling-v1-6"
DURATION = 10
ASPECT_RATIO = "9:16"

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ================== 工具函数 ==================
def encode_jwt_token(ak, sk, expire_seconds=1800):
    now = int(time.time())
    payload = {
        "iss": ak,
        "exp": now + expire_seconds,
        "nbf": now - 5
    }
    token = jwt.encode(payload, sk, algorithm="HS256")
    return token if isinstance(token, str) else token.decode()


def image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ================== 可灵 API ==================
def create_image2video_task(api_key, image_b64, prompt):
    url = "https://api-beijing.klingai.com/v1/videos/image2video"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model_name": MODEL_NAME,
        "mode": "std",
        "duration": DURATION,
        "image": image_b64,
        "prompt": prompt,
        "cfg_scale": 0.8,
        "aspect_ratio": ASPECT_RATIO
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(data.get("message"))

    return data["data"]["task_id"]


def query_task(api_key, task_id):
    url = f"https://api-beijing.klingai.com/v1/videos/image2video/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        return None, "failed"

    status = data["data"]["task_status"]
    if status == "succeed":
        video_url = data["data"]["task_result"]["videos"][0]["url"]
        return video_url, "succeed"
    if status == "failed":
        return None, "failed"

    return None, "running"


def download_video(video_url, save_path):
    with requests.get(video_url, stream=True) as r:
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


# ================== 主流程 ==================
def main():

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    for idx, item in enumerate(items, 1):
        api_key = encode_jwt_token(AK, SK)
        print("✅ JWT Token 生成成功")
        video_id = item["video_id"]
        save_path = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
        if os.path.exists(save_path):
            continue
        image_path = item["image_path"]
        prompt = item["prompt"]

        print(f"\n🎬 [{idx}/{len(items)}] 处理视频 {video_id}")

        if not os.path.exists(image_path):
            print("❌ 图片不存在，跳过")
            continue

        image_b64 = image_to_base64(image_path)

        try:
            task_id = create_image2video_task(api_key, image_b64, prompt)
            print(f"📤 任务提交成功：{task_id}")
        except Exception as e:
            print("❌ 提交失败：", e)
            continue

        # 轮询
        for _ in range(200):
            video_url, status = query_task(api_key, task_id)

            if status == "succeed":
                download_video(video_url, save_path)
                print(f"✅ 下载完成：{save_path}")
                break

            if status == "failed":
                print("❌ 生成失败")
                break

            time.sleep(20)
        else:
            print("⏳ 超时未完成，跳过")

        time.sleep(3)  # 防止限流


if __name__ == "__main__":
    main()
