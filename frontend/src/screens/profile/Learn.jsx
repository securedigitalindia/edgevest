import { useNavigate } from 'react-router-dom'
import PageHeader from '../../components/common/PageHeader'
import { MODULES } from '../../content/education'
import './Profile.css'
import './Learn.css'

// Hub screen — one section per module (numbered, Varsity-inspired IA; see
// docs/prd/financial-education-content.md's 2026-09-01 revision), each
// listing its articles as tappable rows. No fetch, no loading state — all
// content is a static import (content authoring model in the PRD).
export default function Learn() {
  const navigate = useNavigate()

  return (
    <div className="profile-page">
      <PageHeader title="Learn" fallback="/profile" />
      <p className="edu-hub-intro">
        Short guides on the F&amp;O mechanics EdgeVest&rsquo;s strategies use, and how to read the numbers
        already on your Dashboard — no personalised advice, just how things work.
      </p>

      {MODULES.map(mod => (
        <div className="phub-section" key={mod.key}>
          <div className="phub-section-title">Module {mod.number} · {mod.title}</div>
          <div className="edu-module-desc">{mod.description}</div>
          {mod.articles.map(a => (
            <div key={a.slug} className="edu-row" onClick={() => navigate(`/profile/learn/${a.slug}`)}>
              <div className="edu-row-main">
                <div className="edu-row-title">{a.title}</div>
                <div className="edu-row-summary">{a.summary}</div>
              </div>
              <span className="phub-row-chevron">›</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
