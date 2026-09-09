"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type SiteNavProps = {
  tone?: "light" | "dark";
};

export default function SiteNav({ tone = "light" }: SiteNavProps) {
  const pathname = usePathname();
  const isCurrent = (href: string) => pathname === href;

  return (
    <nav className={`site-nav site-nav-${tone}`} aria-label="Primary navigation">
      <Link className="site-brand" href="/">
        <span className="site-brand-mark" aria-hidden="true">◌</span>
        <span>MemoryCue</span>
      </Link>
      <div className="site-nav-links">
        <Link href="/" aria-current={isCurrent("/") ? "page" : undefined}>Product</Link>
        <Link className="site-nav-cta" href="/app" aria-current={isCurrent("/app") ? "page" : undefined}>Try MemoryCue</Link>
        <Link href="/caregiver" aria-current={isCurrent("/caregiver") ? "page" : undefined}>Caregiver</Link>
      </div>
    </nav>
  );
}
