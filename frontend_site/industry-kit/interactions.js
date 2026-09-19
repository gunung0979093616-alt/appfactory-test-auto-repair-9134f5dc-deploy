window.INDUSTRY_KIT = {"motion_profile": "status-reveal", "reduced_motion_safe": true};
(function () {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const targets = document.querySelectorAll('.hero, .proof-rail, .quality-band, .industry-components, .industry-journey-grid, .flow, .section-head, main > .card');
  targets.forEach((node, index) => {
    node.dataset.reveal = String(index + 1);
    node.style.transitionDelay = `${Math.min(index, 5) * 45}ms`;
  });
  if (reduceMotion || !('IntersectionObserver' in window)) return;
  document.body.classList.add('motion-ready');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12 });
  targets.forEach((node) => observer.observe(node));
})();
