<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { addToQueue, fetchStatus, saveConfig } from '../api'

const videoUrl = ref('')
const queue = ref<string[]>([])
const current = ref<string | null>(null)
const running = ref(false)
const downloadPath = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)
const isSavingPath = ref(false)
const pathSaved = ref(false)

let pollTimer: ReturnType<typeof setInterval> | undefined

const refreshStatus = async () => {
  try {
    const data = await fetchStatus()
    queue.value = data.queue
    current.value = data.current
    running.value = data.running
    if (document.activeElement?.id !== 'download-path-input') {
      downloadPath.value = data.path
    }
    errorMessage.value = ''
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Errore di connessione al server'
  }
}

const addDownload = async () => {
  if (!videoUrl.value.trim()) return
  isSubmitting.value = true
  try {
    await addToQueue(videoUrl.value.trim())
    videoUrl.value = ''
    await refreshStatus()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Impossibile aggiungere il link'
  } finally {
    isSubmitting.value = false
  }
}

const updatePath = async () => {
  if (!downloadPath.value.trim()) return
  isSavingPath.value = true
  pathSaved.value = false
  try {
    await saveConfig(downloadPath.value.trim())
    pathSaved.value = true
    setTimeout(() => (pathSaved.value = false), 2000)
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Impossibile salvare il path'
  } finally {
    isSavingPath.value = false
  }
}

onMounted(() => {
  refreshStatus()
  pollTimer = setInterval(refreshStatus, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div>
    <div v-if="errorMessage" class="alert-error">{{ errorMessage }}</div>

    <!-- Input Section -->
    <section class="card input-card">
      <form @submit.prevent="addDownload" class="input-form">
        <input
          v-model="videoUrl"
          type="url"
          placeholder="Incolla l'URL della stagione AnimeSaturn..."
          required
          class="url-input"
        />
        <div class="options-group">
          <button type="submit" class="btn-primary" :disabled="isSubmitting">
            {{ isSubmitting ? 'Aggiunta...' : 'Aggiungi' }}
          </button>
        </div>
      </form>
    </section>

    <!-- Download path -->
    <section class="card path-card">
      <h2>Cartella di Download</h2>
      <form @submit.prevent="updatePath" class="input-form">
        <input
          id="download-path-input"
          v-model="downloadPath"
          type="text"
          placeholder="video/"
          class="url-input"
        />
        <div class="options-group">
          <button type="submit" class="btn-primary" :disabled="isSavingPath">
            {{ isSavingPath ? 'Salvataggio...' : 'Salva' }}
          </button>
          <span v-if="pathSaved" class="saved-hint">Salvato ✓</span>
        </div>
      </form>
    </section>

    <!-- Current Download -->
    <section class="card queue-card">
      <h2>Download in Corso</h2>
      <div v-if="!current" class="empty-state">Nessun download attivo.</div>
      <div v-else class="download-list">
        <div class="download-item">
          <div class="item-info">
            <span class="item-title">{{ current }}</span>
          </div>
          <div class="item-status">
            <div class="progress-bar-container">
              <div class="progress-bar indeterminate"></div>
            </div>
            <span class="status-text downloading">in corso</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Queue -->
    <section class="card queue-card">
      <h2>Coda di Download</h2>
      <div v-if="queue.length === 0" class="empty-state">
        Nessun download in coda. Incolla un link per iniziare.
      </div>
      <div v-else class="download-list">
        <div v-for="(item, index) in queue" :key="index" class="download-item">
          <div class="item-info">
            <span class="item-title">{{ item }}</span>
          </div>
          <div class="item-status">
            <span class="status-text queued">in coda</span>
          </div>
        </div>
      </div>
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

.saved-hint {
  color: #4caf50;
  align-self: center;
}

.progress-bar.indeterminate {
  width: 40%;
  animation: indeterminate 1.2s infinite linear;
}

@keyframes indeterminate {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(250%);
  }
}
</style>
