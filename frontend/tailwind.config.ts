import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Every colour role resolves to a token in src/styles/tokens.css. This
      // used to point at a parallel slate/teal palette defined in globals.css,
      // which is why the site rendered blue while tokens.css coloured only the
      // charts. There is now one colour system.
      //
      // hsl(var(--ui-x) / <alpha-value>) rather than hsl(var(--ui-x)) so the
      // alpha modifiers this codebase uses — bg-primary/10, bg-muted/50,
      // bg-card/80 — keep working.
      colors: {
        // Preflight resolves ::placeholder to theme('colors.gray.400'), so the
        // only way to keep its gray out of the compiled CSS is to point that
        // entry at a token. Overriding ::placeholder in globals.css wins at
        // runtime but leaves the hex in the bundle, and the gate reads the
        // bundle.
        gray: {
          400: "hsl(var(--ui-muted-foreground))",
        },
        border: "hsl(var(--ui-border) / <alpha-value>)",
        input: "hsl(var(--ui-input) / <alpha-value>)",
        ring: "hsl(var(--ui-ring) / <alpha-value>)",
        background: "hsl(var(--ui-background) / <alpha-value>)",
        foreground: "hsl(var(--ui-foreground) / <alpha-value>)",
        primary: {
          DEFAULT: "hsl(var(--ui-primary) / <alpha-value>)",
          foreground: "hsl(var(--ui-primary-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "hsl(var(--ui-muted) / <alpha-value>)",
          foreground: "hsl(var(--ui-muted-foreground) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "hsl(var(--ui-accent) / <alpha-value>)",
          foreground: "hsl(var(--ui-accent-foreground) / <alpha-value>)",
        },
        card: {
          DEFAULT: "hsl(var(--ui-card) / <alpha-value>)",
          foreground: "hsl(var(--ui-card-foreground) / <alpha-value>)",
        },
        popover: {
          DEFAULT: "hsl(var(--ui-popover) / <alpha-value>)",
          foreground: "hsl(var(--ui-popover-foreground) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "hsl(var(--ui-destructive) / <alpha-value>)",
          foreground: "hsl(var(--ui-destructive-foreground) / <alpha-value>)",
        },
        // Brand tokens, straight through as hex. Named so a component can reach
        // the palette without a hex literal of its own.
        brand: {
          DEFAULT: "var(--accent)",
          deep: "var(--plum-deep)",
          mid: "var(--plum-mid)",
          light: "var(--plum-light)",
        },
        status: {
          critical: "var(--status-critical)",
          warning: "var(--status-warning)",
          ok: "var(--status-ok)",
        },
      },
      // Preflight's universal reset is `border: 0 solid <borderColor.DEFAULT>`,
      // which ships Tailwind's gray-200 into the bundle unless it is pointed at
      // a token. Same reason ::placeholder is overridden in globals.css.
      borderColor: {
        DEFAULT: "hsl(var(--ui-border) / <alpha-value>)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [tailwindcssAnimate],
};

export default config;
