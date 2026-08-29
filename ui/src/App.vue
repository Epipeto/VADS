<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="container">
    <!-- Navbar Header -->
    <header class="header">
      <div class="brand">
        <span class="logo-icon">▶</span>
        <h1>SaturnTube</h1>
      </div>
      <nav class="nav-links">
        <RouterLink to="/" class="nav-link">Download</RouterLink>
        <RouterLink to="/logs" class="nav-link">Log</RouterLink>
      </nav>
    </header>

    <!-- Main Content -->
    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
@import './style.css';
</style>

<style>
body {
  margin: 0;
  padding: 0;
}
</style>
