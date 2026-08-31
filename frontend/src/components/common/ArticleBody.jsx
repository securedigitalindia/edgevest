import './ArticleBody.css'

// Renders an article's `body` block array (see any file under
// frontend/src/content/education/ for the shape). Deliberately simple —
// { type: 'p' | 'heading' | 'list' | 'callout' | 'table', ... } — rather
// than raw JSX or an MDX pipeline, per docs/prd/financial-education-content.md's
// "Content authoring model" section: ~10 static articles don't justify a
// new build-time dependency.
export default function ArticleBody({ blocks }) {
  return (
    <div className="edu-body">
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'heading':
            return <h2 key={i} className="edu-heading">{block.text}</h2>
          case 'p':
            return <p key={i} className="edu-p">{block.text}</p>
          case 'list':
            return (
              <ul key={i} className="edu-list">
                {block.items.map((item, j) => <li key={j}>{item}</li>)}
              </ul>
            )
          case 'callout':
            return <div key={i} className="edu-callout">{block.text}</div>
          case 'table':
            return (
              <div key={i} className="edu-table-wrap">
                <table className="edu-table">
                  <thead>
                    <tr>{block.headers.map((h, j) => <th key={j}>{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>{row.map((cell, c) => <td key={c}>{cell}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
