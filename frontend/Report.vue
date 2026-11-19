<template>
  <div class="report-container">
    <h2>{{ mode === 'history' ? '練習紀錄' : '面試完成！以下是面試的回饋' }}</h2>

    <!-- 儲存狀態（剛完成的面試）或練習時間（查看紀錄） -->
    <p v-if="mode === 'history'" class="notice">練習時間：{{ createdText }}</p>
    <p v-else-if="saveStatus === 'saved'" class="notice good">✔ 這次的結果與錄影已儲存到「練習紀錄」。</p>
    <p v-else-if="saveStatus === 'guest'" class="notice">訪客模式：這次的結果不會保存。登入後練習，就能在「練習紀錄」中回顧。</p>
    <p v-else-if="saveStatus === 'failed'" class="notice bad">⚠ 結果儲存失敗，離開這個頁面後將無法再查看。</p>

    <div class="info-section">
      <div class="info-row">
        <div class="info-label">應徵職位：</div>
        <div class="info-text">{{ jobTitle }}（{{ difficulty }}，共 {{ answers.length }} 題）</div>
      </div>
    </div>

    <!-- ① 口語流暢度 -->
    <div class="metrics-panel">
      <h3>口語流暢度分析</h3>
      <div class="fluency-card">
        <div class="fluency-details">
          <p class="sub-title">整場平均</p>
          <p>說話語速 (WPM)： <strong>{{ overall.wpm }}</strong> 字/分</p>
          <p>停頓時間占比： <strong>{{ overall.ratio }}</strong> %
            <span class="note">（共停頓 {{ overall.pauseCount }} 次；定義：字與字之間空白超過 {{ overall.threshold }} 秒）</span>
          </p>
          <p>口頭填充詞 (那個/然後/就是/呃/嗯/啊)： <strong>{{ overall.fillers }}</strong> 個</p>
        </div>

        <div class="table-wrap">
          <table class="fluency-table">
            <thead>
              <tr><th>段落</th><th>語速（字/分）</th><th>停頓占比</th><th>停頓次數</th><th>填充詞</th></tr>
            </thead>
            <tbody>
              <tr v-for="seg in segments" :key="seg.label">
                <td>{{ seg.label }}</td>
                <template v-if="seg.ok && seg.has_speech">
                  <td>{{ seg.wpm }}</td>
                  <td>{{ seg.pause_stats.ratio }}%</td>
                  <td>{{ seg.pause_stats.count }}</td>
                  <td>{{ seg.filler_count }}</td>
                </template>
                <td v-else-if="seg.ok" colspan="4" class="muted">未偵測到有效語音（不列入平均）</td>
                <td v-else colspan="4" class="error-text">分析失敗</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="note">※ 以上為客觀量測數值，僅供練習時自我檢視，不代表面試表現的好壞。說話時間少於 15 秒的段落，停頓占比僅供參考。</p>
      </div>
    </div>

    <!-- ② 自我介紹 -->
    <div class="feedback-section">
      <h3>自我介紹</h3>
      <template v-if="intro?.videoUrl">
        <p class="label">回答影片</p>
        <video class="answer-video" :src="intro.videoUrl" controls playsinline preload="metadata" @loadedmetadata="fixDuration"></video>
      </template>
      <template v-if="intro && intro.ok">
        <p class="label">你的自我介紹（語音轉文字）</p>
        <p class="content-text transcript">{{ intro.transcript || '（沒有辨識到語音）' }}</p>
        <p class="label">回饋</p>
        <p class="content-text feedback">{{ intro.feedback }}</p>
      </template>
      <p v-else class="error-text">自我介紹分析失敗：{{ intro?.error || '未知錯誤' }}</p>
    </div>

    <!-- ③ 各題：題目、語音轉文字、回饋 -->
    <div class="feedback-section" v-for="(a, i) in answers" :key="i">
      <h3>第 {{ i + 1 }} 題</h3>
      <p class="content-text question">{{ a.question }}</p>
      <template v-if="a.videoUrl">
        <p class="label">回答影片</p>
        <video class="answer-video" :src="a.videoUrl" controls playsinline preload="metadata" @loadedmetadata="fixDuration"></video>
      </template>
      <template v-if="a.ok">
        <p class="label">你的回答（語音轉文字）</p>
        <p class="content-text transcript">{{ a.transcript || '（沒有辨識到語音）' }}</p>
        <p class="label">回饋</p>
        <p class="content-text feedback">{{ a.feedback }}</p>
      </template>
      <p v-else class="error-text">這題分析失敗：{{ a.error }}</p>
    </div>

    <!-- ④ 摘要與建議 -->
    <div class="feedback-section summary-section">
      <h3>整場摘要與建議</h3>
      <p v-if="summary" class="content-text summary">{{ summary }}</p>
      <p v-else class="error-text">摘要產生失敗，請參考上面各題的回饋。</p>
    </div>

    <div class="report-footer">
      <button v-if="mode === 'history'" class="primary-btn" @click="$emit('back')">返回練習紀錄</button>
      <button v-else class="primary-btn" @click="$emit('restart')">再練習一次</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  jobTitle: { type: String, default: '未提供職位' },
  difficulty: { type: String, default: '' },
  intro: { type: Object, default: null },          // { ok, has_speech, transcript, feedback, wpm, filler_count, pause_stats } 或 { ok: false, error }
  answers: { type: Array, default: () => [] },     // 每題同上，再加上 question
  summary: { type: String, default: '' },
  mode: { type: String, default: 'live' },         // 'live' = 剛完成的面試，'history' = 查看練習紀錄
  saveStatus: { type: String, default: '' },       // 'saved' | 'guest' | 'failed'（只有 live 模式使用）
  createdAt: { type: Number, default: 0 }          // 練習時間（只有 history 模式使用）
});

defineEmits(['restart', 'back']);

const createdText = computed(() => props.createdAt
  ? new Date(props.createdAt * 1000).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '');

// 瀏覽器錄的 webm 影片沒有寫入總長度（duration 是 Infinity），播放器會無法顯示時間和拖動進度條。
// 常見的解法：先跳到很後面讓瀏覽器算出真正長度，再跳回開頭。
const fixDuration = (event) => {
  const video = event.target;
  if (video.duration !== Infinity) return;
  const reset = () => {
    video.removeEventListener('timeupdate', reset);
    video.currentTime = 0;
  };
  video.addEventListener('timeupdate', reset);
  video.currentTime = 1e101;
};

// 流暢度表格的每一列：自我介紹 + 每一題
const segments = computed(() => [
  { label: '自我介紹', ...(props.intro || { ok: false }) },
  ...props.answers.map((a, i) => ({ label: `第 ${i + 1} 題`, ...a }))
]);

// 整場平均：語速以說話時間加權，停頓占比 = 總停頓時間 / 總說話時間
const overall = computed(() => {
  // 只計算有有效語音的段落（沒說話或只錄到雜音的段落不列入）
  const ok = segments.value.filter(s => s.ok && s.has_speech && s.pause_stats);
  const span = ok.reduce((sum, s) => sum + (s.pause_stats.span_sec || 0), 0);
  const pauseSec = ok.reduce((sum, s) => sum + (s.pause_stats.total_sec || 0), 0);
  let wpm = 0;
  if (span > 0) {
    wpm = Math.round(ok.reduce((sum, s) => sum + s.wpm * (s.pause_stats.span_sec || 0), 0) / span);
  } else if (ok.length) {
    wpm = Math.round(ok.reduce((sum, s) => sum + s.wpm, 0) / ok.length);
  }
  return {
    wpm,
    ratio: span > 0 ? Math.round(pauseSec / span * 1000) / 10 : 0,
    pauseCount: ok.reduce((sum, s) => sum + (s.pause_stats.count || 0), 0),
    fillers: ok.reduce((sum, s) => sum + (s.filler_count || 0), 0),
    threshold: ok[0]?.pause_stats.threshold_sec ?? 0.5
  };
});
</script>

<style scoped>
.report-container { max-width: 800px; margin: 0 auto; padding: 30px 16px; font-family: sans-serif; }
h2 { text-align: center; color: #2c3e50; margin-bottom: 20px; }
.notice { text-align: center; margin: 0 0 25px; padding: 10px 15px; border-radius: 8px; background: #ecf0f1; color: #34495e; }
.notice.good { background: #e8f8f0; color: #1e5631; }
.notice.bad { background: #fdecec; color: #c0392b; }

/* 職位資訊 */
.info-section { background: white; padding: 20px 25px; border-radius: 15px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); margin-bottom: 25px; text-align: left; }
.info-row { font-size: 1.1rem; display: flex; align-items: flex-start; }
.info-label { font-weight: bold; color: #34495e; min-width: 90px; flex-shrink: 0; }
.info-text { color: #2c3e50; line-height: 1.5; background: #f8f9fa; padding: 4px 12px; border-radius: 6px; flex-grow: 1; }

/* 流暢度 */
.metrics-panel { background: white; padding: 25px; border-radius: 15px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); margin-bottom: 25px; text-align: left; }
.metrics-panel h3 { margin-top: 0; color: #34495e; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 20px;}
.fluency-card { background: #f8f9fa; padding: 20px; border-radius: 12px; display: flex; flex-direction: column; gap: 15px;}
.fluency-details p { margin: 5px 0; font-size: 1.05rem; color: #2c3e50; }
.fluency-details strong { font-size: 1.3rem; color: #e74c3c; margin: 0 5px; }
.sub-title { font-weight: bold; color: #34495e !important; }
.note { font-size: 0.85rem; color: #7f8c8d; margin: 0; }

.table-wrap { overflow-x: auto; }
.fluency-table { width: 100%; border-collapse: collapse; background: white; font-size: 0.95rem; }
.fluency-table th, .fluency-table td { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: center; white-space: nowrap; }
.fluency-table th { background: #ecf0f1; color: #34495e; }
.fluency-table td:first-child, .fluency-table th:first-child { text-align: left; }

/* 區塊 */
.feedback-section { text-align: left; background: white; padding: 25px; border-radius: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 25px;}
.feedback-section h3 { margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 10px; color: #2c3e50; }
.label { font-weight: bold; color: #34495e; margin: 15px 0 5px; }
.answer-video { width: 100%; max-height: 360px; background: #000; border-radius: 8px; display: block; }

.content-text { padding: 15px; border-radius: 8px; line-height: 1.6; font-size: 1.05rem; margin: 0; white-space: pre-line; }
.question { background: #eef2f7; border-left: 5px solid #34495e; color: #2c3e50; font-weight: bold; }
.transcript { background: #f8f9fa; border-left: 5px solid #3498db; color: #2c3e50; }
.feedback { background: #fff9db; border-left: 5px solid #fcc419; color: #8a4b00; }
.summary { background: #e8f8f0; border-left: 5px solid #27ae60; color: #1e5631; }
.summary-section { border: 2px solid #27ae60; }
.error-text { color: #c0392b; }
.muted { color: #95a5a6; }

/* 按鈕 */
.report-footer { text-align: center; margin-top: 30px; }
.primary-btn { background-color: #34495e; color: white; border: none; padding: 12px 30px; border-radius: 8px; cursor: pointer; font-size: 1.1rem; font-weight: bold; transition: background-color 0.2s;}
.primary-btn:hover { background-color: #2c3e50; }
</style>
