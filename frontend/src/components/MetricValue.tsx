import type { ReactNode } from 'react'
import { cn } from '../lib/utils'

/** KPI numbers: sans + tabular (not serif display). */
export default function MetricValue({
  children,
  className,
  size = 'lg',
}: {
  children: ReactNode
  className?: string
  size?: 'md' | 'lg'
}) {
  return (
    <p
      className={cn(
        'font-sans font-semibold tabular-nums tracking-tight text-foreground',
        size === 'lg' ? 'text-2xl sm:text-[1.65rem]' : 'text-xl',
        className,
      )}
    >
      {children}
    </p>
  )
}
