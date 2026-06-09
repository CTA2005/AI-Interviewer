<template>
  <div class="app-container">
    
    <Dashboard 
      v-if="currentView === 'dashboard'" 
      @start-interview="goToInterview" 
    />

    <InterviewRoom 
      v-else-if="currentView === 'interview'" 
      :jobTitle="selectedJob"
      :questionType="selectedType"
      @end-interview="goToReport" 
      @cancel-interview="goToDashboard" 
    />

    <ReportCard 
      v-if="currentView === 'report' && interviewResult" 
      :transcript="interviewResult.transcript" 
      :feedback="interviewResult.feedback" 
      :emotion="interviewResult.emotion"
      @restart="goToDashboard"
    />

  </div>
</template>

<script setup>
import { ref } from 'vue';
import Dashboard from './components/Dashboard.vue';
import InterviewRoom from './components/Interviewroom.vue';
import ReportCard from './components/Report.vue';

const currentView = ref('dashboard');
const selectedJob = ref('');
const selectedType = ref('');
const interviewResult = ref(null); // 存放後端傳回的評分結果

// 切換到面試室
const goToInterview = (payload) => {
  selectedJob.value = payload.job;
  selectedType.value = payload.type;
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
  selectedJob.value = '';
  interviewResult.value = null;
  currentView.value = 'dashboard';
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
