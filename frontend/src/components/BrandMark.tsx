import { Link } from 'react-router-dom'
import { cn } from '../lib/utils'

type BrandMarkProps = {
  /** Pass empty string to render mark only (no link). */
  to?: string
  size?: 'sm' | 'md' | 'lg' | 'hero'
  showProduct?: boolean
  className?: string
}

/**
 * Text brand: The Profit Catalyst (company) + LedgerAI (product).
 * Typography-only mark — no legacy image assets.
 */
export default function BrandMark({
  to = '/',
  size = 'md',
  showProduct = true,
  className,
}: BrandMarkProps) {
  const tag =
    size === 'hero'
      ? 'text-[11px] sm:text-xs tracking-[0.28em]'
      : size === 'sm'
        ? 'text-[9px] tracking-[0.2em]'
        : 'text-[10px] tracking-[0.22em]'

  const product =
    size === 'hero'
      ? 'text-4xl sm:text-5xl md:text-[5.5rem]'
      : size === 'lg'
        ? 'text-2xl'
        : size === 'sm'
          ? 'text-base'
          : 'text-xl'

  const inner = (
    <span className={cn('inline-flex flex-col', className)}>
      <span className={cn('font-medium uppercase text-[var(--text-muted)]', tag)}>
        The Profit Catalyst
      </span>
      {showProduct && (
        <span className={cn('font-display font-medium leading-none text-[var(--accent-cream)]', product)}>
          LedgerAI
        </span>
      )}
      {size === 'hero' && (
        <span className="mt-2 text-sm text-[var(--text-muted)] sm:text-base">Bookkeeping Cleanup</span>
      )}
    </span>
  )

  if (to === '') return inner

  return (
    <Link
      to={to}
      className="inline-flex transition-opacity duration-200 hover:opacity-90"
      title="The Profit Catalyst · LedgerAI"
    >
      {inner}
    </Link>
  )
}
