/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#12100e',
        parchment: '#f6f1e7',
        board: { light: '#eadfc8', dark: '#7a6a53' },
        accent: '#b4703a',
        moss: '#4b6b53',
        // Chart mark hue. Deeper than the UI accent so it clears 3:1 on the card
        // surface (#fbf9f5); validated with the dataviz palette checker.
        mark: '#a85f28',
        surface: '#fbf9f5',
        grid: '#e7e1d6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        serif: ['Georgia', 'Cambria', 'serif'],
      },
    },
  },
  plugins: [],
}
