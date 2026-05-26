<template>
  <div class="interview-container">
    <div class="header-actions">
      <button class="back-btn" @click="$emit('cancel-interview')" :disabled="isRecording">
        返回首頁
      </button>
    </div>

    <h2>面試進行中：{{ jobTitle }}</h2>
    
    <div class="video-wrapper">
      <video ref="videoElement" autoplay muted playsinline></video>
      <canvas ref="snapCanvas" style="display:none;"></canvas>
    </div>

    <div class="status-box">
      <p class="question-text">面試官：{{ currentQuestion }}</p>
    </div>

    <div class="controls">
      <button 
        class="record-btn" 
        :class="{ recording: isRecording }" 
        @click="toggleRecording" 
        :disabled="isLoading"
      >
        {{ isRecording ? '結束回答並送出' : '開始回答' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

const props = defineProps({
  jobTitle: String
});

const emit = defineEmits(['end-interview', 'cancel-interview']);

const videoElement = ref(null);
const snapCanvas = ref(null); // 🔥 綁定快門
const currentQuestion = ref('正在準備問題...');
const isLoading = ref(true);
const isRecording = ref(false);

let mediaStream = null;
let mediaRecorder = null;
let audioChunks = [];

// 🔥 新增：表情追蹤變數
const emotionLog = ref([]);
let expressionInterval = null;

// 計算陣列中出現最多次的表情 (眾數)
const getDominantEmotion = (arr) => {
  if (arr.length === 0) return "平靜 (Neutral)";
  return arr.sort((a,b) => arr.filter(v => v===a).length - arr.filter(v => v===b).length).pop();
};

onMounted(async () => {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    if (videoElement.value) {
      videoElement.value.srcObject = mediaStream;
    }
  } catch (error) {
    alert('無法開啟攝影機與麥克風！請允許權限後再試一次。');
    emit('end-interview', null); 
    return;
  }
  await fetchQuestionFromAI();
});

onUnmounted(() => {
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
  }
  clearInterval(expressionInterval); // 確保定時器被關閉
});

const fetchQuestionFromAI = async () => {
  isLoading.value = true;
  try {
    const response = await fetch('http://127.0.0.1:8000/api/generate-question', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_title: props.jobTitle }) 
    });
    const data = await response.json();
    if (data.status === 'success') {
      currentQuestion.value = data.question;
    } else {
      currentQuestion.value = '抱歉，面試官網路連線異常，請重新開始。';
    }
  } catch (error) {
    currentQuestion.value = '連線到後端失敗，請確認 Python 伺服器有啟動。';
  } finally {
    isLoading.value = false;
  }
};

// 🔥 新增：截圖並發送給後端分析表情
const captureAndAnalyzeFace = () => {
  if (!videoElement.value || !snapCanvas.value) return;

  const video = videoElement.value;
  const canvas = snapCanvas.value;
  const context = canvas.getContext('2d');

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  context.drawImage(video, 0, 0, canvas.width, canvas.height);

  canvas.toBlob(async (blob) => {
    const formData = new FormData();
    formData.append('image', blob, 'snapshot.jpg');

    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze-face', {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      if (data.status === 'success') {
        emotionLog.value.push(data.emotion);
      }
    } catch (error) {
      console.error("表情分析連線失敗", error);
    }
  }, 'image/jpeg');
};

const toggleRecording = () => {
  if (!isRecording.value) {
    startRecording();
  } else {
    stopRecordingAndEvaluate();
  }
};

const startRecording = () => {
  audioChunks = [];
  emotionLog.value = []; // 清空上次紀錄
  const audioTrack = mediaStream.getAudioTracks()[0];
  const streamToRecord = new MediaStream([audioTrack]);
  
  mediaRecorder = new MediaRecorder(streamToRecord, { mimeType: 'audio/webm' });

  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) audioChunks.push(event.data);
  };
  
  mediaRecorder.start();
  isRecording.value = true;

  // 🔥 開始錄音時，每 3 秒偷拍一張照片分析表情
  expressionInterval = setInterval(() => {
    captureAndAnalyzeFace();
  }, 3000);
};

const stopRecordingAndEvaluate = () => {
  isRecording.value = false;
  mediaRecorder.stop();
  clearInterval(expressionInterval); // 🔥 結束錄音時，停止偷拍

  mediaRecorder.onstop = async () => {
    const originalQuestion = currentQuestion.value;
    const finalEmotion = getDominantEmotion(emotionLog.value); // 🔥 結算主要表情

    currentQuestion.value = "正在上傳錄音與分析表情 (這可能需要數十秒)...";
    isLoading.value = true;

    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    
    formData.append('my_audio', audioBlob, 'answer.webm');
    formData.append('question', originalQuestion);
    formData.append('emotion', finalEmotion); // 🔥 把算出來的表情裝箱！

    try {
      const response = await fetch('http://127.0.0.1:8000/api/upload-audio', {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      
      if (result.status === 'success') {
        // 🔥 修正：把 emotion 傳給 App.vue
        emit('end-interview', {
          transcript: result.transcript,
          feedback: result.feedback,
          emotion: result.emotion 
        });
      } else {
        alert("評分失敗：" + result.message);
        emit('end-interview', null);
      }
    } catch (error) {
      console.error("連線後端失敗：", error);
      alert("連線到評分伺服器失敗。");
      emit('end-interview', null);
    }
  };
};
</script>

<style scoped>
/* 樣式保持原樣不變 */
.interview-container { text-align: center; max-width: 800px; margin: 0 auto; padding: 20px; }
.video-wrapper { background: #000; border-radius: 12px; overflow: hidden; margin-bottom: 20px; aspect-ratio: 16/9; }
video { width: 100%; height: 100%; object-fit: cover; }
.status-box { background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
.question-text { font-size: 1.2rem; font-weight: bold; color: #2c3e50; }
.record-btn { padding: 15px 30px; font-size: 1.2rem; border-radius: 8px; border: none; cursor: pointer; background-color: #e74c3c; color: white; transition: background-color 0.3s; font-weight: bold;}
.record-btn.recording { background-color: #c0392b; animation: pulse 1.5s infinite; }
.record-btn:disabled { background-color: #bdc3c7; cursor: not-allowed; animation: none; }
.header-actions {display: flex; justify-content: flex-start; margin-bottom: 10px;}
.back-btn {background-color: #95a5a6; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 1rem; font-weight: bold; transition: background-color 0.2s;}
.back-btn:hover:not(:disabled) {background-color: #7f8c8d;}
.back-btn:disabled {opacity: 0.5; cursor: not-allowed;}

@keyframes pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); }
}
</style>