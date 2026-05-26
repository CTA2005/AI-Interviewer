import os
import time
from faster_whisper import WhisperModel

# 紀錄開始時間
start_time = time.time()

# 取得目前這個 py 檔案所在的絕對路徑
current_dir = os.path.dirname(os.path.abspath(__file__))

# 🛠️ 【檔名檢查點】請確認你 voice_test 資料夾底下的檔案，到底是 test_1.m4a 還是 first_test.m4a？
target_file = "test_1.m4a" 

# 自動組合出絕對路徑，保證 Python 100% 找得到檔案
audio_path = os.path.join(current_dir, "voice_test", target_file)

print(f"1. 🚀 正在檢查檔案是否存在...")
if not os.path.exists(audio_path):
    print(f"❌ 錯誤：找不到音檔！")
    print(f"   系統預期檔案應該在：{audio_path}")
    print(f"   請檢查 voice_test 資料夾內的檔名是否真的叫作 {target_file}")
else:
    print(f"✅ 成功找到音檔：{audio_path}")
    print("2. 🤖 正在載入 AI 模型並開始辨識 (這一步需要 5~10 秒)...")
    
    # 執行純語音轉文字
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, beam_size=5)
    
    print(f"3. 偵測到語言: '{info.language}'\n")
    print("=================== 📝 逐字稿結果 ===================")
    for segment in segments:
        print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")
    print("====================================================")

end_time = time.time()
print(f"\n總花費時間: {end_time - start_time:.2f} 秒。")
