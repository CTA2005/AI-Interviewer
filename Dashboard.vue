<!-- src/components/Dashboard.vue -->
<template>
  <div class="dashboard-container">
    <header class="hero">
      <h1>AI 模擬面試系統</h1>
      <p>結合臉部辨識，打造最真實的面試體驗</p>
    </header>

    <main class="main-action">
      <div class="input-group">
        <label for="jobInput">你想面試什麼職位？</label>
        <input 
          id="jobInput" 
          v-model="targetJob" 
          type="text" 
          placeholder="例如：軟體工程師、產品經理..." 
        />
      </div>

      <div class="input-group">
        <label for="typeInput">請選擇題目類型：</label>
        <select id="typeInput" v-model="targetType">
          <option value="專業技術情境題">專業技術情境題</option>
          <option value="過往經驗與行為題">過往經驗與行為題</option>
        </select>
      </div>
      
      <button 
        class="start-btn" 
        :disabled="!targetJob"
        @click="handleStart"
      >
        +開始新面試
      </button>
    </main>
    <hr class="divider" />
    <section class="history-section">
      <h2>過去的面試紀錄</h2>
      <div class="history-list">
        <div v-for="session in mockHistory" :key="session.id" class="history-card">
          <div class="card-info">
            <h3>{{ session.job }}</h3>
            <span class="date">{{ session.date }}</span>
          </div>
          <div class="card-score">
            <span class="score">{{ session.score }}</span> 分
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue';

// 定義向外發送事件的頻道
const emit = defineEmits(['start-interview']);

const targetJob = ref('');
const mockHistory = ref([
  { id: 1, job: '前端工程師', date: '2026-05-20 14:30', score: 85 },
]);

const targetType = ref('專業技術情境題');
const handleStart = () => {
  // 把使用者輸入的職業，當作「包裹」往外發送給 App.vue
  emit('start-interview', { 
    job: targetJob.value, 
    type: targetType.value 
  });
};
</script>

<style scoped>
/* 這裡放原本 .dashboard-container 到 .history-card 的 CSS */
.dashboard-container { max-width: 800px; margin: 0 auto; padding: 40px 20px; font-family: sans-serif;}
.hero { text-align: center; margin-bottom: 40px; }
.main-action { background: white; padding: 30px; border-radius: 12px; text-align: center; }
.input-group input { width: 60%; padding: 10px; font-size: 1.1rem; }
.start-btn { background-color: #42b883; color: white; padding: 12px 24px; font-size: 1.2rem; border: none; border-radius: 8px; cursor: pointer; margin-top: 15px;}
.start-btn:disabled { background-color: #a0d8c0; }
.history-card { display: flex; justify-content: space-between; background: white; padding: 15px; margin-bottom: 10px; border-radius: 8px;}
</style>