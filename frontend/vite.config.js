import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/health': 'http://localhost:8000',
      '/transcripts': 'http://localhost:8000',
      '/transcript_stream': 'http://localhost:8000',
      '/conversations': 'http://localhost:8000',
      '/summary': 'http://localhost:8000',
      '/resume': 'http://localhost:8000',
      '/analyze': 'http://localhost:8000',
      '/analyze_latest': 'http://localhost:8000',
      '/ai_analysis': 'http://localhost:8000',
      '/analysis_results': 'http://localhost:8000',
<<<<<<< Updated upstream
      '/post_interview_analysis': 'http://localhost:8000',
=======
      '/verify': 'http://localhost:8000',
>>>>>>> Stashed changes
      '/audio_stream': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
