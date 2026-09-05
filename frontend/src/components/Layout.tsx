import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../store/auth'

const links = [
  { to: '/', label: 'Coach', end: true },
  { to: '/games', label: 'Games' },
  { to: '/profile', label: 'Profile' },
]

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen">
      <header className="border-b border-ink/10 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-6 py-3">
          <span className="font-serif text-xl font-semibold">GrandmasterAI</span>
          <nav className="flex gap-1 text-sm">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 transition ${isActive ? 'bg-ink/10 font-medium' : 'text-ink/60 hover:text-ink'}`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            {user && (
              <span className="text-ink/60">
                {user.display_name} · <span className="font-mono">{user.current_rating_estimate}</span>
              </span>
            )}
            <button onClick={logout} className="rounded-md px-2 py-1 text-ink/60 transition hover:bg-ink/5 hover:text-ink">
              Sign out
            </button>
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
