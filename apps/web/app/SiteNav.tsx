import Link from "next/link";

type SiteNavProps = {
  tone?: "light" | "dark";
};

export default function SiteNav({ tone = "light" }: SiteNavProps) {
  return (
    <nav className={`site-nav site-nav-${tone}`} aria-label="Primary navigation">
      <Link className="site-brand" href="/">
        <span className="site-brand-mark" aria-hidden="true">◌</span>
        <span>MemoryCue</span>
      </Link>
      <div className="site-nav-links">
        <Link href="/">Product</Link>
        <Link className="site-nav-cta" href="/app">Try MemoryCue</Link>
        <Link href="/caregiver">Caregiver</Link>
      </div>
    </nav>
  );
}
