import os
import cv2
import numpy as np
import tensorflow as tf
import keras
from keras.utils import image_dataset_from_directory
from keras import layers
from keras.models import Sequential, load_model

import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report

#定義表情標籤
EMOTIONS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]

# ==========================================
# 1. 新版資料載入與預處理 (適應 Keras 3.0+)
# ==========================================
def load_data(base_dir):
    train_dir = os.path.join(base_dir, 'train')
    test_dir = os.path.join(base_dir, 'test')
    
    #設定隨機種子，確保訓練集與驗證集切分時不會重疊
    seed = 42
    
    print("正在載入訓練集圖片")
    train_ds = image_dataset_from_directory(
        train_dir,
        validation_split=0.2,
        subset="training",
        seed=seed,
        label_mode="categorical",
        color_mode="grayscale",
        batch_size=64,
        image_size=(48, 48),
        shuffle=True
    )
    
    print("正在載入驗證集圖片")
    val_ds = image_dataset_from_directory(
        train_dir,
        validation_split=0.2,
        subset="validation",
        seed=seed,
        label_mode="categorical",
        color_mode="grayscale",
        batch_size=64,
        image_size=(48, 48),
        shuffle=True
    )
    
    print("正在載入測試集圖片")
    test_ds = image_dataset_from_directory(
        test_dir,
        label_mode="categorical",
        color_mode="grayscale",
        batch_size=64,
        image_size=(48, 48),
        shuffle=False
    )
    
    #將圖片像素從 0~255 歸一化到 0~1
    normalization_layer = layers.Rescaling(1./255)
    train_ds = train_ds.map(lambda x, y: (normalization_layer(x), y))
    val_ds = val_ds.map(lambda x, y: (normalization_layer(x), y))
    test_ds = test_ds.map(lambda x, y: (normalization_layer(x), y))
    
    #建立資料增強流水線
    data_augmentation = Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.1),
        layers.RandomTranslation(0.1, 0.1)
    ])
    
    #將資料增強應用在訓練集上
    train_ds = train_ds.map(lambda x, y: (data_augmentation(x, training=True), y))
    
    #快取與預取數據，提升效能
    train_ds = train_ds.prefetch(buffer_size=tf.data.AUTOTUNE)
    val_ds = val_ds.prefetch(buffer_size=tf.data.AUTOTUNE)
    test_ds = test_ds.prefetch(buffer_size=tf.data.AUTOTUNE)
    
    return train_ds, val_ds, test_ds

# ==========================================
# 2. 建立 CNN 模型架構
# ==========================================
def build_model():
    model = Sequential([
        #第一層卷積
        layers.Conv2D(32, (3, 3), activation='relu', padding='same', input_shape=(48, 48, 1)),
        layers.BatchNormalization(),
        layers.Conv2D(32, (3, 3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(pool_size=(2, 2)),
        layers.Dropout(0.25),

        #第二層卷積
        layers.Conv2D(64, (3, 3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.Conv2D(64, (3, 3), activation='relu', padding='same'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(pool_size=(2, 2)),
        layers.Dropout(0.25),

        #全連接層
        layers.Flatten(),
        layers.Dense(128, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.5),
        layers.Dense(7, activation='softmax')
    ])
    
    model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])
    model.summary()
    return model

# ==========================================
# 新增函數 A：繪製訓練歷史曲線 (損失與準確率)
# ==========================================
def plot_history(history):
    acc = history.history['accuracy']
    val_acc = history.history['val_accuracy']
    loss = history.history['loss']
    val_loss = history.history['val_loss']
    epochs_range = range(len(acc))

    plt.figure(figsize=(12, 5))

    #1. 準確率曲線
    plt.subplot(1, 2, 1)
    plt.plot(epochs_range, acc, label='Training Accuracy', color='blue')
    plt.plot(epochs_range, val_acc, label='Validation Accuracy', color='orange')
    plt.legend(loc='lower right')
    plt.title('Training and Validation Accuracy')
    plt.xlabel('Epochs')
    plt.ylabel('Accuracy')

    #2. 損失曲線
    plt.subplot(1, 2, 2)
    plt.plot(epochs_range, loss, label='Training Loss', color='blue')
    plt.plot(epochs_range, val_loss, label='Validation Loss', color='orange')
    plt.legend(loc='upper right')
    plt.title('Training and Validation Loss')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')

    plt.tight_layout()
    plt.savefig('learning_curve.png')
    plt.show()

# ==========================================
# 新增函數 B：計算並繪製混淆矩陣
# ==========================================
def plot_confusion_matrix(model, test_ds):
    print("\n正在擷取測試集真實標籤並進行預測...")
    
    #從 tf.data.Dataset 中取出所有的真實標籤
    y_true = []
    for _, labels in test_ds:
        y_true.extend(np.argmax(labels.numpy(), axis=1))
    y_true = np.array(y_true)
    
    #進行模型預測
    y_pred_probs = model.predict(test_ds)
    y_pred = np.argmax(y_pred_probs, axis=1)
    
    #計算混淆矩陣
    cm = confusion_matrix(y_true, y_pred)
    
    #列印文字版的分類報告 (包含 Precision, Recall, F1-score)
    print("\n--- 分類報告 Classification Report ---")
    print(classification_report(y_true, y_pred, target_names=EMOTIONS))
    
    #繪製熱條圖混淆矩陣
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=EMOTIONS, yticklabels=EMOTIONS)
    plt.title('Confusion Matrix')
    plt.ylabel('True Label (Actual)')
    plt.xlabel('Predicted Label')
    plt.tight_layout()
    plt.savefig('confusion_matrix.png')
    plt.show()

# ==========================================
# 3. 即時相機辨識推論
# ==========================================
def start_realtime_cnn(model_path):
    print("正在載入 CNN 模型...")
    model = load_model(model_path)
    
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cap = cv2.VideoCapture(0)
    print("鏡頭已開啟，按下 'q' 鍵可退出...")
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success: break
            
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
        
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2) #繪出臉部方框 (0,255,0)代表綠色方框 2代表方框線條粗細
            
            #把只有人臉的區塊切出來
            roi_gray = gray[y:y+h, x:x+w]
            roi_gray = cv2.resize(roi_gray, (48, 48))
            roi_gray = roi_gray.astype("float") / 255.0
            roi_gray = np.expand_dims(roi_gray, axis=0)
            roi_gray = np.expand_dims(roi_gray, axis=-1) #確保形狀為 (1, 48, 48, 1)
            
            preds = model.predict(roi_gray, verbose=0)[0] #preds儲存每種表情的預測機率
            label_id = np.argmax(preds) #np.argmax找preds最大索引值
            confidence = preds[label_id] #將最大機率數值取出並存進confidence(信心度)
            
            #把即時預測文字印在畫面上
            text = f"{EMOTIONS[label_id]} ({confidence*100:.1f}%)"
            cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
        #把處理好的畫面秀出
        cv2.imshow('Real-time Emotion CNN', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
            
    cap.release()
    cv2.destroyAllWindows()

# ==========================================
# 主程式執行流程
# ==========================================
if __name__ == "__main__":
    archive_path = "Archive"
    model_name = "cnn_emotion_model.keras"
    
    # 步驟 A: 載入資料
    train_ds, val_ds, test_ds = load_data(archive_path)
    
    # 步驟 B: 建立並訓練模型
    cnn_model = build_model()
    print("開始訓練 CNN 模型...")
    
    history = cnn_model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=20
    )

    print("\n--- 正在使用測試集評估模型最終性能 ---")
    test_loss, test_acc = cnn_model.evaluate(test_ds)
    print(f"測試集準確度 (Test Accuracy): {test_acc*100:.2f}%")
    
    # 步驟 C: 儲存模型
    cnn_model.save(model_name)
    print(f"模型訓練完畢，已儲存為 {model_name}")

    print("\n正在生成訓練曲線...")
    plot_history(history)

    plot_confusion_matrix(cnn_model, test_ds)
    
    # 步驟 D: 啟動即時辨識
    start_realtime_cnn(model_name)
