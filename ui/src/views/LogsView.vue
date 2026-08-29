<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { fetchLogs } from '../api'

const logs = ref<string[]>([])
const errorMessage = ref('')
const autoRefresh = ref(true)
const logContainer = ref<HTMLElement | null>(null)

let pollTimer: ReturnType<typeof setInterval> | undefined

const loadLogs = async () => {
  try {
    const data = await fetchLogs(500)
    logs.value = data.lines
    errorMessage.value = ''
    await nextTick()
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Errore nel caricare i log'
  }
}

onMounted(() => {
  loadLogs()
  pollTimer = setInterval(() => {
    if (autoRefresh.value) loadLogs()
  }, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div>
    <div v-if="errorMessage" class="alert-error">{{ errorMessage }}</div>

    <section class="card logs-card">
      <div class="logs-header">
        <h2>Log</h2>
        <label class="auto-refresh">
          <input type="checkbox" v-model="autoRefresh" />
          Aggiornamento automatico
        </label>
        <button type="button" class="btn-primary" @click="loadLogs">Aggiorna</button>
      </div>

      <div v-if="logs.length === 0" class="empty-state">Nessun log disponibile.</div>
      <pre v-else ref="logContainer" class="log-output">{{ logs.join('\n') }}</pre>
    </section>
  </div>
</template>

<style scoped>
@import '../style.css';

.alert-error {
  background-color: #3a1a1a;
  border: 1px solid #a33;
  color: #ff8888;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  margin-bottom: 1.5rem;
}

.logs-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.logs-header h2 {
  margin: 0;
  font-size: 1.1rem;
  color: #aaaaaa;
}

.auto-refresh {
  margin-left: auto;
  color: #aaaaaa;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.log-output {
  background-color: #0e0e0e;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 1rem;
  max-height: 70vh;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Courier New', monospace;
  font-size: 0.85rem;
  color: #ccc;
  margin: 0;
}
</style>
