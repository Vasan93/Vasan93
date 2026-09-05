import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../store/auth'

const links = [
  { to: '/', label: 'Coach', end: true },
  { to: '/assessment', label: 'Assessment' },
  { to: '/train', label: 'Train' },
  { to: '/play', label: 'Play' },
  { to: '/games', label: 'Games' },
  { to: '/weaknesses', label: 'Work on' },
  { to: '/lessons', label: 'Lessons' },
  { to: '/progress', label: 'Progress' },
  { to: '/profile', label: 'Profile' },
]

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen">
      <header className="border-b border-ink/10 bg-white/70 backdrop-blur">
        <div className="mx-auto max-w-5xl px-6 py-3">
          <div className="flex items-center gap-4">
            <span className="font-serif text-xl font-semibold">GrandmasterAI</span>
            <div className="ml-auto flex items-center gap-3 text-sm">
              {user && (
                <span className="hidden text-ink/60 sm:inline">
                  {user.display_name} · <span className="font-mono">{user.current_rating_estimate}</span>
                </span>
              )}
              <button
                onClick={logout}
                className="rounded-md px-2 py-1 text-ink/60 transition hover:bg-ink/5 hover:text-ink"
              >
                Sign out
              </button>
            </div>
          </div>

          {/*
            Nine destinations do not fit on a phone. The strip scrolls inside itself and
            bleeds to the screen edges, so the page body never scrolls sideways.
          */}
          <nav
            aria-label="Main"
            className="-mx-6 mt-2 overflow-x-auto px-6 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            <ul className="flex w-max gap-1 text-sm">
              {links.map((link) => (
                <li key={link.to}>
                  <NavLink
                    to={link.to}
                    end={link.end}
                    className={({ isActive }) =>
                      `block whitespace-nowrap rounded-md px-3 py-1.5 transition ${
                        isActive ? 'bg-ink/10 font-medium' : 'text-ink/60 hover:text-ink'
                      }`
                    }
                  >
                    {link.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
