# behavior_analyzer.py
import re
import time
from faster_whisper import WhisperModel

# ==========================================
# 全域載入模型：Whisper 壞了，伺服器一開機就會報出真正的底層錯誤
# ==========================================
print("\n🚨 [系統啟動中] 準備載入 Whisper 語音模型...")
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
print("✅ [成功] Whisper 模型載入完畢！\n")

# 停頓判定：兩個字之間空白超過這個秒數，就列入停頓計算（暫定值，可依驗證結果調整）
PAUSE_THRESHOLD = 0.5


def build_pause_stats(pause_gaps, first_word_start, last_word_end):
    """把每次停頓的長度整理成統計值。
    比率的分母是「說話區間」(第一個字開始 ~ 最後一個字結束)，
    不含開頭與結尾的靜音，所以跟回答長短無關。"""
    # Whisper 的時間戳可能是 numpy 數字，一律轉成 Python float，回傳 JSON 時才不會出錯
    span = 0.0
    if first_word_start is not None and last_word_end is not None:
        span = float(max(last_word_end - first_word_start, 0.0))
    total = float(sum(pause_gaps))
    count = len(pause_gaps)
    return {
        "threshold_sec": PAUSE_THRESHOLD,
        "count": count,                                                  # 停頓次數
        "total_sec": round(total, 1),                                    # 停頓總時間
        "span_sec": round(span, 1),                                      # 說話區間長度
        "ratio": round(total / span * 100, 1) if span > 0 else 0.0,      # 停頓時間占比 (%)
        "per_min": round(count / (span / 60.0), 1) if span > 0 else 0.0, # 每分鐘停頓次數
        "avg_sec": round(total / count, 1) if count else 0.0,            # 平均每次停頓長度
    }


# Whisper 在沒有人說話時常見的幻聽句子（來自影片字幕的訓練資料）
HALLUCINATION_PHRASES = [
    "訂閱", "點讚", "按讚", "轉發", "打賞", "明鏡", "字幕", "謝謝觀看", "感謝觀看",
    "謝謝收看", "感謝收看", "下期再見", "我們下次見", "請不吝",
]


def is_hallucination(segment):
    """判斷一段辨識結果是不是幻聽：
    1. Whisper 自己判斷「沒有語音」的機率高，而且對辨識結果沒把握
    2. 內容是常見的影片結尾或字幕用語"""
    if segment.no_speech_prob > 0.6 and segment.avg_logprob < -1.0:
        return True
    text = segment.text.strip()
    return any(p in text for p in HALLUCINATION_PHRASES) and len(text) <= 30


def analyze_video_behavior(video_path):
    """分析一段錄音（或錄影）的口語流暢度。
    回傳：(逐字稿, 贅字數, 語速(字/分), 停頓統計 dict)"""
    print(f"\n[分析中] 1. 開始處理檔案: {video_path}", flush=True)
    t_start = time.perf_counter()  # 計時開始

    print("[分析中] 2. 啟動聽覺模型 (Whisper)，開始抽取聲音轉文字 (這可能需要幾十秒)...", flush=True)

    ai_text_combined = ""
    pause_gaps = []          # 每一次停頓的長度（秒）
    first_word_start = None  # 第一個字開始的時間
    last_word_end = None     # 上一個字結束的時間
    speech_duration_min = 0.0  # 語速用的時間：Whisper 成功後改用音訊實際長度

    try:
        segments, info = whisper_model.transcribe(
            video_path,
            language="zh",
            initial_prompt="這是一段繁體中文的台灣語音。",
            vad_filter=True,
            # 調小 VAD 的靜音門檻，避免把較短的停頓直接吃掉
            vad_parameters=dict(min_silence_duration_ms=500),
            # 開啟逐字時間戳，用「字與字之間」的空白判斷停頓
            word_timestamps=True,
            # 不拿上一句當提示，避免在靜音時一直重複產生同一句幻聽文字
            condition_on_previous_text=False,
        )

        if getattr(info, "duration", None):
            speech_duration_min = info.duration / 60.0

        for segment in segments:
            # 過濾 Whisper 在靜音或雜音時「幻聽」出來的文字
            if is_hallucination(segment):
                print(f"[略過疑似幻聽] {segment.text} (無語音機率 {segment.no_speech_prob:.2f})", flush=True)
                continue
            ai_text_combined += segment.text
            print(f"聽到: {segment.text} (時間: {segment.start:.1f}s - {segment.end:.1f}s)", flush=True)

            # 不管停頓落在 segment 之間還是 segment 裡面，都能抓到
            for word in (segment.words or []):
                if first_word_start is None:
                    first_word_start = word.start
                if last_word_end is not None:
                    gap = word.start - last_word_end
                    if gap > PAUSE_THRESHOLD:
                        pause_gaps.append(gap)
                        print(f"[偵測到停頓] 空白了 {gap:.1f} 秒！", flush=True)
                last_word_end = word.end

    except Exception as e:
        print(f"Whisper 發生嚴重錯誤：{e}", flush=True)
        ai_text_combined = "聲音分析失敗"
        speech_duration_min = 0.0
        pause_gaps, first_word_start, last_word_end = [], None, None

    filler_words = ["那個", "然後", "就是", "呃", "嗯", "啊"]
    filler_count = sum(ai_text_combined.count(fw) for fw in filler_words)
    clean_text = re.sub(r'[^\w\u4e00-\u9fff]+', '', ai_text_combined)

    total_words = len(clean_text)
    wpm = int(total_words / speech_duration_min) if speech_duration_min > 0 else 0

    # 停頓統計
    pause_stats = build_pause_stats(pause_gaps, first_word_start, last_word_end)

    print(f"[分析中] 3. 完成！語速:{wpm}字/分 | 停頓占比:{pause_stats['ratio']}% ({pause_stats['count']}次) | 贅字:{filler_count}個", flush=True)
    print(f"[計時] 語音分析（Whisper） {time.perf_counter() - t_start:.1f} 秒", flush=True)

    return clean_text, filler_count, wpm, pause_stats
