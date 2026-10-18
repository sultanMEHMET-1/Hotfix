import { m, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { blurFadeIn, spring } from "../lib/motion";

/** Same blur-fade as BlurFade, triggered once when the block scrolls into view. */
export default function ScrollReveal({ children, delay = 0, className, as = "div" }: {
  children: ReactNode; delay?: number; className?: string; as?: "div" | "li";
}) {
  const reduce = useReducedMotion();
  const Tag = as === "li" ? m.li : m.div;
  return (
    <Tag
      className={className}
      initial={reduce ? false : blurFadeIn.initial}
      whileInView={blurFadeIn.animate}
      viewport={{ once: true, margin: "0px" }}
      transition={{ ...spring, delay: reduce ? 0 : delay }}
    >
      {children}
    </Tag>
  );
}
