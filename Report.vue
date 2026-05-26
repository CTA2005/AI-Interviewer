<template>
  <div class="report-container">
    <h2>🎉 面試完成！以下是面試的回饋</h2>

    <div class="emotion-box">
      <h3>面試時的主要表情</h3>
      <div class="emotion-result">
        表情：{{ emotion }}
      </div>
    </div>

    <div class="feedback-section">
      <h3>🎙️ 你的回答 (逐字稿)</h3>
      <p class="content-text">{{ transcript }}</p>
    </div>

    <div class="feedback-section">
      <h3>💡 面試建議</h3>
      <p class="content-text">{{ feedback }}</p>
    </div>

    <button class="primary-btn" @click="$emit('restart')">再練習一次</button>
  </div>
</template>

<script setup>
// 定義從外部 (App.vue) 傳進來的資料
defineProps({
  transcript: {
    type: String,
    required: true
  },
  feedback: {
    type: String,
    required: true
  },
  // 🔥 新增：接收面試時的主要表情
  emotion: {
    type: String,
    default: "未偵測"
  }
  // 🗑️ 注意：這裡已經把 score 拿掉了！
});

// 定義發送給外部的事件 (例如：重新面試)
defineEmits(['restart']);
</script>

<style scoped>
.report-container { max-width: 800px; margin: 0 auto; padding: 30px; font-family: sans-serif; }
.report-header { text-align: center; margin-bottom: 30px; }
.empty-state { text-align: center; padding: 50px; background: white; border-radius: 12px; color: #7f8c8d; }

.score-card { display: flex; align-items: center; justify-content: space-around; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-bottom: 30px;}
.main-score .label { color: #7f8c8d; font-size: 1.1rem; }
.main-score .number { font-size: 4rem; color: #42b883; margin: 0; }
.visual-score p { font-weight: bold; color: #34495e; font-size: 1.1rem; margin: 10px 0;}
.badge { font-size: 0.8rem; color: #95a5a6; font-weight: normal; }

.details-section { text-align: left; background: white; padding: 25px; border-radius: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
.details-section h3 { margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 10px; color: #2c3e50; }
.label { display: block; margin-top: 20px; font-weight: bold; color: #7f8c8d; }

.content-box { padding: 15px; border-radius: 8px; line-height: 1.6; margin-top: 5px; font-size: 1.05rem; }
.transcript { background: #f8f9fa; border-left: 5px solid #3498db; color: #2c3e50; }
.feedback { background: #fff9db; border-left: 5px solid #fcc419; color: #d35400; white-space: pre-line; } /* white-space 讓 AI 的換行符號生效 */

.report-footer { text-align: center; margin-top: 40px; }
.home-btn { background-color: #34495e; color: white; border: none; padding: 12px 30px; border-radius: 8px; cursor: pointer; font-size: 1.1rem; font-weight: bold;}
.home-btn:hover { background-color: #2c3e50; }
</style>