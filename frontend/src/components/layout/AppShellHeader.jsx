export function AppShellHeader() {
  return (
    <header className="site-header">
      <p className="est">Est. A.D. 2026</p>
      <h1>Boston Tea Party 2.0</h1>
      <p className="tagline">
        Planning agent, constraint engine, and hybrid RAG—live when the API is running.
      </p>
      <div className="rule" aria-hidden="true" />
      <nav className="nav-chapters" aria-label="Sections">
        <a href="#facts">1. Data</a>
        <a href="#report">2. Report</a>
        <a href="#facts">3. Run</a>
      </nav>
    </header>
  );
}
