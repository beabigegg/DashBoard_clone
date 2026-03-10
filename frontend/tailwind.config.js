/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './src/**/*.{vue,js,ts,jsx,tsx,html}',
    '../src/mes_dashboard/templates/**/*.html'
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#667eea',
          600: '#5a67d8',
          700: '#4c51bf',
          800: '#4338ca'
        },
        accent: {
          500: '#764ba2'
        },
        surface: {
          app: '#f5f7fa',
          card: '#ffffff',
          muted: '#f8fafc',
          hover: '#f1f5f9',
          active: '#eef2ff'
        },
        stroke: {
          soft: '#e2e8f0',
          panel: '#e3e8f2',
          input: '#dbe4ef'
        },
        text: {
          primary: '#1f2937',
          secondary: '#64748b',
          muted: '#94a3b8',
          subtle: '#475569'
        },
        state: {
          success: '#22c55e',
          warning: '#f59e0b',
          danger: '#ef4444',
          neutral: '#9ca3af',
          info: '#3b82f6'
        }
      },
      fontFamily: {
        sans: ['"Noto Sans TC"', '"Microsoft JhengHei"', 'system-ui', 'sans-serif']
      },
      spacing: {
        shell: '20px',
        panel: '24px',
        nav: '14px',
        block: '12px'
      },
      borderRadius: {
        shell: '10px',
        card: '8px'
      },
      boxShadow: {
        shell: '0 4px 12px rgba(102, 126, 234, 0.3)',
        panel: '0 2px 10px rgba(0, 0, 0, 0.08)',
        soft: '0 1px 4px rgba(0, 0, 0, 0.06)'
      },
      zIndex: {
        popup: '1000'
      }
    }
  },
  corePlugins: {
    preflight: false
  }
};
