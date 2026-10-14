import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Money Making Platform",
  description: "A foundation for managing legitimate online revenue streams.",
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
