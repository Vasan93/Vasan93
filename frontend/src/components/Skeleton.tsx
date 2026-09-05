/** Placeholder blocks that hold a screen's shape while its data loads. */
export function SkeletonLine({ className = '' }: { className?: string }) {
  return <div className={`h-4 animate-pulse rounded bg-ink/10 ${className}`} />
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-xl border border-ink/10 bg-white/60 p-4">
      <SkeletonLine className="w-1/3" />
      <div className="mt-3 space-y-2">
        {Array.from({ length: lines }).map((_, index) => (
          <SkeletonLine key={index} className={index === lines - 1 ? 'w-2/3' : 'w-full'} />
        ))}
      </div>
    </div>
  )
}

export function SkeletonBoard() {
  return (
    <div className="mx-auto w-full max-w-[26rem]">
      <div className="aspect-square animate-pulse rounded-xl bg-ink/10" />
    </div>
  )
}

export default function PageSkeleton({ title = true, cards = 2 }: { title?: boolean; cards?: number }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      {title && <SkeletonLine className="h-8 w-56" />}
      <div className="mt-6 space-y-4">
        {Array.from({ length: cards }).map((_, index) => (
          <SkeletonCard key={index} />
        ))}
      </div>
    </div>
  )
}
