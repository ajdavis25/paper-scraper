document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("onboarding-root");
  if (!root) return;

  const steps = Array.from(document.querySelectorAll(".wizard-step"));
  const nextBtn = document.getElementById("wizard-next");
  const backBtn = document.getElementById("wizard-back");
  const saveBtn = document.getElementById("wizard-save");
  const previewBtn = document.getElementById("preview-btn");
  const previewList = document.getElementById("preview-results");
  const previewMessage = document.getElementById("preview-message");
  const autoKeywordField = document.getElementById("auto-keywords");
  const manualKeywordField = document.getElementById("manual-keywords");
  const customExcluded = document.getElementById("custom-excluded");
  const categorySelect = document.getElementById("category-select");
  const categoryHint = document.getElementById("category-hint");
  const manualCategorySelections = new Set();
  const implicitCategorySelections = new Set();
  const domainData = (() => {
    try {
      return JSON.parse(root.dataset.domains || "[]");
    } catch (err) {
      return [];
    }
  })();
  const domainMap = new Map(domainData.map((d) => [d.key, d.categories || []]));
  let currentStep = 0;

  const notify = (msg, type = "info") => {
    if (window.toastifyNotify) {
      window.toastifyNotify(msg, type);
    } else {
      console.log(`[${type}] ${msg}`);
    }
  };

  const existing = (() => {
    try {
      return JSON.parse(root.dataset.existing || "{}");
    } catch (err) {
      return {};
    }
  })();

  function showStep(index) {
    steps.forEach((step, idx) => {
      step.hidden = idx !== index;
    });
    currentStep = index;
    backBtn.disabled = index === 0;
    nextBtn.hidden = index === steps.length - 1;
    saveBtn.hidden = index !== steps.length - 1;
  }

  function dedupe(list) {
    const seen = new Set();
    const out = [];
    list.forEach((item) => {
      const key = item.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        out.push(item);
      }
    });
    return out;
  }

  function getSelectedDomains() {
    const set = new Set();
    document.querySelectorAll(".domain-option:checked").forEach((input) => {
      const value = (input.value || "").trim();
      if (value) {
        set.add(value);
      }
    });
    return set;
  }

  function deriveDomainCategories(existingSelection) {
    const union = new Set();
    const domains = existingSelection || getSelectedDomains();
    domains.forEach((key) => {
      const cats = domainMap.get(key) || [];
      cats.forEach((c) => union.add(c));
    });
    return union;
  }

  function categoriesMatchDomain(cats, allowedSet) {
    if (!cats.length || !allowedSet.size) {
      return false;
    }
    for (const cat of cats) {
      const normalized = cat.toLowerCase();
      for (const allowed of allowedSet) {
        const allowedNorm = (allowed || "").toLowerCase();
        if (!allowedNorm) continue;
        if (
          normalized === allowedNorm ||
          normalized.startsWith(`${allowedNorm}.`) ||
          allowedNorm.startsWith(`${normalized}.`)
        ) {
          return true;
        }
      }
    }
    return false;
  }

  function recomputeImplicitCategories() {
    implicitCategorySelections.clear();
    deriveDomainCategories().forEach((cat) =>
      implicitCategorySelections.add(cat)
    );
    deriveInterestCategories().forEach((cat) =>
      implicitCategorySelections.add(cat)
    );
  }

  function recomputeCategories() {
    recomputeImplicitCategories();
    refreshCategoryOptions();
  }

  function deriveInterestCategories() {
    const union = new Set();
    document.querySelectorAll(".interest-option:checked").forEach((input) => {
      const cats = (input.dataset.categories || "")
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      cats.forEach((cat) => union.add(cat));
    });
    return union;
  }

  function allowedCategorySet() {
    const allowed = deriveDomainCategories();
    deriveInterestCategories().forEach((cat) => allowed.add(cat));
    return allowed;
  }

  function deriveInterestKeywords() {
    const set = new Set();
    document.querySelectorAll(".interest-option:checked").forEach((input) => {
      (input.dataset.keywords || "")
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean)
        .forEach((kw) => set.add(kw));
    });
    return Array.from(set);
  }

  function filterInterestChips() {
    const currentSelection = getSelectedDomains();
    const domainCats = deriveDomainCategories(currentSelection);
    const hasDomainFilter = currentSelection.size > 0;
    document.querySelectorAll(".interest-chip").forEach((chip) => {
      const checkbox = chip.querySelector(".interest-option");
      if (!checkbox) return;
      const chipDomains = (checkbox.dataset.domains || "")
        .split(",")
        .map((d) => d.trim())
        .filter(Boolean);
      const cats = (checkbox.dataset.categories || "")
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      if (!hasDomainFilter) {
        chip.classList.remove("interest-chip-hidden");
        chip.removeAttribute("aria-hidden");
        return;
      }
      const domainMatch =
        chipDomains.length > 0 &&
        chipDomains.some((dom) => currentSelection.has(dom));
      const catMatch = categoriesMatchDomain(cats, domainCats);
      const shouldShow = domainMatch || catMatch;
      chip.classList.toggle("interest-chip-hidden", !shouldShow);
      chip.setAttribute("aria-hidden", shouldShow ? "false" : "true");
    });
    const hint = document.getElementById("interest-hint");
    if (hint) {
      hint.textContent = hasDomainFilter
        ? "showing interests related to your selected domains."
        : "select a domain above to narrow this list or keep everything visible.";
    }
  }

  function gatherPrefs() {
    const interestSelections = deriveInterestKeywords();
    const manualKeywords = (manualKeywordField.value || "")
      .split(/[,\\n]/)
      .map((k) => k.trim())
      .filter(Boolean);
    const excluded = (customExcluded.value || "")
      .split(/[,\\n]/)
      .map((k) => k.trim())
      .filter(Boolean);
    const categories = Array.from(categorySelect.selectedOptions).map(
      (opt) => opt.value
    );
    return {
      keywords: dedupe([...interestSelections, ...manualKeywords]),
      excluded_keywords: dedupe(excluded),
      categories: dedupe([
        ...categories,
        ...Array.from(deriveDomainCategories()),
        ...Array.from(deriveInterestCategories()),
      ]),
      min_score: 1.0,
    };
  }

  function updateKeywordField() {
    const autoKeywords = deriveInterestKeywords();
    autoKeywordField.value = autoKeywords.join(", ");
  }

  function refreshCategoryOptions() {
    const allowed = allowedCategorySet();
    const showAll = allowed.size === 0;
    if (categoryHint) {
      categoryHint.textContent = showAll
        ? "no subcategories matched; you can still pick any."
        : "hold ctrl/cmd to select multiple.";
    }

    Array.from(categorySelect.options).forEach((opt) => {
      const shouldShow =
        showAll ||
        allowed.has(opt.value) ||
        manualCategorySelections.has(opt.value);
      opt.hidden = !shouldShow;
      opt.selected =
        manualCategorySelections.has(opt.value) ||
        implicitCategorySelections.has(opt.value);
    });
  }

  function renderPreview(records) {
    previewList.innerHTML = "";
    if (!records.length) {
      previewList.innerHTML =
        "<p class='muted'>no sample papers yet &mdash; try different keywords.</p>";
      return;
    }
    records.forEach((rec) => {
      const card = document.createElement("div");
      card.className = "preview-card paper";
      const title = rec.title || "untitled";
      const link = rec.link || "";
      const titleMarkup = link
        ? `<a href="${link}" target="_blank" rel="noopener">${title}</a>`
        : title;
      const scoreText =
        typeof rec.score === "number" ? rec.score.toFixed(1) : rec.score ?? "?";
      const whyMarkup = rec.why
        ? `<p class="why-this">why this paper? ${rec.why}</p>`
        : "";
      card.innerHTML = `
        <h4>${titleMarkup}</h4>
        <div class="preview-meta meta">
          <span class="category-tag">${rec.category || "astro-ph"}</span>
          <span class="score-tag">score: ${scoreText}</span>
        </div>
        <p>${rec.summary || ""}</p>
        ${whyMarkup}
      `;
      previewList.appendChild(card);
    });

    if (window.MathJax) {
      const targets = [previewList];
      if (typeof window.MathJax.typesetPromise === "function") {
        window.MathJax.typesetPromise(targets).catch((err) =>
          console.warn("[onboarding] MathJax typeset failed", err)
        );
      } else if (typeof window.MathJax.typeset === "function") {
        try {
          window.MathJax.typeset(targets);
        } catch (err) {
          console.warn("[onboarding] MathJax typeset failed", err);
        }
      }
    }
  }

  nextBtn.addEventListener("click", () => {
    if (currentStep < steps.length - 1) {
      showStep(currentStep + 1);
    }
  });

  backBtn.addEventListener("click", () => {
    if (currentStep > 0) {
      showStep(currentStep - 1);
    }
  });

  previewBtn.addEventListener("click", () => {
    const prefs = gatherPrefs();
    previewBtn.disabled = true;
    fetch("/api/onboarding-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    })
      .then((r) => r.json())
      .then((data) => {
        previewMessage.textContent = data.message || "";
        renderPreview(data.records || []);
      })
      .catch(() => {
        previewMessage.textContent = "unable to load preview right now.";
      })
      .finally(() => {
        previewBtn.disabled = false;
      });
  });

  saveBtn.addEventListener("click", () => {
    const prefs = gatherPrefs();
    saveBtn.disabled = true;
    fetch("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "ok") {
          notify("preferences saved! generating recommendations...", "success");
          setTimeout(() => {
            window.location.href = "/recommendations";
          }, 800);
        } else {
          notify(data.error || "unable to save preferences.", "error");
        }
      })
      .catch(() => notify("unable to save preferences.", "error"))
      .finally(() => {
        saveBtn.disabled = false;
      });
  });

  function hydrateExisting() {
    if (!existing) return;
    const kw = existing.keywords || existing.any_keywords || [];
    const uniqueKw = dedupe(kw);
    manualKeywordField.value = uniqueKw.join(", ");
    const excluded =
      existing.excluded_keywords || existing.exclude_keywords || [];
    customExcluded.value = excluded.join(", ");
    const initialCategories = existing.categories || [];
    manualCategorySelections.clear();
    initialCategories.forEach((cat) => manualCategorySelections.add(cat));
    Array.from(categorySelect.options).forEach((opt) => {
      opt.selected = initialCategories.includes(opt.value);
    });

    const keywordSet = new Set(uniqueKw.map((k) => k.toLowerCase()));
    document.querySelectorAll(".interest-option").forEach((input) => {
      const groupKeywords = (input.dataset.keywords || "")
        .split(",")
        .map((k) => k.trim().toLowerCase())
        .filter(Boolean);
      if (groupKeywords.some((k) => keywordSet.has(k))) {
        input.checked = true;
      }
    });
    updateKeywordField();
    recomputeCategories();
  }

  document.querySelectorAll(".interest-option").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      updateKeywordField();
      recomputeImplicitCategories();
      refreshCategoryOptions();
    });
  });

  categorySelect.addEventListener("change", () => {
    manualCategorySelections.clear();
    Array.from(categorySelect.selectedOptions).forEach((opt) => {
      manualCategorySelections.add(opt.value);
    });
    refreshCategoryOptions();
  });

  document.querySelectorAll(".domain-option").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      filterInterestChips();
      recomputeImplicitCategories();
      refreshCategoryOptions();
    });
  });

  hydrateExisting();
  filterInterestChips();
  recomputeImplicitCategories();
  refreshCategoryOptions();
  showStep(0);
});
