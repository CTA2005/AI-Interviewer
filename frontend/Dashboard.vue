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
  </div>
</template>

<script setup>
import { ref } from 'vue';

// 定義向外發送事件的頻道
const emit = defineEmits(['start-interview']);

const targetJob = ref('');
const targetType = ref('專業技術情境題');

const handleStart = () => {
  // 1. 去除頭尾空白
  const job = targetJob.value.trim(); 
  
  // 2. 防呆驗證：檢查是否為純數字，或者長度小於 2
  const isOnlyNumbers = /^\d+$/.test(job);
  
  if (isOnlyNumbers || job.length < 2) {
    alert("請輸入真實有效的職位名稱！（不可為純數字或單一字母）");
    targetJob.value = ""; // 清空輸入框讓使用者重填
    return; // 終止函數，不會發送給後端
  }

  // 3. 驗證通過，發送包裹
  emit('start-interview', { 
    job: job, 
    type: targetType.value 
  });
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

.start-btn { background-color: #42b883; color: white; padding: 12px 24px; font-size: 1.2rem; border: none; border-radius: 8px; cursor: pointer; margin-top: 15px; font-weight: bold; transition: background-color 0.2s;}
.start-btn:hover:not(:disabled) { background-color: #33996b; }
.start-btn:disabled { background-color: #a0d8c0; cursor: not-allowed; }
</style>
