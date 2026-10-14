import Link from "next/link";

const capabilities = [
  {
    title: "Bring it together",
    description:
      "Keep the channels that support your business organized in one clear workspace.",
  },
  {
    title: "See what is working",
    description:
      "Build a clearer picture of your earnings and the opportunities behind them.",
  },
  {
    title: "Grow with intention",
    description:
      "Make room for new revenue streams while keeping your business grounded in the details.",
  },
];

export default function Home() {
  return (
    <main className="page-shell">
      <header className="site-header">
        <Link className="brand" href="/" aria-label="Money Making Platform home">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>Money Making Platform</span>
        </Link>
        <span className="status-pill">
          <span className="status-dot" aria-hidden="true" />
          Your business, in view
        </span>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <p className="eyebrow">Make more of what you build</p>
        <h1 id="hero-title">
          Your business has
          <br />
          <span>more room to grow.</span>
        </h1>
        <p className="hero-copy">
          Money Making Platform helps you bring your revenue streams into focus,
          understand what is earning, and plan what comes next.
        </p>
        <a className="primary-link" href="#capabilities">
          See how it works <span aria-hidden="true">→</span>
        </a>
      </section>

      <section
        className="capabilities"
        id="capabilities"
        aria-labelledby="capabilities-title"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">A healthier view of growth</p>
            <h2 id="capabilities-title">Make every stream count</h2>
          </div>
          <p className="section-note">
            Clarity for today. Confidence for what comes next.
          </p>
        </div>
        <div className="capability-grid">
          {capabilities.map((capability, index) => (
            <article className="capability-card" key={capability.title}>
              <span className="card-number">0{index + 1}</span>
              <h3>{capability.title}</h3>
              <p>{capability.description}</p>
              <span className="card-arrow" aria-hidden="true">
                ↗
              </span>
            </article>
          ))}
        </div>
      </section>

      <footer className="site-footer">
        <span>Build sustainable revenue, one stream at a time.</span>
        <Link href="/api/health">Platform status</Link>
      </footer>
    </main>
  );
}
