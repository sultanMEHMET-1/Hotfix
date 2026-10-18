import "@testing-library/jest-dom/vitest";

// jsdom has no IntersectionObserver, and scroll reveals wait for one. Report everything as already in view.
class InViewObserver {
  constructor(private callback: IntersectionObserverCallback) {}
  observe(target: Element) {
    this.callback([{ isIntersecting: true, target, intersectionRatio: 1 } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = InViewObserver;
