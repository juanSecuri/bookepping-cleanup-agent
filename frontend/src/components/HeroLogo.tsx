/** Animated 3D-style hero mark for landing (CSS only + generated PNG). */
export default function HeroLogo() {
  return (
    <div className="hero-logo-stage relative mx-auto aspect-square w-full max-w-[min(100%,420px)]">
      <div className="hero-logo-glow absolute inset-[8%] rounded-full opacity-70" aria-hidden />
      <div className="hero-logo-orbit absolute inset-0" aria-hidden>
        <span className="hero-logo-dot" />
        <span className="hero-logo-dot hero-logo-dot--2" />
        <span className="hero-logo-dot hero-logo-dot--3" />
      </div>
      <img
        src="/ledgerai-hero-mark.png"
        alt=""
        className="hero-logo-img relative z-[1] h-full w-full object-contain drop-shadow-2xl"
        decoding="async"
      />
    </div>
  )
}
