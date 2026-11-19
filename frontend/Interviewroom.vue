<template>
  <div class="interview-container">
    <div class="header-actions">
      <!-- 點擊返回首頁會觸發 cancel-interview 事件 -->
      <button class="back-btn" @click="$emit('cancel-interview')" :disabled="isRecording">
        返回首頁
      </button>
    </div>

    <h2>面試進行中：{{ jobTitle }}（{{ difficulty }}）</h2>
    <p class="progress">{{ progressText }}</p>

    <div class="video-wrapper">
      <video ref="videoElement" autoplay muted playsinline></video>
    </div>

    <div class="status-box">
      <p class="question-text">{{ isLoading ? statusText : '面試官：' + currentPrompt }}</p>
      <p v-if="!isLoading && step === 0" class="hint">
        建議約 1 分鐘，可以包含：學校科系、相關技能或專題經驗、為什麼想應徵這個職務。
      </p>
      <p v-if="phase === 'finishing'" class="hint">
        已完成 {{ doneCount }} / {{ count + 1 }} 段回答的分析
      </p>
    </div>

    <div class="controls" v-if="phase !== 'finishing'">
      <button
        class="record-btn"
        :class="{ recording: isRecording }"
        @click="toggleRecording"
        :disabled="isLoading"
      >
        {{ buttonText }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { auth, apiFetch, apiJson } from '../api.js';


const props = defineProps({
  jobTitle: String,
  difficulty: { type: String, default: '中級' },
  count: { type: Number, default: 3 },  // 技術題的題數
  keepOriginal: { type: Boolean, default: false }  // 使用者選擇保留自己輸入的職務名稱
});

const emit = defineEmits(['end-interview', 'cancel-interview', 'restart']);

const videoElement = ref(null);
const step = ref(0);              // 0 = 自我介紹，1 ~ count = 第幾題
const phase = ref('intro');       // 'intro' | 'question' | 'finishing'
const currentPrompt = ref('請先簡單做一段自我介紹。');
const statusText = ref('');
const isLoading = ref(true);
const isRecording = ref(false);
const keyPoints = ref('');        // 出題時後端一起產生的參考要點，交卷時送回去給評分用
const doneCount = ref(0);         // 已經分析完成的回答數

let mediaStream = null;
let mediaRecorder = null;
let recordedChunks = [];
let cancelled = false;            // 離開面試室後，背景回來的結果就不要再處理
let finished = false;             // 是否已正常結束並把結果交給結果頁
let videoUrls = [];               // 每段錄影的播放網址，結果頁重播用

// 背景進行中的工作
let usedFocus = [];               // 已經出過的主題，避免重複
let usedTypes = [];               // 已經出過的題型，避免題目都長得一樣
let nextQuestionPromise = null;   // 預先準備好的下一題
let introPromise = null;          // 自我介紹的分析結果
let answerPromises = [];          // 每一題的分析結果

const progressText = computed(() => {
  if (phase.value === 'finishing') return '全部回答完畢';
  return step.value === 0 ? `自我介紹（共 ${props.count} 題技術題）` : `第 ${step.value} / ${props.count} 題`;
});

const buttonText = computed(() => {
  if (step.value === 0) return isRecording.value ? '結束自我介紹，開始答題' : '開始自我介紹';
  if (!isRecording.value) return '開始回答';
  return step.value < props.count ? '結束回答，下一題' : '結束回答並查看結果';
});

onMounted(async () => {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    if (videoElement.value) {
      videoElement.value.srcObject = mediaStream;
    }

    mediaStream.getTracks().forEach(track => {
      track.onended = () => {
        console.warn(`偵測到 ${track.kind} 軌道中斷！`);
        alert("偵測到攝影機或麥克風權限被關閉，或硬體已斷線！面試將強制結束。");
        emit('cancel-interview');
      };
    });

  } catch (error) {
    alert('無法開啟攝影機與麥克風！請允許權限後再試一次。');
    emit('cancel-interview');
    return;
  }

  // 學生自我介紹的同時，後端先準備第 1 題
  nextQuestionPromise = prefetchQuestion();
  isLoading.value = false;
});

onUnmounted(() => {
  cancelled = true;
  // 面試中途離開：錄影網址用不到了，釋放記憶體（正常結束時交給結果頁，由 App.vue 負責釋放）
  if (!finished) videoUrls.forEach(url => URL.revokeObjectURL(url));
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
  }
});

// ==========================================
// 出題
// ==========================================
const fetchQuestion = async () => {
  const response = await apiFetch('/api/generate-question', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      job_title: props.jobTitle,
      difficulty: props.difficulty,
      used_focus: usedFocus,
      used_types: usedTypes,
      keep_original: props.keepOriginal
    })
  });
  if (!response.ok) throw new Error(`伺服器錯誤狀態碼：${response.status}`);
  const data = await response.json();
  if (data.status !== 'success') throw new Error(data.message || '出題失敗');
  usedFocus.push(data.focus);
  if (data.question_type) usedTypes.push(data.question_type);
  return data;
};

// 在背景先準備下一題；失敗時回傳 null，輪到這題時再重試
const prefetchQuestion = () => fetchQuestion().catch(err => {
  console.warn('預先出題失敗，稍後重試：', err);
  return null;
});

// ==========================================
// 上傳分析（在背景進行，不阻擋學生繼續作答；一律回傳結果物件，不會丟出錯誤）
// ==========================================
const postRecording = async (path, formData) => {
  try {
    for (let attempt = 1; ; attempt++) {
      let response;
      try {
        response = await apiFetch(path, { method: 'POST', body: formData });
      } catch (networkError) {
        // 連不到伺服器（例如網路瞬斷）：重試一次
        if (attempt < 2) { console.warn('上傳失敗，重試一次：', networkError); continue; }
        throw new Error(`無法連線到伺服器（${networkError.message}）`);
      }
      // 盡量讀出後端回傳的錯誤原因，顯示在結果頁
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.detail?.[0]?.msg || `狀態碼：${response.status}`);
      if (data.status !== 'success') throw new Error(data.message || '分析失敗');
      return { ok: true, ...data };
    }
  } catch (error) {
    console.error('分析失敗：', error);
    return { ok: false, error: String(error.message || error) };
  } finally {
    doneCount.value += 1;
  }
};

const fileExt = (blob) => (blob.type.includes('mp4') ? 'mp4' : 'webm');

// 把錄影檔轉成瀏覽器內的播放網址，讓結果頁可以重播（影片只存在這個瀏覽器分頁，不會上傳保存）
const makeVideoUrl = (blob) => {
  const url = URL.createObjectURL(blob);
  videoUrls.push(url);
  return url;
};

const uploadIntro = (blob) => {
  const videoUrl = makeVideoUrl(blob);
  const formData = new FormData();
  formData.append('my_audio', blob, `intro.${fileExt(blob)}`);  // 後端只取其中的聲音來分析
  formData.append('job_title', props.jobTitle);
  return postRecording('/api/analyze-intro', formData)
    .then(result => ({ ...result, videoUrl }));  // 分析失敗時也保留影片
};

const uploadAnswer = (blob, question, points) => {
  const videoUrl = makeVideoUrl(blob);
  const formData = new FormData();
  formData.append('my_audio', blob, `answer.${fileExt(blob)}`);
  formData.append('question', question);
  formData.append('difficulty', props.difficulty);
  formData.append('job_title', props.jobTitle);
  formData.append('key_points', points);
  return postRecording('/api/upload-audio', formData)
    .then(result => ({ question, ...result, videoUrl }));  // 分析失敗時也保留題目和影片
};

// ==========================================
// 錄影
// ==========================================
const toggleRecording = () => {
  if (!isRecording.value) {
    startRecording();
  } else {
    stopRecording();
  }
};

const startRecording = () => {
  try {
    recordedChunks = [];

    if (!mediaStream) {
      throw new Error("攝影機未準備就緒");
    }

    // 依瀏覽器支援度挑選錄影格式（Chrome/Edge 用 webm，Safari 用 mp4）
    const candidates = ['video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4'];
    const mimeType = candidates.find(t => MediaRecorder.isTypeSupported(t));
    mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    };

    mediaRecorder.start();
    isRecording.value = true;
    console.log("錄影成功啟動！使用的格式：", mediaRecorder.mimeType);

  } catch (error) {
    console.error("啟動錄影失敗：", error);
    alert("啟動錄影時發生錯誤，請按 F12 打開開發者工具查看 Console 日誌。");
  }
};

const stopRecording = () => {
  mediaRecorder.onstop = () => {
    const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || 'video/webm' });
    // 送到後端分析，不等結果，直接進入下一步
    if (step.value === 0) {
      introPromise = uploadIntro(blob);
    } else {
      answerPromises.push(uploadAnswer(blob, currentPrompt.value, keyPoints.value));
    }
    goNext();
  };
  isRecording.value = false;
  mediaRecorder.stop();
};

// ==========================================
// 流程控制
// ==========================================
const goNext = async () => {
  if (step.value >= props.count) {
    await finish();
    return;
  }

  step.value += 1;
  phase.value = 'question';
  isLoading.value = true;
  statusText.value = `面試官正在準備第 ${step.value} 題...`;

  // 先用預先準備好的題目，沒有的話（預先出題失敗）就再試一次
  let data = await nextQuestionPromise;
  if (!data) {
    try {
      data = await fetchQuestion();
    } catch (error) {
      if (cancelled) return;
      alert('連線到 AI 面試官失敗，請檢查網路連線或稍後再試。');
      emit('restart');
      return;
    }
  }
  if (cancelled) return;

  currentPrompt.value = data.question;
  keyPoints.value = data.key_points || '';
  isLoading.value = false;

  // 學生作答時，背景先準備再下一題
  nextQuestionPromise = step.value < props.count ? prefetchQuestion() : null;
};

const finish = async () => {
  phase.value = 'finishing';
  isLoading.value = true;
  statusText.value = '正在分析你的回答，這可能需要一至數分鐘...';

  const intro = await introPromise;
  const answers = await Promise.all(answerPromises);
  if (cancelled) return;

  statusText.value = '正在產生整場面試的摘要與建議...';
  let summary = '';
  try {
    const response = await apiFetch('/api/summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_title: props.jobTitle,
        difficulty: props.difficulty,
        intro_transcript: intro.ok && intro.has_speech ? intro.transcript : '',
        intro_feedback: intro.ok && intro.has_speech ? intro.feedback : '',
        answers: answers.map(a => ({
          question: a.question,
          transcript: a.ok ? a.transcript : '',
          feedback: a.ok ? a.feedback : '',
          has_speech: !!(a.ok && a.has_speech)
        }))
      })
    });
    const data = await response.json();
    summary = data.status === 'success' ? data.summary : '';
  } catch (error) {
    console.error('摘要產生失敗：', error);
  }
  if (cancelled) return;

  // 有登入就把結果存成練習紀錄（訪客不保存）
  const saveStatus = auth.token ? await saveRecord(intro, answers, summary) : 'guest';
  if (cancelled) return;

  finished = true;
  emit('end-interview', { intro, answers, summary, saveStatus });
};

// 每一段只存需要的欄位（播放網址 videoUrl 只在這個分頁有效，不存；改存後端的 recording_id）
const toSegment = (s, question = '') => ({
  question: s.question ?? question,
  ok: !!s.ok,
  error: s.error || '',
  has_speech: !!s.has_speech,
  transcript: s.transcript || '',
  feedback: s.feedback || '',
  wpm: s.wpm || 0,
  filler_count: s.filler_count || 0,
  pause_stats: s.pause_stats || {},
  recording_id: s.recording_id || null
});

const saveRecord = async (intro, answers, summary) => {
  statusText.value = '正在儲存練習紀錄...';
  try {
    const { data } = await apiJson('/api/interviews', 'POST', {
      job_title: props.jobTitle,
      difficulty: props.difficulty,
      summary,
      segments: [toSegment(intro || {}), ...answers.map(a => toSegment(a))]
    });
    return data.status === 'success' ? 'saved' : 'failed';
  } catch (error) {
    console.error('儲存練習紀錄失敗：', error);
    return 'failed';
  }
};
</script>

<style scoped>
.interview-container { text-align: center; max-width: 800px; margin: 0 auto; padding: 20px; }
.progress { color: #7f8c8d; font-weight: bold; margin-top: -8px; }
.video-wrapper { background: #000; border-radius: 12px; overflow: hidden; margin-bottom: 20px; aspect-ratio: 16/9; }
video { width: 100%; height: 100%; object-fit: cover; }
.status-box { background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
.question-text { font-size: 1.2rem; font-weight: bold; color: #2c3e50; }
.hint { color: #7f8c8d; margin: 8px 0 0; }
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
