import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HireLens — resume and job description assessment",
  description:
    "Paste a resume and a job description. Get a fit score, the gaps against the role, and interview questions worth asking.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
