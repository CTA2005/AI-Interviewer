<template>
  <div class="dashboard-container">
    <header class="hero">
      <h1>AI 模擬面試練習系統</h1>
      <p>面試回答練習與口語流暢度回饋</p>
    </header>

    <main class="main-action">
      <div class="input-group">
        <label for="jobInput">你想練習哪一種職務的面試？</label>
        <!-- 可以直接輸入，也可以從建議清單中選擇 -->
        <input
          id="jobInput"
          v-model="targetJob"
          list="jobSuggestions"
          maxlength="20"
          placeholder="例如：後端工程師（可從清單選擇或自行輸入）"
          @input="jobError = ''; suggestion = null"
        />
        <datalist id="jobSuggestions">
          <option v-for="job in jobOptions" :key="job" :value="job"></option>
        </datalist>
        <p v-if="jobError" class="error-text">{{ jobError }}</p>

        <!-- 系統把職務對應成別的名稱時，讓使用者自己決定 -->
        <div v-if="suggestion" class="suggest-box">
          <p>系統將「{{ suggestion.original }}」對應為「{{ suggestion.suggested }}」，題目會依照「{{ suggestion.suggested }}」的範圍出題。</p>
          <div class="suggest-actions">
            <button class="suggest-btn primary" :disabled="isChecking" @click="useSuggested">
              使用「{{ suggestion.suggested }}」
            </button>
            <button class="suggest-btn" :disabled="isChecking" @click="keepOriginal">
              保留「{{ suggestion.original }}」
            </button>
          </div>
        </div>
      </div>

      <div class="input-group">
        <label for="difficultyInput">請選擇難易度：</label>
        <select id="difficultyInput" v-model="targetDifficulty">
          <option value="初級">初級（觀念解釋）</option>
          <option value="中級">中級（觀念理解）</option>
          <option value="進階">進階（簡單應用）</option>
        </select>
      </div>

      <div class="input-group">
        <label for="countInput">題目數量：</label>
        <select id="countInput" v-model.number="targetCount">
          <option v-for="n in 5" :key="n" :value="n">{{ n }} 題</option>
        </select>
      </div>

      <p class="flow-hint">流程：自我介紹 → 技術題 {{ targetCount }} 題 → 結果報告</p>

      <button
        v-if="!suggestion"
        class="start-btn"
        :disabled="!targetJob.trim() || isChecking"
        @click="handleStart"
      >
        {{ isChecking ? '正在確認職務...' : '+開始新面試' }}
      </button>
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue';

// 定義向外發送事件的頻道
const emit = defineEmits(['start-interview']);

// 職務建議清單：必須與後端 backend/roles.json 的職務名稱一致（也可以自行輸入其他職務）
const jobOptions = [
  '後端工程師',
  '前端工程師',
  '資料分析師',
  'AI／機器學習工程師',
  '嵌入式／韌體工程師',
  '軟體測試工程師'
];

const targetJob = ref('');
const targetDifficulty = ref('中級');
const targetCount = ref(3);
const jobError = ref('');
const isChecking = ref(false);

// 第一層：格式檢查（後端也有同樣的檢查，這裡只是讓使用者馬上看到錯誤）
const validateJob = (text) => {
  const t = text.trim();
  if (t.length < 2 || t.length > 20) return '職務名稱請輸入 2～20 個字。';
  if (!/^[一-鿿A-Za-z0-9 ／/、\-]+$/.test(t)) return '職務名稱不能包含特殊符號。';
  if (!/[一-鿿]/.test(t)) return '請用中文輸入職務名稱，例如「後端工程師」。';
  return '';
};

const suggestion = ref(null);   // { original, suggested }：系統建議改用的職務名稱，等使用者決定

const startInterview = (job, keepOriginalName = false) => {
  emit('start-interview', {
    job,
    keepOriginal: keepOriginalName,  // 保留原名時，出題也要告訴後端不要再對應
    difficulty: targetDifficulty.value,
    count: targetCount.value
  });
};

// 第二、三層：請後端確認這是合理的資訊相關職務
const checkJob = async (jobTitle, keepOriginalName) => {
  isChecking.value = true;
  try {
    const response = await fetch('http://127.0.0.1:8000/api/check-job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_title: jobTitle, keep_original: keepOriginalName })
    });
    return await response.json();
  } catch (error) {
    return { status: 'error', message: '無法連線到伺服器，請確認後端是否已啟動。' };
  } finally {
    isChecking.value = false;
  }
};

const handleStart = async () => {
  suggestion.value = null;
  jobError.value = validateJob(targetJob.value);
  if (jobError.value) return;

  const data = await checkJob(targetJob.value.trim(), false);
  if (data.status === 'success') {
    startInterview(data.job_title);
  } else if (data.status === 'confirm') {
    // 例如輸入「後端開發」，系統建議對應為「後端工程師」：先問使用者
    suggestion.value = { original: data.original, suggested: data.suggested };
  } else {
    jobError.value = data.message || '無法確認職務名稱，請重新輸入。';
  }
};

const useSuggested = () => {
  startInterview(suggestion.value.suggested);
};

const keepOriginal = async () => {
  const original = suggestion.value.original;
  const data = await checkJob(original, true);  // 為使用者輸入的名稱準備專屬的主題
  if (data.status === 'success') {
    startInterview(data.job_title, true);
  } else {
    suggestion.value = null;
    jobError.value = data.message || '無法確認職務名稱，請重新輸入。';
  }
};
</script>

<style scoped>
.dashboard-container { max-width: 800px; margin: 0 auto; padding: 40px 20px; font-family: sans-serif;}
.hero { text-align: center; margin-bottom: 40px; }
.main-action { background: white; padding: 30px; border-radius: 12px; text-align: center; }

/* 微調了 input-group 讓畫面更有層次 */
.input-group { margin-bottom: 20px; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.input-group label { font-size: 1.1rem; font-weight: bold; color: #2c3e50; }
.input-group input, .input-group select { width: 60%; padding: 10px; font-size: 1.1rem; border: 1px solid #ccc; border-radius: 6px; }

.input-group input { box-sizing: border-box; }
.error-text { color: #c0392b; margin: 0; font-size: 0.95rem; }
.suggest-box { width: 60%; box-sizing: border-box; background: #fff9db; border-left: 5px solid #fcc419; border-radius: 6px; padding: 12px 15px; text-align: left; }
.suggest-box p { margin: 0 0 10px; color: #2c3e50; line-height: 1.5; }
.suggest-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.suggest-btn { padding: 8px 14px; font-size: 1rem; border-radius: 6px; border: 1px solid #ccc; background: white; color: #2c3e50; cursor: pointer; font-weight: bold; }
.suggest-btn.primary { background-color: #42b883; border-color: #42b883; color: white; }
.suggest-btn:disabled { opacity: 0.6; cursor: not-allowed; }
@media (max-width: 600px) { .suggest-box, .input-group input, .input-group select { width: 100%; } }
.flow-hint { color: #7f8c8d; margin: 5px 0 0; }
.start-btn { background-color: #42b883; color: white; padding: 12px 24px; font-size: 1.2rem; border: none; border-radius: 8px; cursor: pointer; margin-top: 15px; font-weight: bold; transition: background-color 0.2s;}
.start-btn:hover:not(:disabled) { background-color: #33996b; }
.start-btn:disabled { background-color: #a0d8c0; cursor: not-allowed; }
</style>
