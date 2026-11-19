import sys
import re
# ==========================================
# 0. 終端機編碼防護罩
# ==========================================
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


# ==========================================
# 終端機輸出同步存一份到 backend/server.log，出問題時方便事後查看
# ==========================================
class _Tee:
    def __init__(self, stream, log_file):
        self.stream, self.log_file = stream, log_file

    def write(self, text):
        self.stream.write(text)
        try:
            self.log_file.write(text)
            self.log_file.flush()
        except Exception:
            pass  # 記錄檔寫不進去不影響主程式
        return len(text)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


if __name__ == "__main__":  # 只有用 python main.py 啟動時才寫記錄檔（測試工具匯入時不寫）
    import datetime as _dt
    import os as _os
    _log = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "server.log"), "a", encoding="utf-8")
    _log.write(f"\n===== 伺服器啟動 {_dt.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    sys.stdout = _Tee(sys.stdout, _log)
    sys.stderr = _Tee(sys.stderr, _log)

from fastapi import FastAPI, UploadFile, File, Form, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import storage
from pydantic import BaseModel
from openai import OpenAI
from behavior_analyzer import analyze_video_behavior
import uvicorn
import os
import json
import random
import threading
import traceback
import uuid
from typing import List, Optional
from dotenv import load_dotenv

# ==========================================
# 1. 讀取外部 JSON 提示詞
# ==========================================
with open("prompts.json", "r", encoding="utf-8") as file:
    PROMPTS = json.load(file)

# 職務清單、各職務的主題、難度定義（放在 roles.json，方便組員與老師審查、修改）
with open("roles.json", "r", encoding="utf-8") as file:
    ROLE_DATA = json.load(file)
ROLES = ROLE_DATA["roles"]
DIFFICULTY_GUIDE = ROLE_DATA["difficulty"]
QUESTION_TYPES = ROLE_DATA["question_types"]  # 各難度的題型，出題時隨機挑選

# ==========================================
# 2. 設定 NVIDIA API 客戶端
# ==========================================
# 從 backend/api.env 讀取金鑰 (api.env 內容格式：NVIDIA_API_KEY=你的金鑰)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, "api.env"))
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
if not NVIDIA_API_KEY:
    raise RuntimeError("找不到 NVIDIA_API_KEY，請確認 backend/api.env 內有 NVIDIA_API_KEY=你的金鑰")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)
MODEL_NAME = "nvidia/nemotron-3.5-bolt-e4b"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """沒有預料到的錯誤：在終端機印出完整錯誤，並把原因回傳給前端顯示，方便除錯。"""
    print(f"\n❌ [未預期錯誤] {request.url.path}：{exc!r}", flush=True)
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    # 這個錯誤處理在 CORS 中介層之外執行，要自己補上 CORS 標頭，
    # 否則瀏覽器會擋掉這個回應，前端只會看到「Failed to fetch」
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"伺服器錯誤：{type(exc).__name__}: {exc}"},
        headers={"Access-Control-Allow-Origin": "*"}
    )


os.makedirs("uploads", exist_ok=True)

# 資料庫（帳號與練習紀錄）：啟動時建立資料表，並清掉之前沒有存成紀錄的錄影
storage.init_db()
storage.cleanup_orphan_recordings()


def _token_from_header(authorization):
    """從 Authorization: Bearer <token> 標頭取出 token。"""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return None


def optional_user(authorization):
    """有登入就回傳使用者，訪客回傳 None（模擬面試允許訪客使用）。"""
    return storage.user_from_token(_token_from_header(authorization))


def require_user(authorization):
    """一定要登入的 API 用：沒登入或登入已過期就回傳 401。"""
    user = optional_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="請先登入，或登入已過期。")
    return user

# Whisper 在 CPU 上一次只分析一段錄音，避免多段同時轉文字把電腦拖垮
WHISPER_LOCK = threading.Lock()

# 有效作答的最低門檻（暫定值，可依實測調整）
MIN_ANSWER_CHARS = 10   # 至少 10 個字
MIN_SPEECH_SEC = 3.0    # 至少說話 3 秒
NO_SPEECH_NOTE = "這次沒有偵測到足夠的回答內容，因此無法評分。請確認麥克風正常，並在回答時清楚說出你的想法。"
# 自我介紹沒有標準答案，沒作答時提供固定的介紹結構範本
NO_SPEECH_INTRO_FEEDBACK = (
    "【自我介紹回饋】\n"
    "✘ " + NO_SPEECH_NOTE + "\n\n"
    "建議的介紹結構：\n"
    "1. 基本背景：我是（學校）（科系）（年級）的學生。\n"
    "2. 相關經驗：我曾經做過（專題、實習或作品名稱），負責（你的工作內容），成果是（具體成果或數據）。\n"
    "3. 應徵動機：我想應徵這個職務，是因為（你的動機），希望能運用（你的技能）在（職務相關的工作）上。"
)


# ==========================================
# 3. 共用小工具
# ==========================================
def looks_complete(text):
    """簡單檢查題目有沒有真的『提問』：結尾附近要有問句或要求作答的字眼。"""
    tail = text.strip()[-30:]
    return any(k in tail for k in ["？", "?", "請", "如何", "怎麼", "你會", "說明", "描述", "解釋"])


def safe_difficulty(difficulty):
    return difficulty if difficulty in DIFFICULTY_GUIDE else "中級"  # 不認得的值一律當中級


# ==========================================
# 職務名稱檢查（職務改為手動輸入，要防亂輸入、純英文與提示詞注入）
# ==========================================
JOB_ALLOWED = re.compile(r"[一-鿿A-Za-z0-9 ／/、\-]+")  # 只允許中英文、數字、空白和少數符號
CUSTOM_ROLES = {}   # 自訂職務的主題清單（記在記憶體，伺服器重啟後會重新產生）
JOB_CHECK_CACHE = {}  # 同一個輸入不重複問 AI


def job_format_error(job_title):
    """第一層：格式檢查。通過回傳空字串，不通過回傳錯誤訊息（前端也有同樣的檢查）。"""
    t = (job_title or "").strip()
    if not 2 <= len(t) <= 20:
        return "職務名稱請輸入 2～20 個字。"
    if not JOB_ALLOWED.fullmatch(t):
        return "職務名稱不能包含特殊符號。"
    if not re.search(r"[一-鿿]", t):
        return "請用中文輸入職務名稱，例如「後端工程師」。"
    return ""


def safe_job(job_title):
    """放進提示詞前使用：格式不合法就換成通用名稱，避免提示詞注入。"""
    return job_title.strip() if job_title and not job_format_error(job_title) else "資訊相關職務"


def parse_json_object(text):
    """從 AI 的回覆中取出第一個 JSON 物件；取不出來回傳 None。"""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def generate_job_topics(job_title):
    """為自訂職務產生 5～7 個面試主題；失敗回傳空清單。"""
    prompt = PROMPTS["system_prompts"]["job_topics"].format(job_title=job_title)
    try:
        text = call_llm(prompt, temperature=0.3, max_tokens=400)
    except Exception as e:
        print(f"[警告] 自訂職務主題產生失敗：{e}", flush=True)
        return []
    topics = []
    for line in text.splitlines():
        t = re.sub(r"^\s*(\d+[\.、．)]|[-•*])\s*", "", line).strip()
        if 2 <= len(t) <= 30:
            topics.append(t)
    return topics[:7]


def ask_ai_about_job(job_input):
    """第三層：請 AI 判斷是不是合理的資訊相關職務，並找出最接近的現有職務。
    回傳 (AI 判斷結果 dict, 錯誤訊息)。同一個輸入的結果會暫存，不重複問 AI。"""
    if job_input in JOB_CHECK_CACHE:
        return JOB_CHECK_CACHE[job_input], ""
    prompt = PROMPTS["system_prompts"]["check_job"].format(
        job_input=job_input,
        role_list="、".join(ROLES)
    )
    try:
        result = parse_json_object(call_llm(prompt, temperature=0, max_tokens=300))
    except Exception as e:
        print(f"[警告] 職務檢查失敗：{e}", flush=True)
        return None, "目前無法確認職務名稱，請稍後再試，或從建議清單中選擇。"
    if not result or not result.get("valid"):
        print(f"[INFO] 職務不通過：{job_input!r}，AI 判斷原因：{(result or {}).get('reason')}", flush=True)
        return None, f"「{job_input}」不是一個職務名稱，請重新輸入。"
    JOB_CHECK_CACHE[job_input] = result
    return result, ""


def ensure_custom_role(name):
    """確保自訂職務有主題清單（沒有就請 AI 產生）。回傳錯誤訊息，成功為空字串。"""
    if name in ROLES or name in CUSTOM_ROLES:
        return ""
    topics = generate_job_topics(name)
    if len(topics) < 3:
        return "目前無法為這個職務準備題目，請換個說法，或從建議清單中選擇。"
    CUSTOM_ROLES[name] = topics
    print(f"[INFO] 新增自訂職務【{name}】，主題：{topics}", flush=True)
    return ""


def resolve_job(job_input, keep_original=False):
    """把使用者輸入的職務轉成系統使用的職務名稱，並準備好主題清單。
    keep_original=True：使用者選擇保留自己輸入的名稱，不對應到現有職務。
    回傳 (職務名稱, 錯誤訊息)；成功時錯誤訊息為空字串。"""
    job_input = (job_input or "").strip()

    # 第二層：後端格式檢查（前端的檢查可以被繞過）
    err = job_format_error(job_input)
    if err:
        return "", err

    # 完全符合現有職務或已確認過的自訂職務，就不用再問 AI
    if job_input in ROLES or job_input in CUSTOM_ROLES:
        return job_input, ""

    result, err = ask_ai_about_job(job_input)
    if err:
        return "", err

    if keep_original:
        name = job_input                                  # 保留使用者輸入的名稱
    elif result.get("matched_role") in ROLES:
        name = result["matched_role"]                     # 對應到現有職務，沿用它的主題清單
    else:
        name = (result.get("normalized") or "").strip()   # 新職務，用 AI 整理過的標準名稱
        if job_format_error(name):                        # AI 給的名稱也要通過格式檢查
            name = job_input

    err = ensure_custom_role(name)
    return ("", err) if err else (name, "")


def get_topics(job_title):
    return ROLES.get(job_title) or CUSTOM_ROLES.get(job_title) or []


def call_llm(prompt, temperature=0.3, max_tokens=800):
    """呼叫 NVIDIA API，回傳清理過的純文字。"""
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    text = (completion.choices[0].message.content or "").replace("```json", "").replace("```", "").strip()
    # 保險：如果 AI 回了 {"feedback": "..."} 的格式，就把外殼拆掉
    m = re.search(r'^\s*\{\s*"feedback"\s*:\s*"(.*)"\s*\}\s*$', text, re.S)
    if m:
        text = m.group(1).replace("\\n", "\n")
    return text


def generate_key_points(job_title, question, difficulty):
    """針對題目產生 2～3 個評分用的參考要點；失敗時回傳空字串。"""
    prompt = PROMPTS["system_prompts"]["answer_key"].format(
        job_title=safe_job(job_title),
        question=question,
        difficulty=difficulty,
        difficulty_desc=DIFFICULTY_GUIDE[difficulty]
    )
    try:
        text = call_llm(prompt, temperature=0.2, max_tokens=400)  # 要點求穩定，溫度調低
        # 只保留編號開頭的行，去掉模型偶爾多加的標題或說明
        lines = [l.strip() for l in text.splitlines() if re.match(r"^\s*\d+[\.、．]", l)]
        return "\n".join(lines) if lines else text
    except Exception as e:
        print(f"[警告] 參考要點生成失敗：{e}", flush=True)
        return ""


def build_no_speech_feedback(question, difficulty, key_points):
    """沒有作答時的回饋：不評分，但提供這題的關鍵要點與參考回答，讓學生知道可以怎麼答。"""
    parts = ["【技術與內容】", "✘ " + NO_SPEECH_NOTE, ""]
    if key_points.strip():
        parts += ["這題的關鍵要點：", key_points.strip(), ""]

    prompt = PROMPTS["system_prompts"]["reference_answer"].format(
        question=question,
        difficulty=difficulty,
        difficulty_desc=DIFFICULTY_GUIDE[difficulty],
        key_points=key_points.strip() or "（無，請自行判斷這題在此難度下的重點）"
    )
    try:
        reference = call_llm(prompt, temperature=0.3, max_tokens=400)
        parts += ["參考回答：", reference]
    except Exception as e:
        print(f"[警告] 參考回答生成失敗：{e}", flush=True)
    return "\n".join(parts).strip()


def save_and_analyze(upload: UploadFile, user=None):
    """存下錄影檔（每次用不同檔名，避免同時上傳互相覆蓋），再做語音轉文字與流暢度分析。
    已登入：保留錄影，之後可以存進練習紀錄；訪客：分析完就刪除錄影，不保存。"""
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in (".webm", ".mp4", ".wav"):
        ext = ".webm"
    recording_id = f"{uuid.uuid4().hex}{ext}"
    file_location = storage.recording_path(recording_id)
    with open(file_location, "wb") as f:
        f.write(upload.file.read())
    try:
        with WHISPER_LOCK:
            transcript, filler_count, wpm, pause_stats = analyze_video_behavior(file_location)
    except Exception:
        os.remove(file_location)
        raise

    if user:
        storage.register_recording(recording_id, user["id"])
    else:
        os.remove(file_location)  # 訪客的錄影不保存
        recording_id = None

    # 字數太少或說話時間太短，視為沒有有效作答（例如沒說話、只錄到旁人聲音或雜音）
    # 用 bool() 轉成 Python 的布林值：Whisper 回傳的時間是 numpy 數字，比較結果會是 numpy.bool_，回傳 JSON 時會出錯
    has_speech = bool(len(transcript) >= MIN_ANSWER_CHARS and pause_stats["span_sec"] >= MIN_SPEECH_SEC)
    if not has_speech:
        print(f"[INFO] 沒有偵測到有效作答（{len(transcript)} 字，說話 {pause_stats['span_sec']} 秒）", flush=True)
    return {
        "transcript": transcript,
        "filler_count": filler_count if has_speech else 0,
        "wpm": wpm if has_speech else 0,  # 沒有有效作答時，語速沒有意義
        "pause_stats": pause_stats,
        "has_speech": has_speech,
        "recording_id": recording_id,  # 存練習紀錄時用來對應這段錄影
    }


# ==========================================
# 3.5 API 端點 (零)：確認使用者輸入的職務
# ==========================================
class CheckJobRequest(BaseModel):
    job_title: str
    keep_original: bool = False  # 使用者選擇保留自己輸入的名稱


@app.post("/api/check-job")
def check_job(req: CheckJobRequest):
    print(f"\n[INFO] 檢查職務輸入：{req.job_title[:30]!r}（保留原名：{req.keep_original}）", flush=True)
    original = req.job_title.strip()
    job_title, err = resolve_job(original, req.keep_original)
    if err:
        return {"status": "error", "message": err}
    if job_title != original:
        # 名稱被對應或修正成別的，先讓使用者確認，不要靜默替換
        return {"status": "confirm", "original": original, "suggested": job_title}
    return {"status": "success", "job_title": job_title}


# ==========================================
# 4. API 端點 (一)：生成面試題目
#    以下端點都用一般 def（不是 async def）：FastAPI 會把它們放到背景執行緒，
#    這樣 Whisper 在分析上一題時，下一題仍然可以同時出題。
# ==========================================
class JobRequest(BaseModel):
    job_title: str
    difficulty: str = "中級"    # 沒有帶這個欄位時，預設為中級
    used_focus: List[str] = []  # 這場面試已經出過的主題，避免重複
    used_types: List[str] = []  # 這場面試已經出過的題型，避免題目都長得一樣
    keep_original: bool = False # 使用者選擇保留自己輸入的職務名稱（伺服器重啟後也不會被重新對應）


@app.post("/api/generate-question")
def generate_question(req: JobRequest):
    print(f"\n[INFO] 準備生成【{req.job_title}】的面試題目，難度：【{req.difficulty}】...")

    # 職務必須通過檢查（前端已經檢查過，後端仍要再檢查一次；伺服器重啟後自訂職務也會在這裡重新準備）
    job_title, err = resolve_job(req.job_title, req.keep_original)
    if err:
        return {"status": "error", "message": err}
    difficulty = safe_difficulty(req.difficulty)

    # 從還沒出過的主題中隨機挑一個；全部出過了才允許重複
    all_topics = get_topics(job_title)
    topics = [t for t in all_topics if t not in req.used_focus] or all_topics
    focus = random.choice(topics)
    # 題型也一樣：從這場還沒出過的題型中隨機挑一個，全部出過了再重新輪
    all_types = QUESTION_TYPES[difficulty]
    types = [t for t in all_types if t not in req.used_types] or all_types
    question_type = random.choice(types)
    print(f"[INFO] 本題主題：{focus}｜題型：{question_type[:question_type.index('：')]}", flush=True)

    system_prompt = PROMPTS["system_prompts"]["opening_question"].format(
        job_title=job_title,
        difficulty=difficulty,
        difficulty_desc=DIFFICULTY_GUIDE[difficulty],
        focus=focus,
        question_type=question_type
    )

    try:
        question_text = ""
        for attempt in range(2):  # 題目不完整時，最多重試一次
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": system_prompt}],
                temperature=0.7,
                max_tokens=600
            )
            choice = completion.choices[0]
            # 去掉模型偶爾加上的 Markdown 符號（例如 `malloc`、**粗體**）
            question_text = re.sub(r"[`*#]", "", choice.message.content or "").strip()
            print(f"[INFO] 題目生成結束原因：{choice.finish_reason}（第 {attempt + 1} 次）", flush=True)
            # 正常結束，而且結尾真的有提問，才算完整題目
            if choice.finish_reason == "stop" and looks_complete(question_text):
                break
        # 出題後，再請 AI 為這題準備評分用的參考要點（評分時拿來比對）
        key_points = generate_key_points(job_title, question_text, difficulty)
        print(f"[INFO] 參考要點：\n{key_points}", flush=True)
        return {"status": "success", "question": question_text, "focus": focus,
                "question_type": question_type, "key_points": key_points}
    except Exception as e:
        print(f"\n[致命錯誤] 呼叫 NVIDIA API 失敗，原因：{e}")
        traceback.print_exc()
        return {"status": "error", "message": "面試官目前不在座位上，請稍後再試。"}


# ==========================================
# 5. API 端點 (二)：分析自我介紹
# ==========================================
@app.post("/api/analyze-intro")
def analyze_intro(my_audio: UploadFile = File(...), job_title: str = Form(""),
                  authorization: Optional[str] = Header(None)):
    print(f"\n[INFO] 收到自我介紹錄音，職務：{job_title}")
    try:
        result = save_and_analyze(my_audio, optional_user(authorization))
    except Exception as e:
        print(f"❌ 語音分析失敗: {e}", flush=True)
        traceback.print_exc()
        return {"status": "error", "message": "語音分析失敗"}

    if not result["has_speech"]:
        return {"status": "success", **result, "feedback": NO_SPEECH_INTRO_FEEDBACK}

    prompt = PROMPTS["system_prompts"]["evaluate_intro"].format(
        job_title=safe_job(job_title),
        transcript=result["transcript"]
    )
    try:
        feedback = call_llm(prompt, temperature=0.3, max_tokens=700)
    except Exception as e:
        print(f"❌ NVIDIA API 錯誤: {e}", flush=True)
        traceback.print_exc()
        feedback = "（自我介紹回饋產生失敗，請稍後再試）"
    return {"status": "success", **result, "feedback": feedback}


# ==========================================
# 6. API 端點 (三)：分析單題回答並評分
# ==========================================
@app.post("/api/upload-audio")
def upload_audio(
    my_audio: UploadFile = File(...),
    question: str = Form(...),
    difficulty: str = Form("中級"),
    job_title: str = Form(""),
    key_points: str = Form(""),
    authorization: Optional[str] = Header(None)
):
    difficulty = safe_difficulty(difficulty)
    print(f"\n[INFO] 收到回答錄音！題目: {question}，難度: {difficulty}")

    # 1. 語音轉文字與流暢度分析
    try:
        result = save_and_analyze(my_audio, optional_user(authorization))
    except Exception as e:
        print(f"❌ 語音分析失敗: {e}", flush=True)
        traceback.print_exc()
        return {"status": "error", "message": "行為分析失敗"}

    # 2. 出題時沒拿到參考要點（例如當時生成失敗），就在這裡補產生一次
    if not key_points.strip():
        key_points = generate_key_points(job_title, question, difficulty)

    # 沒有有效作答就不評分（避免 AI 對著空白或雜音硬給回饋），改成提供參考答案
    if not result["has_speech"]:
        feedback = build_no_speech_feedback(question, difficulty, key_points)
        return {"status": "success", **result, "feedback": feedback,
                "question": question, "key_points": key_points}

    if not key_points.strip():
        key_points = "（沒有參考要點，請自行判斷這題在此難度下應包含的 2 到 3 個關鍵要點）"

    # 3. 組合提示詞並評分（輸出格式寫在 prompts.json 的 evaluate_answer 裡）
    prompt = PROMPTS["system_prompts"]["evaluate_answer"].format(
        question=question,
        transcript=result["transcript"],
        difficulty=difficulty,
        difficulty_desc=DIFFICULTY_GUIDE[difficulty],
        key_points=key_points
    )
    try:
        print("\n[系統] 準備將資料發送給 NVIDIA 進行分析評分...", flush=True)
        feedback_text = call_llm(prompt, temperature=0.3, max_tokens=800)
        print("[系統] ✅ 成功收到 NVIDIA 的評分結果！", flush=True)
    except Exception as e:
        print(f"❌ NVIDIA API 錯誤: {e}", flush=True)
        traceback.print_exc()
        feedback_text = "（評分產生失敗，請稍後再試）"

    return {
        "status": "success",
        **result,
        "feedback": feedback_text,
        "question": question,
        "key_points": key_points
    }


# ==========================================
# 7. API 端點 (四)：整場面試的摘要與建議
# ==========================================
class AnswerItem(BaseModel):
    question: str
    transcript: str = ""
    feedback: str = ""
    has_speech: bool = True


def feedback_for_summary(feedback):
    """摘要只需要「面試者答了什麼、漏了什麼」。
    把回饋裡的「關鍵要點」「參考回答」拿掉，避免摘要把標準答案誤當成面試者說過的話。"""
    if "你的回答：" in feedback:
        feedback = feedback.split("你的回答：", 1)[1]
    return feedback.split("參考回答：", 1)[0].strip()


class SummaryRequest(BaseModel):
    job_title: str
    difficulty: str = "中級"
    intro_transcript: str = ""
    intro_feedback: str = ""
    answers: List[AnswerItem] = []


@app.post("/api/summary")
def summarize_interview(req: SummaryRequest):
    print(f"\n[INFO] 產生整場面試摘要：{req.job_title}，共 {len(req.answers)} 題")
    difficulty = safe_difficulty(req.difficulty)

    parts = []
    for i, a in enumerate(req.answers, start=1):
        if not a.has_speech or not a.transcript.strip():
            parts.append(f"第 {i} 題：{a.question}\n面試者回答：（面試者沒有作答）")
            continue
        parts.append(
            f"第 {i} 題：{a.question}\n"
            f"面試者回答：{a.transcript}\n"
            f"該題的評語：{feedback_for_summary(a.feedback) or '（沒有評語）'}"
        )

    has_intro = bool(req.intro_transcript.strip())
    prompt = PROMPTS["system_prompts"]["summary"].format(
        job_title=safe_job(req.job_title),
        difficulty=difficulty,
        intro_transcript=req.intro_transcript if has_intro else "（面試者沒有做自我介紹）",
        intro_feedback=req.intro_feedback if has_intro else "（無）",
        answers="\n\n".join(parts) or "（沒有題目回答）"
    )
    try:
        summary = call_llm(prompt, temperature=0.3, max_tokens=900)
    except Exception as e:
        print(f"❌ NVIDIA API 錯誤: {e}", flush=True)
        traceback.print_exc()
        return {"status": "error", "message": "摘要產生失敗。"}
    return {"status": "success", "summary": summary}


# ==========================================
# 8. 帳號：註冊、登入、登出
# ==========================================
class AccountRequest(BaseModel):
    username: str
    password: str


@app.post("/api/register")
def register(req: AccountRequest):
    username = req.username.strip()
    err = storage.validate_credentials(username, req.password)
    if err:
        return {"status": "error", "message": err}
    user_id, err = storage.create_user(username, req.password)
    if err:
        return {"status": "error", "message": err}
    print(f"[INFO] 新使用者註冊：{username}", flush=True)
    return {"status": "success", "token": storage.create_session(user_id), "username": username}


@app.post("/api/login")
def login(req: AccountRequest):
    username = req.username.strip()
    user_id = storage.check_login(username, req.password)
    if not user_id:
        return {"status": "error", "message": "帳號或密碼錯誤。"}  # 不透露是帳號還是密碼錯，避免被用來猜帳號
    return {"status": "success", "token": storage.create_session(user_id), "username": username}


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(None)):
    token = _token_from_header(authorization)
    if token:
        storage.delete_session(token)
    return {"status": "success"}


@app.get("/api/me")
def me(authorization: Optional[str] = Header(None)):
    user = require_user(authorization)
    return {"status": "success", "username": user["username"]}


# ==========================================
# 9. 練習紀錄：儲存、列表、查看、刪除、播放錄影（都需要登入，而且只能存取自己的紀錄）
# ==========================================
class SegmentItem(BaseModel):
    question: str = ""
    ok: bool = False
    error: str = ""
    has_speech: bool = False
    transcript: str = ""
    feedback: str = ""
    wpm: int = 0
    filler_count: int = 0
    pause_stats: dict = {}
    recording_id: Optional[str] = None


class SaveInterviewRequest(BaseModel):
    job_title: str
    difficulty: str = "中級"
    summary: str = ""
    segments: List[SegmentItem]  # [自我介紹, 第 1 題, 第 2 題, ...]


@app.post("/api/interviews")
def save_interview(req: SaveInterviewRequest, authorization: Optional[str] = Header(None)):
    user = require_user(authorization)
    if not req.segments:
        return {"status": "error", "message": "沒有可儲存的內容。"}
    interview_id = storage.save_interview(
        user["id"], safe_job(req.job_title), safe_difficulty(req.difficulty), req.summary,
        [s.model_dump() for s in req.segments])
    print(f"[INFO] {user['username']} 儲存練習紀錄 #{interview_id}", flush=True)
    storage.cleanup_orphan_recordings()
    return {"status": "success", "id": interview_id}


@app.get("/api/interviews")
def list_interviews(authorization: Optional[str] = Header(None)):
    user = require_user(authorization)
    return {"status": "success", "interviews": storage.list_interviews(user["id"])}


@app.get("/api/interviews/{interview_id}")
def get_interview(interview_id: int, authorization: Optional[str] = Header(None)):
    user = require_user(authorization)
    data = storage.get_interview(interview_id, user["id"])
    if not data:
        raise HTTPException(status_code=404, detail="找不到這筆紀錄。")
    return {"status": "success", "interview": data}


@app.delete("/api/interviews/{interview_id}")
def delete_interview(interview_id: int, authorization: Optional[str] = Header(None)):
    user = require_user(authorization)
    if not storage.delete_interview(interview_id, user["id"]):
        raise HTTPException(status_code=404, detail="找不到這筆紀錄。")
    print(f"[INFO] {user['username']} 刪除練習紀錄 #{interview_id}", flush=True)
    return {"status": "success"}


@app.get("/api/recordings/{recording_id}")
def get_recording(recording_id: str, authorization: Optional[str] = Header(None)):
    user = require_user(authorization)
    # 檔名只允許 uuid + 副檔名，避免用 ../ 讀到其他檔案
    if not re.fullmatch(r"[0-9a-f]{32}\.(webm|mp4|wav)", recording_id) \
            or not storage.recording_owner_ok(recording_id, user["id"]):
        raise HTTPException(status_code=404, detail="找不到這段錄影。")
    path = storage.recording_path(recording_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="錄影檔已不存在。")
    media = {"webm": "video/webm", "mp4": "video/mp4", "wav": "audio/wav"}[recording_id.rsplit(".", 1)[1]]
    return FileResponse(path, media_type=media)


if __name__ == "__main__":
    print("[START] Python FastAPI Server is running...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
