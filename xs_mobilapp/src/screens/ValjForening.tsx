import { navigate } from '../app/router'
import { ChevronRight } from '../components/icons'
import { useSession } from '../state/session'

/**
 * Only reachable when the user belongs to more than one förening. Switching
 * wipes the förening being left from this device — see session.switchTenant.
 */
export function ValjForening({ standalone = false }: { standalone?: boolean }) {
  const { memberships, activeBrfId, switchTenant } = useSession()

  async function choose(brfId: string) {
    await switchTenant(brfId)
    navigate('/', { replace: true })
  }

  const body = (
    <div className="screen">
      <h1 className="screen__title">Välj förening</h1>
      <p className="screen__lede">
        Du är medlem i flera föreningar. Appen visar en i taget — dokument, svar och nedladdade
        sidor för den förening du lämnar tas bort från telefonen.
      </p>

      <div className="list">
        {memberships.map((membership) => (
          <button
            key={membership.brf_id}
            type="button"
            className="row"
            onClick={() => void choose(membership.brf_id)}
            aria-current={membership.brf_id === activeBrfId ? 'true' : undefined}
          >
            <span className="row__body">
              <span className="row__title">{membership.name}</span>
              <span className="row__meta">
                {membership.role === 'admin' ? 'Administratör' : 'Styrelseledamot'}
                {membership.brf_id === activeBrfId ? ' · aktiv' : ''}
              </span>
            </span>
            <ChevronRight className="row__chevron" />
          </button>
        ))}
      </div>
    </div>
  )

  if (standalone) {
    return (
      <div className="frame">
        <main className="frame__main">{body}</main>
      </div>
    )
  }
  return body
}
