"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type SiteNavProps = {
  tone?: "light" | "dark";
};

export default function SiteNav({ tone = "light" }: SiteNavProps) {
  const pathname = usePathname();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const mobileMenuRef = useRef<HTMLDivElement | null>(null);
  const isCurrent = (href: string) => pathname === href;

  useEffect(() => {
    setIsMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!isMenuOpen) {
      return;
    }

    const firstLink = mobileMenuRef.current?.querySelector<HTMLAnchorElement>("a");
    firstLink?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isMenuOpen]);

  function closeMenu() {
    setIsMenuOpen(false);
  }

  return (
    <nav className={`site-nav site-nav-${tone}`} aria-label="Primary navigation">
      <Link className="site-brand" href="/">
        <span className="site-brand-mark" aria-hidden="true">◌</span>
        <span>MemoryCue</span>
      </Link>
      <div className="site-nav-links">
        <Link href="/" aria-current={isCurrent("/") ? "page" : undefined}>Product</Link>
        <Link className="site-nav-cta" href="/app" aria-current={isCurrent("/app") ? "page" : undefined}>Try the simulator</Link>
        <Link href="/caregiver" aria-current={isCurrent("/caregiver") ? "page" : undefined}>Caregiver</Link>
      </div>
      <button
        ref={menuButtonRef}
        className={`site-nav-menu-button ${isMenuOpen ? "is-open" : ""}`}
        type="button"
        aria-expanded={isMenuOpen}
        aria-controls="site-mobile-menu"
        aria-label={isMenuOpen ? "Close navigation menu" : "Open navigation menu"}
        onClick={() => setIsMenuOpen((open) => !open)}
      >
        <span aria-hidden="true" />
        <span aria-hidden="true" />
        <span className="site-nav-menu-label">{isMenuOpen ? "Close" : "Menu"}</span>
      </button>
      <div
        ref={mobileMenuRef}
        id="site-mobile-menu"
        className={`site-mobile-menu ${isMenuOpen ? "is-open" : ""}`}
        hidden={!isMenuOpen}
        aria-label="Mobile navigation"
      >
        <Link href="/" aria-current={isCurrent("/") ? "page" : undefined} onClick={closeMenu}>Product</Link>
        <Link href="/app" aria-current={isCurrent("/app") ? "page" : undefined} onClick={closeMenu}>Try the simulator</Link>
        <Link href="/caregiver" aria-current={isCurrent("/caregiver") ? "page" : undefined} onClick={closeMenu}>Caregiver</Link>
      </div>
    </nav>
  );
}
