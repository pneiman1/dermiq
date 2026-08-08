// Section header — sets the grain/context for a block once (e.g. "Trailing 12 months")
// so individual cards below don't need to repeat it.
export function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="min-w-0">
      <h2 className="text-base font-semibold tracking-tight sm:text-lg">{title}</h2>
      {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
    </div>
  );
}
