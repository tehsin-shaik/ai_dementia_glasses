import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MemoryCue — Memory, when you need it.",
  description: "AI-assisted memory support that brings everyday context back into view for people experiencing memory loss and their caregivers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
