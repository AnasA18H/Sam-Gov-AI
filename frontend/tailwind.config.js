/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        /** Dark theme: page background = dark grey; login/signup form panel = black */
        matte: '#171717',
        'dark-form': '#0a0a0a',
        'dark-surface': '#141414',
        'dark-elevated': '#1c1c1c',
        'dark-hover': '#262626',
        'dark-border': '#2e2e2e',
        'dark-muted': '#737373',
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
          /** Lighter accent for dark mode (utility bar, icons, links) */
          'dm': '#5EEAD4',
        },
        green: {
          accent: '#10B981',
        },
      },
    },
  },
  plugins: [],
}
