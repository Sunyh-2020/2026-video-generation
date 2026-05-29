import os
import json
import time
import base64
import hmac
import hashlib
import datetime
import requests

# ================== 基本配置 ==================
ACCESS_KEY = ""
SECRET_KEY = "=="

HOST = "visual.volcengineapi.com"
ENDPOINT = "https://visual.volcengineapi.com"
REGION = "cn-north-1"
SERVICE = "cv"

SUBMIT_ACTION = "CVSync2AsyncSubmitTask"
QUERY_ACTION = "CVSync2AsyncGetResult"
VERSION = "2022-08-31"

REQ_KEY = "jimeng_i2v_first_v30"

PROMPT_JSON_PATH = "generated_prompts_30.json"
OUTPUT_DIR = "jimeng_videos"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ================== V4 签名工具 ==================
def sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def get_signature_key(key, date_stamp, region, service):
    k_date = sign(key.encode("utf-8"), date_stamp)
    k_region = sign(k_date, region)
    k_service = sign(k_region, service)
    k_signing = sign(k_service, "request")
    return k_signing

def signed_post(action, body_dict):
    body = json.dumps(body_dict)
    t = datetime.datetime.utcnow()
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    canonical_uri = "/"
    canonical_querystring = f"Action={action}&Version={VERSION}"
    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    canonical_headers = (
        f"content-type:application/json\n"
        f"host:{HOST}\n"
        f"x-content-sha256:{payload_hash}\n"
        f"x-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-content-sha256;x-date"

    canonical_request = (
        "POST\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    algorithm = "HMAC-SHA256"
    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    signing_key = get_signature_key(SECRET_KEY, date_stamp, REGION, SERVICE)
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization_header = (
        f"{algorithm} "
        f"Credential={ACCESS_KEY}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Date": amz_date,
        "X-Content-Sha256": payload_hash,
        "Authorization": authorization_header,
    }

    url = f"{ENDPOINT}?{canonical_querystring}"
    response = requests.post(url, headers=headers, data=body, timeout=60)
    return response.json()

# ================== 工具函数 ==================
def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def wait_and_get_video(task_id):
    """修改：遇到错误时返回None而不是抛出异常"""
    while True:
        resp = signed_post(
            QUERY_ACTION,
            {
                "req_key": REQ_KEY,
                "task_id": task_id
            }
        )

        if resp.get("code") != 10000:
            print(f"   ❌ 查询任务失败: {resp.get('message', '未知错误')} (code: {resp.get('code')})")
            return None  # 返回None表示失败

        status = resp["data"]["status"]
        print(f"   task {task_id} status: {status}")

        if status == "done":
            return resp["data"].get("video_url")
        elif status in ["failed", "canceled"]:
            print(f"   ❌ 任务状态为: {status}")
            return None

        time.sleep(5)

def download_video(url, save_path):
    """修改：添加下载错误处理"""
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()  # 抛出HTTP错误
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"   ❌ 下载失败: {str(e)}")
        # 如果下载失败，删除不完整的文件
        if os.path.exists(save_path):
            os.remove(save_path)
        return False

# ================== 主流程 ==================
def main():
    try:
        with open(PROMPT_JSON_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {str(e)}")
        return

    for idx, item in enumerate(items, 1):
        video_id = item["video_id"]
        save_path = os.path.join(OUTPUT_DIR, f"{video_id}.mp4")
        
        # 跳过已存在的视频
        if os.path.exists(save_path):
            print(f"\n[{idx}/{len(items)}] 📥 视频已存在，跳过: {video_id}")
            continue
        
        # 检查必要的字段
        required_fields = ["image_path", "prompt", "video_id"]
        missing_fields = [field for field in required_fields if field not in item]
        if missing_fields:
            print(f"\n[{idx}/{len(items)}] ❌ 缺少必要字段 {missing_fields}，跳过: {video_id}")
            continue
        
        image_path = item["image_path"]
        prompt = item["prompt"]

        print(f"\n[{idx}/{len(items)}] 生成视频: {video_id}")

        # 检查图片文件是否存在
        if not os.path.exists(image_path):
            print(f"   ❌ 图片文件不存在: {image_path}")
            continue

        # 图片转base64
        try:
            img_b64 = image_to_base64(image_path)
        except Exception as e:
            print(f"   ❌ 图片转base64失败: {str(e)}")
            continue

        # 提交任务
        try:
            submit_resp = signed_post(
                SUBMIT_ACTION,
                {
                    "req_key": REQ_KEY,
                    "binary_data_base64": [img_b64],
                    "prompt": prompt,
                    "frames": 241
                }
            )
        except Exception as e:
            print(f"   ❌ 提交任务失败: {str(e)}")
            continue

        if submit_resp.get("code") != 10000:
            print("   ❌ 提交失败:", submit_resp.get("message", "未知错误"))
            continue

        task_id = submit_resp["data"]["task_id"]
        print("   task_id:", task_id)

        # 查询任务结果（修改后会返回None表示失败）
        video_url = wait_and_get_video(task_id)
        if not video_url:
            print("   ❌ 未获取到有效视频URL")
            continue

        # 下载视频
        print(f"   📥 开始下载视频: {video_url}")
        if download_video(video_url, save_path):
            print("✅ 已下载:", save_path)
        else:
            print("❌ 下载失败，跳过该视频")

if __name__ == "__main__":
    main()