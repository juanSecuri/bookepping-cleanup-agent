import { Link } from 'react-router-dom'
import { cn } from '../lib/utils'

type BrandMarkProps = {
  /** Pass empty string to render img only (no link). */
  to?: string
  size?: 'sm' | 'md' | 'lg' | 'hero'
  showWordmark?: boolean
  className?: string
}

const sizeMap = {
  sm: 'h-8',
  md: 'h-10',
  lg: 'h-14',
  hero: 'h-[4.5rem] sm:h-24 md:h-28',
} as const

export default function BrandMark({
  to = '/',
  size = 'md',
  showWordmark = false,
  className,
}: BrandMarkProps) {
  const img = (
    <img
      src="/yasnay-logo.png"
      alt="YASNAY — The Profit Catalyst"
      className={cn(sizeMap[size], 'w-auto max-w-full object-contain', className)}
      decoding="async"
    />
  )

  if (to === '') return img

  return (
    <Link
      to={to}
      className={cn(
        'inline-flex items-center gap-3 transition-opacity duration-200 hover:opacity-90',
        showWordmark && 'group',
      )}
      title="YASNAY · LedgerAI"
    >
      {img}
      {showWordmark && (
        <span className="font-display text-lg tracking-[0.08em] text-primary sm:text-xl">
          LedgerAI
        </span>
      )}
    </Link>
  )
}
