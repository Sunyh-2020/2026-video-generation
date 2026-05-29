import os
import json
import base64
import gc
from openai import OpenAI
from prompt_kling import update_prompt

# ========= 基础配置 =========
VIDEOS_JSON = "generated_prompts_30.json"
METRIC_JSON = "total_metrics.json"
OUTPUT_JSON = "updated_prompt.json"
STYLE_JSON="doubao_type_result.json"
MODEL_NAME = "doubao-seed-1-6-250615"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
API_KEY = ""  # 强烈建议用环境变量 

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

# ========= 工具函数 =========
def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[-1][1:].lower()
    ext = "jpeg" if ext == "jpg" else ext
    return f"data:image/{ext};base64,{encoded}"

def build_prompt_block(cloth_title, raw_prompt, metric,style):
    """
    拼成你之前单条 demo 里的那种格式
    """
    score_text = (
        f"(VQ, TC, TVA, BD, CD, CTD, AQ) = "
        f"({metric['simplevqa']:.2f}, "
        f"{metric['cliptemp']:.2f}, "
        f"{metric['clipsim']:.2f}, "
        f"{metric['avg_dis']:.2f}, "
        f"{metric['convex_total']:.2f}, "
        f"{metric['catwalk']:.2f}, "
        f"{metric['vbench']:.2f})"
    )

    return f"""
主播售卖的服装名称是{cloth_title},风格分类是{style}

提示词1：
{raw_prompt.strip()}

提示词1得分：
{score_text}
""".strip()

# ========= 主流程 =========
def main():
    with open(VIDEOS_JSON, "r", encoding="utf-8") as f:
        videos = json.load(f)

    with open(METRIC_JSON, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    
    with open(STYLE_JSON, "r", encoding="utf-8") as f:
        styles = json.load(f)

    results = []

    for idx, video in enumerate(videos, 1):
        video_id = video["video_id"]

        print(f"\n[{idx}/{len(videos)}] Processing {video_id}")

        if video_id not in metrics:
            print(f"⚠️ metrics not found, skip")
            continue

        # ---- 构造用户输入 ----
        prompt_block = build_prompt_block(
            cloth_title=video["cloth_title"],
            raw_prompt=video["prompt"],
            metric=metrics[video_id],
            style=styles[video_id.split('_')[0]+'_'+video_id.split('_')[1]]
        )
        print(prompt_block)
        image_url = encode_image(video["image_path"])

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的视频生成提示词优化专家，专注于时尚走秀类视频的提示词优化。"
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": update_prompt
                    },
                    {
                        "type": "text",
                        "text": prompt_block
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    },
                ]
            }
        ]

        # ---- 调用模型（单条）----
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages
        )

        optimized_prompt = response.choices[0].message.content

        results.append({
            "video_id": video_id,
            "optimized_prompt": optimized_prompt,
            "metrics": metrics[video_id],
            "usage": response.usage.to_dict()
        })

        # ---- 关键：主动释放内存 ----
        del image_url, messages, response
        gc.collect()

    # ---- 写入结果 ----
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done. Saved to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()