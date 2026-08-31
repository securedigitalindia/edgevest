import { useParams, Link } from 'react-router-dom'
import PageHeader from '../../components/common/PageHeader'
import ArticleBody from '../../components/common/ArticleBody'
import { getArticleBySlug } from '../../content/education'
import './Profile.css'
import './Learn.css'

// Article content only ever carries a plain 'YYYY-MM-DD' (no time component —
// it's a manually-maintained "last updated" courtesy date, not an event
// timestamp), so this formats directly rather than reaching for
// utils/format.js's fmtIstShort (built for full ISO timestamps with a time
// part) or reportUtils.js's fmtDayLabel (drops the year, fine for a report
// month but not for evergreen content someone might read years later).
function fmtArticleDate(dateStr) {
  return new Date(`${dateStr}T00:00:00+05:30`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function LearnArticle() {
  const { slug } = useParams()
  const article = getArticleBySlug(slug)

  if (!article) {
    return (
      <div className="profile-page">
        <PageHeader title="Learn" fallback="/profile/learn" />
        <div className="empty">That article doesn&rsquo;t exist. Head back to <Link to="/profile/learn">Learn</Link>.</div>
      </div>
    )
  }

  return (
    <div className="profile-page">
      <PageHeader title={article.title} fallback="/profile/learn" />
      <div className="edu-article-meta">Last updated {fmtArticleDate(article.lastUpdated)}</div>
      <ArticleBody blocks={article.body} />
    </div>
  )
}
