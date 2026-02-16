import { Copy, Check } from 'lucide-react'
import { useState, useCallback } from 'react'

type CodeBlockProps = {
  children: string
  language?: string
  className?: string
}

export default function CodeBlock({ children, language, className = '' }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [children])

  return (
    <div className={`relative group rounded-lg overflow-hidden ${className}`}>
      {language && (
        <div className="flex items-center justify-between bg-slate-800 dark:bg-slate-900 px-4 py-1.5 text-[10px] font-medium uppercase tracking-wider text-slate-400">
          {language}
        </div>
      )}
      <pre className="bg-slate-900 dark:bg-black/50 p-4 overflow-x-auto text-sm leading-relaxed">
        <code className="font-mono text-slate-100">{children}</code>
      </pre>
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity rounded p-1.5 bg-slate-700/80 hover:bg-slate-600 text-slate-300"
        aria-label="Copy code"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  )
}
