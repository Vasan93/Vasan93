import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { GameSummary, ImportResult } from '../lib/types'
import { buttonClass, inputClass, Field } from '../components/Field'

const outcomeStyles: Record<string, string> = {
  win: 'bg-moss/15 text-moss',
  loss: 'bg-red-100 text-red-800',
  draw: 'bg-ink/10 text-ink/70',
  unknown: 'bg-ink/5 text-ink/50',
}

export default function GamesPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<'username' | 'pgn'>('username')
  const [platform, setPlatform] = useState<'lichess' | 'chess.com'>('lichess')
  const [username, setUsername] = useState('')
  const [pgn, setPgn] = useState('')
  const [color, setColor] = useState<'white' | 'black'>('white')
  const [notice, setNotice] = useState<string | null>(null)

  const { data: games = [], isLoading } = useQuery({
    queryKey: ['games'],
    queryFn: () => api<GameSummary[]>('/games'),
  })

  const importer = useMutation({
    mutationFn: (body: { path: string; payload: unknown }) =>
      api<ImportResult>(body.path, { method: 'POST', body: JSON.stringify(body.payload) }),
    onSuccess: (result) => {
      setNotice(
        `Imported ${result.imported.length} game${result.imported.length === 1 ? '' : 's'}.` +
          (result.skipped.length ? ` Skipped ${result.skipped.length}.` : ''),
      )
      setPgn('')
      void queryClient.invalidateQueries({ queryKey: ['games'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const remover = useMutation({
    mutationFn: (id: number) => api<void>(`/games/${id}`, { method: 'DELETE' }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['games'] }),
  })

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    setNotice(null)
    if (tab === 'username') importer.mutate({ path: '/games/import/username', payload: { platform, username, max_games: 5 } })
    else importer.mutate({ path: '/games/import/pgn', payload: { pgn, user_color: color } })
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">Your games</h1>
      <p className="mt-1 max-w-prose text-ink/60">
        Your real games show your coach far more than puzzles can. Import a few to get started.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4 rounded-xl border border-ink/10 bg-white/70 p-6">
        <div className="flex gap-1 rounded-lg bg-ink/5 p-1 text-sm">
          {([
            ['username', 'From your account'],
            ['pgn', 'Paste a PGN'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setTab(value)}
              className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${
                tab === value ? 'bg-white shadow-sm' : 'text-ink/60 hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'username' ? (
          <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
            <Field label="Platform">
              <select className={inputClass} value={platform} onChange={(e) => setPlatform(e.target.value as typeof platform)}>
                <option value="lichess">Lichess</option>
                <option value="chess.com">Chess.com</option>
              </select>
            </Field>
            <Field label="Username" hint="We read public games only.">
              <input className={inputClass} value={username} onChange={(e) => setUsername(e.target.value)} required />
            </Field>
          </div>
        ) : (
          <>
            <Field label="PGN" hint="One game, or a file with several.">
              <textarea
                className={`${inputClass} h-36 font-mono text-xs`}
                value={pgn}
                onChange={(e) => setPgn(e.target.value)}
                placeholder={'[Event "Casual game"]\n\n1. e4 e5 2. Nf3 ...'}
                required
              />
            </Field>
            <Field label="Which side were you?">
              <select className={inputClass} value={color} onChange={(e) => setColor(e.target.value as typeof color)}>
                <option value="white">White</option>
                <option value="black">Black</option>
              </select>
            </Field>
          </>
        )}

        {notice && <p className="rounded-lg bg-ink/5 px-3 py-2 text-sm">{notice}</p>}

        <button type="submit" className={buttonClass} disabled={importer.isPending}>
          {importer.isPending ? 'Importing…' : 'Import games'}
        </button>
      </form>

      <section className="mt-8">
        {isLoading && <p className="text-ink/50">Loading…</p>}
        {!isLoading && games.length === 0 && (
          <p className="rounded-xl border border-dashed border-ink/20 px-4 py-8 text-center text-ink/50">
            No games yet. Import one above and your coach will study it.
          </p>
        )}
        <ul className="space-y-2">
          {games.map((game) => (
            <li key={game.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-ink/10 bg-white/60 px-4 py-3">
              <span className={`rounded-md px-2 py-0.5 text-xs font-medium capitalize ${outcomeStyles[game.outcome]}`}>
                {game.outcome}
              </span>
              <Link to={`/games/${game.id}`} className="font-medium hover:text-accent">
                {game.white} vs {game.black}
              </Link>
              <span className="text-xs text-ink/50">
                as {game.user_color} · {Math.ceil(game.ply_count / 2)} moves
              </span>
              <span className="ml-auto flex items-center gap-3 text-xs">
                <span className="text-ink/40">{game.review_status}</span>
                <button onClick={() => remover.mutate(game.id)} className="text-ink/40 transition hover:text-red-700">
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  )
}
