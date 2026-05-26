import os
import cv2
import numpy as np
import tensorflow as tf
import keras
from keras.utils import image_dataset_from_directory
from keras import layers
from keras.models import Sequential, load_model
from sklearn.utils.class_weight import compute_class_weight

# 如果電腦有低階或內建 GPU，開啟混合精度多少能幫忙加速，若沒有則會自動切回 float32
try:
    tf.keras.mixed_precision.set_global_policy('mixed_float16')
    print("已成功啟用混合精度訓練 (Mixed Precision)")
except Exception as e:
    pass

# 定義表情標籤
EMOTIONS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]

# ==========================================
# 1. 資料載入與預處理 (維持高效的 48x48 灰階)
# ==========================================
def load_data(base_dir):
    train_dir = os.path.join(base_dir, 'train')
    test_dir = os.path.join(base_dir, 'test')
    
    print("正在載入訓練集圖片...")
    train_ds = image_dataset_from_directory(
        train_dir,
        label_mode="categorical",
        color_mode="grayscale",
        batch_size=64,
        image_size=(48, 48),
        shuffle=True
    )
    
    print("正在載入測試集圖片...")
    test_ds = image_dataset_from_directory(
        test_dir,
        label_mode="categorical",
        color_mode="grayscale",
        batch_size=64,
        image_size=(48, 48),
        shuffle=False
    )
    
    # 圖片像素歸一化 0~1
    normalization_layer = layers.Rescaling(1./255)
    train_ds = train_ds.map(lambda x, y: (normalization_layer(x), y))
    test_ds = test_ds.map(lambda x, y: (normalization_layer(x), y))
    
    # 資料增強流水線 (隨機水平翻轉、微幅旋轉平移)
    data_augmentation = Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.1),
        layers.RandomTranslation(0.1, 0.1)
    ])
    
    train_ds = train_ds.map(lambda x, y: (data_augmentation(x, training=True), y))
    
    # 快取與預取數據優化
    train_ds = train_ds.prefetch(buffer_size=tf.data.AUTOTUNE)
    test_ds = test_ds.prefetch(buffer_size=tf.data.AUTOTUNE)
    
    return train_ds, test_ds

# ==========================================
# 2. 計算類別權重 (Class Weights + Max 4.0 裁剪)
# ==========================================
def get_clipped_class_weights(base_dir):
    train_dir = os.path.join(base_dir, 'train')
    y_train = []
    
    for emotion_idx, emotion_name in enumerate(EMOTIONS):
        folder_path = os.path.join(train_dir, emotion_name)
        if os.path.exists(folder_path):
            num_files = len(os.listdir(folder_path))
            y_train.extend([emotion_idx] * num_files)
        
    y_train = np.array(y_train)
    classes = np.unique(y_train)
    
    # 計算平衡權重並裁剪至最大 4.0
    weights = compute_class_weight(class_weight='balanced', classes=classes, y=y_train)
    clipped_weights = np.clip(weights, a_min=None, a_max=4.0)
    
    class_weight_dict = {cls: weight for cls, weight in zip(classes, clipped_weights)}
    print("裁剪後的不平衡類別權重:", class_weight_dict)
    return class_weight_dict

# ==========================================
# 3. 建立優化後的 CNN 模型架喚
# ==========================================
def build_model():
    model = Sequential([
        # 第一層卷積塊
        layers.Conv2D(32, (3, 3), activation='relu', padding='same', input_shape=(48, 48, 1)),
        layers.BatchNormalization(),
        layers.Conv2D(32, (3, 3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(pool_size=(2, 2)),
        layers.Dropout(0.25),

        # 第二層卷積塊
        layers.Conv2D(64, (3, 3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.Conv2D(64, (3, 3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(pool_size=(2, 2)),
        layers.Dropout(0.25),

        # 全連接分類頭
        layers.Flatten(),
        layers.Dense(128, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.5),
        # 指定 dtype='float32' 確保與混合精度相容
        layers.Dense(7, activation='softmax', dtype='float32')
    ])
    
    # 引入 AdamW 優化器（含權重衰減，防過度擬合）與 標籤平滑 = 0.06
    optimizer = keras.optimizers.AdamW(learning_rate=1e-3, weight_decay=1e-4)
    loss_fn = keras.losses.CategoricalCrossentropy(label_smoothing=0.06)
    
    model.compile(optimizer=optimizer, loss=loss_fn, metrics=['accuracy'])
    return model

# ==========================================
# 4. 即時相機辨識推論
# ==========================================
def start_realtime_cnn(model_path):
    print("\n正在載入訓練好的 CNN 模型...")
    model = load_model(model_path)
    
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cap = cv2.VideoCapture(0)
    print("鏡頭已開啟，將臉部對準鏡頭。按下 'q' 鍵可退出...")
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success: break
            
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
        
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            
            roi_gray = gray[y:y+h, x:x+w]
            roi_gray = cv2.resize(roi_gray, (48, 48))
            roi_gray = roi_gray.astype("float") / 255.0
            roi_gray = np.expand_dims(roi_gray, axis=0)
            roi_gray = np.expand_dims(roi_gray, axis=-1)
            
            preds = model.predict(roi_gray, verbose=0)[0]
            label_id = np.argmax(preds)
            confidence = preds[label_id]
            
            text = f"{EMOTIONS[label_id]} ({confidence*100:.1f}%)"
            cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
        cv2.imshow('Real-time Emotion CNN (Optimized)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
            
    cap.release()
    cv2.destroyAllWindows()

# ==========================================
# 主程式執行流程
# ==========================================
if __name__ == "__main__":
    archive_path = "Archive"  
    model_name = "cnn_emotion_model_v2.keras" 
    
    # 步驟 A: 載入資料與計算裁剪後的類別權重
    train_ds, test_ds = load_data(archive_path)
    class_weight_dict = get_clipped_class_weights(archive_path)
    
    # 步驟 B: 建立模型
    cnn_model = build_model()
    
    # 步驟 C: 設定現代化訓練的 Callbacks 控制器
    callbacks_list = [
        # 驗證集準確度 3 輪沒進步就提前結束，防浪費時間，並自動還原最佳權重
        keras.callbacks.EarlyStopping(monitor='val_accuracy', patience=3, restore_best_weights=True, verbose=1),
        # 驗證集損失 2 輪沒改善就降低學習率為 0.3 倍
        keras.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.3, patience=2, verbose=1),
        # 只保存驗證集準確度最高的模型
        keras.callbacks.ModelCheckpoint(filepath=model_name, monitor='val_accuracy', save_best_only=True, verbose=1),
        # 紀錄日誌
        keras.callbacks.CSVLogger('training_log.csv', append=False)
    ]
    
    print("\n🚀 開始高效率 CNN 模型訓練...")
    # 設定上限跑 20 輪，但因為有 EarlyStopping，通常第 10~15 輪收斂後就會提早自動結束
    cnn_model.fit(
        train_ds,
        validation_data=test_ds,
        epochs=20,
        class_weight=class_weight_dict,
        callbacks=callbacks_list
    )
    
    print(f"\n✨ 訓練結束！最優模型已存為 {model_name}")
    
    # 步驟 D: 啟動即時相機推論
    start_realtime_cnn(model_name)
