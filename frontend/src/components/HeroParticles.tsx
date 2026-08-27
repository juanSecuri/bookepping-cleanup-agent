/** Inline SVG floating particles for landing hero (CSS-animated, zero libs). */
export default function HeroParticles() {
  const dots = Array.from({ length: 30 }, (_, i) => {
    const x = ((i * 37) % 100)
    const y = ((i * 53) % 100)
    const r = 1.2 + (i % 4) * 0.6
    const dur = 12 + (i % 8) * 2
    const delay = (i % 10) * 0.7
    const cream = i % 3 === 0
    return { x, y, r, dur, delay, cream }
  })

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full opacity-60"
      aria-hidden
      xmlns="http://www.w3.org/2000/svg"
    >
      {dots.map((d, i) => (
        <circle
          key={i}
          cx={`${d.x}%`}
          cy={`${d.y}%`}
          r={d.r}
          fill={d.cream ? 'var(--accent-cream)' : 'var(--positive)'}
          opacity={d.cream ? 0.35 : 0.25}
          style={{
            animation: `particle-float ${d.dur}s ease-in-out ${d.delay}s infinite`,
          }}
        />
      ))}
    </svg>
  )
}
