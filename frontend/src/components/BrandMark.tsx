import { Link } from 'react-router-dom'
import { cn } from '../lib/utils'

type BrandMarkProps = {
  /** Pass empty string to render mark only (no link). */
  to?: string
  size?: 'sm' | 'md' | 'lg' | 'hero'
  showProduct?: boolean
  className?: string
  /** Optional subtitle under product (localized by parent). */
  subtitle?: string
}

/**
 * Text brand: The Profit Catalyst (company) + LedgerAI (product).
 * High-contrast cream on dark sidebar / surfaces.
 */
export default function BrandMark({
  to = '/',
  size = 'md',
  showProduct = true,
  className,
  subtitle,
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
          ? 'text-lg'
          : 'text-xl'

  const inner = (
    <span className={cn('inline-flex flex-col', className)}>
      <span
        className={cn(
          'font-medium uppercase tracking-[0.2em] text-[var(--accent-cream-soft)] opacity-90',
          tag,
        )}
      >
        The Profit Catalyst
      </span>
      {showProduct && (
        <span
          className={cn(
            'font-display font-semibold leading-none text-[var(--accent-cream-soft)]',
            product,
          )}
          style={{ textShadow: '0 1px 12px rgba(0,0,0,0.35)' }}
        >
          LedgerAI
        </span>
      )}
      {(subtitle || size === 'hero') && (
        <span className="mt-1.5 text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--accent-cream-soft)]/85 sm:text-xs">
          {subtitle || 'Bookkeeping Cleanup'}
        </span>
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
