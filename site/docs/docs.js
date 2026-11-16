(() => {
  const body = document.body;
  const sideToggle = document.getElementById("sideToggle");
  const sideOverlay = document.getElementById("sideOverlay");
  const copyButtons = document.querySelectorAll("[data-copy]");
  const sectionLinks = document.querySelectorAll(".side-link[href^='#']");
  const sections = [...document.querySelectorAll(".doc-section[id]")];

  function setSideOpen(open) {
    body.classList.toggle("side-open", open);
    if (sideToggle) {
      sideToggle.setAttribute("aria-expanded", open ? "true" : "false");
    }
  }

  sideToggle?.addEventListener("click", () => {
    setSideOpen(!body.classList.contains("side-open"));
  });

  sideOverlay?.addEventListener("click", () => setSideOpen(false));

  sectionLinks.forEach((link) => {
    link.addEventListener("click", () => {
      if (window.matchMedia("(max-width: 980px)").matches) {
        setSideOpen(false);
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSideOpen(false);
  });

  copyButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const targetId = button.getAttribute("data-copy");
      const target = targetId ? document.getElementById(targetId) : null;
      const text = target?.textContent?.trim() || "";
      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
        button.classList.add("is-copied");
        const label = button.querySelector("[data-copy-label]");
        const previous = label?.textContent || "Copy";
        if (label) label.textContent = "Copied";
        window.setTimeout(() => {
          button.classList.remove("is-copied");
          if (label) label.textContent = previous;
        }, 1600);
      } catch {
        button.classList.add("is-copied");
        window.setTimeout(() => button.classList.remove("is-copied"), 1200);
      }
    });
  });

  function setActive(id) {
    sectionLinks.forEach((link) => {
      const href = link.getAttribute("href");
      link.classList.toggle("is-active", href === `#${id}`);
    });
  }

  if ("IntersectionObserver" in window && sections.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]?.target?.id) setActive(visible[0].target.id);
      },
      {
        rootMargin: "-20% 0px -55% 0px",
        threshold: [0.1, 0.25, 0.5],
      }
    );
    sections.forEach((section) => observer.observe(section));
  }

  const hash = window.location.hash.slice(1);
  if (hash) setActive(hash);
  else if (sections[0]) setActive(sections[0].id);

  function bootSwagger() {
    if (!window.SwaggerUIBundle) return;

    window.ui = window.SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      displayRequestDuration: true,
      filter: true,
      docExpansion: "list",
      defaultModelsExpandDepth: 0,
      supportedSubmitMethods: [],
      tryItOutEnabled: false,
      presets: [window.SwaggerUIBundle.presets.apis],
      layout: "BaseLayout",
      onComplete: () => {
        const host = document.getElementById("swaggerHost");
        const servers = window.ui?.specSelectors?.servers?.();
        const first = servers && typeof servers.get === "function" ? servers.get(0) : null;
        const url = first && typeof first.get === "function" ? first.get("url") : null;
        if (host && url) host.textContent = url;
      },
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootSwagger);
  } else {
    bootSwagger();
  }
})();
