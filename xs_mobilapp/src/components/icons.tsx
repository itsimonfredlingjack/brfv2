/* Inline icons. A whole icon package for nine glyphs would cost more than the
 * rest of the app's JS put together — and the bundle budget is what pays for
 * not shipping a PDF engine. All decorative: labels live on the controls. */

interface IconProps {
  size?: number
  className?: string
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
})

export const AskIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.3-.6L3 21l1.8-4.9A8.4 8.4 0 1 1 21 11.5Z" />
  </svg>
)

export const LibraryIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H9v16H5.5A1.5 1.5 0 0 1 4 18.5Z" />
    <path d="M9 4h4.5A1.5 1.5 0 0 1 15 5.5v13a1.5 1.5 0 0 1-1.5 1.5H9" />
    <path d="m16.6 5.2 2.6.7a1.5 1.5 0 0 1 1 1.9l-3.4 12" />
  </svg>
)

export const ChevronRight = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m9 6 6 6-6 6" />
  </svg>
)

export const ChevronLeft = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m15 6-6 6 6 6" />
  </svg>
)

export const CloseIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
)

export const CheckIcon = ({ size = 15, className }: IconProps) => (
  <svg {...base(size)} className={className} strokeWidth={2.4}>
    <path d="m4 12.5 5 5L20 6.5" />
  </svg>
)

export const SendIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4.5 12h14M12.5 5.5 19 12l-6.5 6.5" />
  </svg>
)

export const AlertIcon = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 4.5 21 20H3Z" />
    <path d="M12 10v4" />
    <path d="M12 17.2v.1" />
  </svg>
)

/* The mark for "nothing could be verified". Deliberately not a cross: nothing
 * failed and nothing is broken — the honest answer is simply that the archive
 * does not settle it. */
export const UnknownIcon = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9.7 9.6a2.4 2.4 0 0 1 4.6.9c0 1.6-2.3 1.9-2.3 3.3" />
    <path d="M12 17.3v.1" />
  </svg>
)

export const ReviewIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M14 3H7a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 7 21h5" />
    <path d="M14 3v4.5h4.5" />
    <circle cx="16.3" cy="15.3" r="3.3" />
    <path d="m18.8 17.8 2.4 2.4" />
  </svg>
)

export const DocIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M14 3H7a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 7 21h10a1.5 1.5 0 0 0 1.5-1.5V7.5Z" />
    <path d="M14 3v4.5h4.5" />
  </svg>
)

export const LockIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
    <path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7" />
  </svg>
)
