import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'PMOS | Evidence-backed private markets intelligence',
  description: 'A public-safe presentation of the evidence, relationship and transaction operating layer for private markets.',
}

const capabilities = [
  ['Evidence', 'Every material assertion carries a source, confidence, freshness and review state.'],
  ['Identity', 'People and institutions are resolved without silently merging ambiguous records.'],
  ['Relationships', 'Capital, asset, advisory and introduction paths become inspectable graph edges.'],
  ['Transactions', 'Readiness gates, exceptions, counsel decisions and audit history stay in one workflow.'],
]

export default function PresentationPage() {
  return <main className="presentationPage">
    <nav className="presentationNav" aria-label="Presentation navigation">
      <Link className="presentationBrand" href="/presentation" aria-label="PMOS presentation home"><span>P</span><strong>PMOS</strong></Link>
      <div><a href="#structure">Structure</a><a href="#boundary">Data boundary</a><Link className="presentationNavCta" href="/">Open live demo</Link></div>
    </nav>
    <section className="presentationHero">
      <p className="presentationKicker">PRIVATE MARKETS OPERATING SYSTEM</p>
      <h1>Turn fragmented evidence and relationships into transaction-ready intelligence.</h1>
      <p className="presentationLead">PMOS gives private-market teams one controlled place to understand who matters, what is known, what remains unresolved and what should happen next—without replacing specialist judgment.</p>
      <div className="presentationActions"><Link className="presentationPrimary" href="/">Explore the transaction</Link><a className="presentationSecondary" href="#structure">See how it works</a></div>
      <p className="presentationDisclosure">Public-safe demonstration · Fictional transaction · Real named institutions use public-source identity only</p>
    </section>
    <section className="presentationStatement">
      <p>THE OPERATING QUESTION</p>
      <blockquote>“Is this transaction ready, what could stop it, who needs to decide, who is a credible counterparty, and what evidence supports every conclusion?”</blockquote>
    </section>
    <section className="presentationSection" id="structure">
      <div className="presentationSectionHead"><p>ONE SYSTEM · FOUR CONTROLLED FUNCTIONS</p><h2>From raw information to governed action.</h2></div>
      <div className="presentationCapabilityGrid">{capabilities.map(([title, body], index) => <article key={title}><span>0{index + 1}</span><h3>{title}</h3><p>{body}</p></article>)}</div>
    </section>
    <section className="presentationSection presentationWorkflow">
      <div className="presentationSectionHead"><p>PRIVATE-SALE WORKFLOW</p><h2>Evidence moves through gates—not around them.</h2></div>
      <div className="presentationFlow" aria-label="PMOS private-sale workflow">{['Asset & authority', 'Provenance & attribution', 'Risk & counsel', 'Counterparty fit', 'Closing & audit'].map((step, index) => <div key={step}><span>{index + 1}</span><strong>{step}</strong></div>)}</div>
      <div className="presentationDemoCard">
        <div><p>SYNTHETIC TRANSACTION · PM-2026-014</p><h3>Untitled, 1988</h3><span>$18–24M indicative value · 4 of 5 critical gates supported</span></div>
        <div className="presentationScore"><strong>82</strong><span>READINESS</span></div>
        <Link href="/">Inspect the evidence-backed path →</Link>
      </div>
    </section>
    <section className="presentationBoundary" id="boundary">
      <div><p>PUBLIC PRESENTATION</p><h2>Safe to share.</h2><ul><li>Application and generic workflow</li><li>Synthetic transaction and counterparties</li><li>Real institutional identities from public sources</li><li>Generic scoring and evidence methodology</li></ul></div>
      <div><p>PRIVATE OPERATING ENVIRONMENT</p><h2>Sealed by design.</h2><ul><li>Private contact and investor databases</li><li>Relationship notes and introduction paths</li><li>Proprietary enrichment, scoring and outreach</li><li>Credentials, local databases and private evidence</li></ul></div>
    </section>
    <section className="presentationClose"><p>PMOS preserves specialist judgment while making the evidence around it usable.</p><h2>See the operating layer in action.</h2><Link className="presentationPrimary" href="/">Open the guided demonstration</Link></section>
    <footer className="presentationFooter"><strong>PMOS</strong><span>Public-safe product presentation · No confidential intelligence included</span></footer>
  </main>
}
