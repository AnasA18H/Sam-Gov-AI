/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
        },
        // Design colors from cover.png
        purple: {
          dark: '#2D1B3D',
        },
        teal: {
          light: '#14B8A6',
          DEFAULT: '#14B8A6',
          dark: '#0D9488',
        },
        green: {
          accent: '#10B981',
        },
      },
    },
  },
  plugins: [],
}
