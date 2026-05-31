interface Props {
  message: string
  log?: string[]
}

export function LoadingOverlay({ message, log = [] }: Props) {
  return (
    <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-gray-950/80 backdrop-blur-sm">
      <div className="bg-gray-900 border border-white/10 rounded-2xl p-8 max-w-sm w-full mx-4 shadow-2xl">
        <div className="flex items-center gap-4 mb-4">
          <span className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin shrink-0" />
          <p className="text-white font-semibold text-lg">{message}</p>
        </div>
        {log.length > 0 && (
          <div className="mt-4 bg-black/40 rounded-lg p-3 max-h-40 overflow-y-auto font-mono text-xs text-gray-400 space-y-1">
            {log.map((line, i) => (
              <p key={i} className="truncate">{line}</p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
