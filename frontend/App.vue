<template>
  <div class="app-container">

    <!-- 帳號列：面試進行中與登入頁不顯示 -->
    <div v-if="showAccountBar" class="account-bar">
      <template v-if="auth.token">
        <span>帳號：<strong>{{ auth.username }}</strong></span>
        <button class="link-btn" @click="goToHistory">練習紀錄</button>
        <button class="link-btn" @click="logout">登出</button>
      </template>
      <template v-else>
        <span class="guest-note">訪客模式（練習結果不會保存）</span>
        <button class="link-btn" @click="goToLogin">登入／註冊</button>
      </template>
    </div>

    <p v-if="currentView === 'loading'" class="loading">載入中...</p>

    <LoginPage
      v-else-if="currentView === 'login'"
      @logged-in="goToDashboard"
      @guest="goToDashboard"
    />

    <Dashboard
      v-else-if="currentView === 'dashboard'"
      @start-interview="goToInterview"
    />

    <InterviewRoom
      v-else-if="currentView === 'interview'"
      :jobTitle="selectedJob"
      :difficulty="selectedDifficulty"
      :count="selectedCount"
      :keepOriginal="keepOriginalJob"
      @end-interview="goToReport"
      @cancel-interview="goToDashboard"
      @restart="goToDashboard"
    />

    <ReportCard
      v-else-if="currentView === 'report' && interviewResult"
      :jobTitle="selectedJob"
      :difficulty="selectedDifficulty"
      :intro="interviewResult.intro"
      :answers="interviewResult.answers"
      :summary="interviewResult.summary"
      :saveStatus="interviewResult.saveStatus"
      @restart="goToDashboard"
    />

    <HistoryList
      v-else-if="currentView === 'history'"
      @open="openRecord"
      @back="goToDashboard"
      @logged-out="handleExpired"
    />

    <HistoryDetail
      v-else-if="currentView === 'historyDetail'"
      :interviewId="selectedRecordId"
      @back="goToHistory"
      @logged-out="handleExpired"
    />

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { auth, apiJson, clearSession } from './api.js';
import LoginPage from './components/Login.vue';
import Dashboard from './components/Dashboard.vue';
import InterviewRoom from './components/Interviewroom.vue';
import ReportCard from './components/Report.vue';
import HistoryList from './components/History.vue';
import HistoryDetail from './components/HistoryDetail.vue';

const currentView = ref('loading');  // 'loading' | 'login' | 'dashboard' | 'interview' | 'report' | 'history' | 'historyDetail'
const selectedJob = ref('');
const selectedDifficulty = ref('中級');
const selectedCount = ref(3);
const keepOriginalJob = ref(false);  // 使用者選擇保留自己輸入的職務名稱
const interviewResult = ref(null);   // 存放整場面試的結果：{ intro, answers, summary, saveStatus }
const selectedRecordId = ref(null);  // 正在查看的練習紀錄

const showAccountBar = computed(() => !['loading', 'login', 'interview'].includes(currentView.value));

// 開啟網站時：之前有登入過，就確認登入是否還有效
onMounted(async () => {
  if (!auth.token) {
    currentView.value = 'login';
    return;
  }
  try {
    const { status, data } = await apiJson('/api/me', 'GET');
    if (status === 200 && data.status === 'success') {
      auth.username = data.username;
      currentView.value = 'dashboard';
    } else {
      clearSession();
      currentView.value = 'login';
    }
  } catch {
    currentView.value = 'login';  // 後端沒開時先停在登入頁
  }
});

// 釋放上一場面試的錄影（影片存在瀏覽器記憶體中，不釋放的話練習越多次佔用越多）
const releaseVideos = () => {
  const r = interviewResult.value;
  if (r) {
    [r.intro, ...(r.answers || [])].forEach(item => {
      if (item?.videoUrl) URL.revokeObjectURL(item.videoUrl);
    });
  }
  interviewResult.value = null;
};

// 切換到面試室
const goToInterview = (payload) => {
  selectedJob.value = payload.job;
  selectedDifficulty.value = payload.difficulty || '中級';
  selectedCount.value = payload.count || 3;
  keepOriginalJob.value = !!payload.keepOriginal;
  currentView.value = 'interview';
};

// 接收面試室傳上來的包裹，並切換到成績單
const goToReport = (resultPayload) => {
  if (resultPayload) {
    interviewResult.value = resultPayload;
  }
  currentView.value = 'report';
};

// 返回首頁並清空資料
const goToDashboard = () => {
  releaseVideos();
  selectedJob.value = '';
  currentView.value = 'dashboard';
};

const goToLogin = () => {
  releaseVideos();
  currentView.value = 'login';
};

const goToHistory = () => {
  releaseVideos();
  currentView.value = 'history';
};

const openRecord = (id) => {
  selectedRecordId.value = id;
  currentView.value = 'historyDetail';
};

const logout = async () => {
  try { await apiJson('/api/logout', 'POST'); } catch { /* 後端沒回應也照樣登出 */ }
  clearSession();
  goToLogin();
};

// 查看紀錄時發現登入已過期
const handleExpired = () => {
  clearSession();
  alert('登入已過期，請重新登入。');
  goToLogin();
};
</script>

<style>
/* 全域共用設定 */
body {
  margin: 0;
  padding: 0;
  background-color: #f0f2f5;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
</style>

<style scoped>
.account-bar {
  max-width: 800px;
  margin: 0 auto;
  padding: 14px 20px 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  color: #2c3e50;
  font-size: 0.95rem;
}
.guest-note { color: #7f8c8d; }
.link-btn {
  background: white;
  border: 1px solid #ccc;
  color: #2c3e50;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.9rem;
}
.link-btn:hover { background: #f8f9fa; }
.loading { text-align: center; color: #7f8c8d; margin-top: 80px; }
</style>
