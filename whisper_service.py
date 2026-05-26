# whisper_service.py
from faster_whisper import WhisperModel

print("[INFO] 正在初始化聽覺部門 (預先載入 Whisper STT 模型)...")
# 這行只會在模組被引入時跑一次，後續都會秒速辨識！
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
print("[SUCCESS] Whisper 模型載入完成！")

def transcribe_audio(file_path: str) -> str:
    """
    接收音檔路徑，交給 Whisper 聽寫，並回傳完整的純文字逐字稿。
    """
    try:
        segments, info = whisper_model.transcribe(file_path, beam_size=5)
        transcript = ""
        for segment in segments:
            transcript += segment.text + " "
        return transcript.strip()
    except Exception as e:
        # 如果辨識失敗，將錯誤拋出給 main.py 處理
        raise Exception(f"Whisper 辨識失敗: {str(e)}")