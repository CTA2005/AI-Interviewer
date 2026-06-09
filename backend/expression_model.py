# expression_model.py
import numpy as np
import tensorflow as tf
from PIL import Image
import io

print("[INFO] 正在初始化視覺部門 (載入 cnn_emotion_model.keras 模型)...")
# 🔍 修改點 1：換成你最新上傳的 CNN 模型檔名
model = tf.keras.models.load_model("cnn_emotion_model.keras")
print("[SUCCESS] 全新 CNN 臉部表情辨識模型載入完成！")

#注意：請確認這 7 個情緒的排列順序，和你「訓練新模型時 (train_generator.class_indices)」的標籤順序完全一致！
EMOTIONS = ["生氣 (Angry)", "厭惡 (Disgust)", "恐懼 (Fear)", "開心 (Happy)", "難過 (Sad)", "驚訝 (Surprise)", "平靜 (Neutral)"]

def analyze_face(image_bytes: bytes) -> str:
    """
    接收前端圖片，轉換為 48x48 灰階 float32 格式後進行表情預測
    """
    try:
        # 1. 讀取圖片，強制轉換為灰階 ('L')
        img = Image.open(io.BytesIO(image_bytes)).convert('L')
        
        # 2. 調整大小為 48x48
        img = img.resize((48, 48))
        
        # 3. 轉為陣列、正規化，並精準契合你模型要求的 float32 型態
        img_array = np.array(img, dtype=np.float32) / 255.0
        
        # 4. 擴充維度 [Batch, Height, Width, Channels] 變成 (1, 48, 48, 1)
        img_array = np.expand_dims(img_array, axis=-1)
        img_array = np.expand_dims(img_array, axis=0)
        
        # 5. 進行預測
        predictions = model.predict(img_array, verbose=0)
        
        # 6. 找出機率最高的情緒
        max_index = np.argmax(predictions[0])
        result = EMOTIONS[max_index]
        
        return result
        
    except Exception as e:
        raise Exception(f"影像前處理或辨識失敗: {str(e)}")
