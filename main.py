# main.py
import sys
# ==========================================
# 0. 終端機編碼防護罩
# ==========================================
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import uvicorn
import os
import json

# 核心魔法：引入我們的雙引擎！
from whisper_service import transcribe_audio
from expression_model import analyze_face  # 新增：匯入視覺部門

# ==========================================
# 1. 讀取外部 JSON 提示詞
# ==========================================
with open("prompts.json", "r", encoding="utf-8") as file:
    PROMPTS = json.load(file)

# ==========================================
# 2. 設定 NVIDIA API 客戶端
# ==========================================
NVIDIA_API_KEY = "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"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)

class JobRequest(BaseModel):
    job_title: str
    question_type: str

# ==========================================
# 4. API 端點 (一)：生成面試題目 
# ==========================================
@app.post("/api/generate-question")
async def generate_question(req: JobRequest):
    print(f"\n[INFO] 準備生成【{req.job_title}】的面試題目，類型：【{req.question_type}】...")
    template = PROMPTS["system_prompts"]["opening_question"]
    system_prompt = template.format(job_title=req.job_title, question_type=req.question_type)
    system_prompt += "【規則】如果該職位是亂碼或無意義字眼，請嚴厲回覆：『這似乎不是一個有效的職業，請重新輸入。』"

    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.7,
            presence_penalty=0.6,
            max_tokens=100
        )
        question_text = completion.choices[0].message.content
        return {"status": "success", "question": question_text}
    except Exception as e:
        return {"status": "error", "message": "面試官目前不在座位上，請稍後再試。"}


# ==========================================
# 5. 新增 API 端點 (二)：處理臉部截圖
# ==========================================
@app.post("/api/analyze-face")
async def api_analyze_face(image: UploadFile = File(...)):
    try:
        image_bytes = await image.read()
        emotion = analyze_face(image_bytes)
        return {"status": "success", "emotion": emotion}
    except Exception as e:
        print(f"[ERROR] 表情分析失敗: {str(e)}")
        return {"status": "error", "message": "影像處理失敗"}


# ==========================================
# 6. API 端點 (三)：處理錄音與評分
# ==========================================
@app.post("/api/upload-audio")
async def upload_audio(my_audio: UploadFile = File(...), question: str = Form(...), emotion: str = Form("未偵測")):
    print(f"\n[INFO] 收到包裹！題目: {question} | 偵測表情: {emotion}")
    
    file_location = f"uploads/{my_audio.filename}"
    with open(file_location, "wb") as f:
        f.write(await my_audio.read())

    try:
        transcript = transcribe_audio(file_location)
    except Exception as e:
        return {"status": "error", "message": "語音辨識失敗"}

    template = PROMPTS["system_prompts"]["evaluate_answer"]
    system_prompt = template.format(question=question, transcript=transcript, emotion=emotion)
    system_prompt += "\n【最高指令】請務必只以合法的 JSON 格式回傳，絕對不能包含 'score' 欄位。完美的格式範例如下：\n{\"feedback\": \"你的綜合評語\"}\n除了上述 JSON 結構之外，不要輸出任何其他廢話、標記或 markdown 符號。"

    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.1-70b-instruct",
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.3,
            max_tokens=800
        )
        
        raw_result = completion.choices[0].message.content
        ai_evaluation = json.loads(raw_result)
        
        # 修正：把 emotion 加進回傳的包裹裡！
        return {
            "status": "success",
            "message": "評分完成！",
            "transcript": transcript,
            "feedback": ai_evaluation.get("feedback"),
            "emotion": emotion  
        }
        
    except Exception as e:
        return {"status": "error", "message": "評分伺服器異常。"}

if __name__ == "__main__":
    print("[START] Python FastAPI Server is running...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
