import type { Transition } from "framer-motion";

// Spring physics, ease-out feel, no bounce. The same recipe as Telogify and the Portfolio.
export const spring: Transition = { type: "spring", stiffness: 120, damping: 20 };

export const blurFadeIn = {
  initial: { opacity: 0, filter: "blur(10px)", y: 10 },
  animate: { opacity: 1, filter: "blur(0px)", y: 0 },
};
