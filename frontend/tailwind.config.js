/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        graph: {
          artist: '#6366f1',
          release: '#10b981',
          track: '#f59e0b',
          label: '#ef4444',
        },
      },
    },
  },
  plugins: [],
}
