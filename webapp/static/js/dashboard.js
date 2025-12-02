document.addEventListener("DOMContentLoaded", () => {
  console.log("dashboard.js loaded");

  const form = document.getElementById("prefs-form");
  const notify = (text, type = "info") => {
    if (window.toastifyNotify) {
      window.toastifyNotify(text, type);
    } else {
      console.log(`[${type}] ${text}`);
    }
  };
  const parsePrefsResponse = (response) => {
    if (response.status === 401) {
      window.location.href = "/login";
      return Promise.reject(new Error("authentication required"));
    }
    return response.json();
  };
  const DEFAULT_WEIGHTS = {
    keyword_weight: 1.0,
    author_weight: 3.0,
    exclude_penalty: 2.0,
    all_bonus: 2.0,
  };

  const clampNumber = (value, min, max) => {
    if (!Number.isFinite(value)) return value;
    if (Number.isFinite(min)) value = Math.max(value, min);
    if (Number.isFinite(max)) value = Math.min(value, max);
    return value;
  };

  const setNumberInput = (id, value, fallback) => {
    const node = document.getElementById(id);
    if (!node) return;
    const resolved =
      Number.isFinite(value) && value >= 0 ? value : fallback ?? node.value;
    node.value = resolved;
  };

  const readNumberInput = (id, fallback) => {
    const node = document.getElementById(id);
    if (!node) return fallback;
    const min = node.min !== "" ? parseFloat(node.min) : undefined;
    const max = node.max !== "" ? parseFloat(node.max) : undefined;
    const parsed = parseFloat(node.value);
    if (!Number.isFinite(parsed)) {
      node.value = fallback;
      return fallback;
    }
    const clamped = clampNumber(parsed, min, max);
    node.value = clamped;
    return clamped;
  };


  // ===============================
  // feedback form submission
  // ===============================
  const feedbackForm = document.getElementById("feedback-form");
  const setFeedbackStatus = (message, type) => {
    notify(message, type);
  };

  if (feedbackForm) {
    feedbackForm.addEventListener("submit", (e) => {
      e.preventDefault();

      const payload = {
        name: document.getElementById("name").value.trim(),
        email: document.getElementById("email").value.trim(),
        message: document.getElementById("message").value.trim(),
      };

      if (!payload.message) {
        setFeedbackStatus("please enter a message before sending.", "error");
        return;
      }

      fetch("/send-feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then((r) => r.json())
        .then((data) => {
          setFeedbackStatus(data.message || "feedback sent!", "success");
          feedbackForm.reset();
        })
        .catch(() => {
          setFeedbackStatus("error sending feedback.", "error");
        });
    });
  }


  // ===============================
  // helper: fade in message
  // ===============================
  const showMessage = (msg, type = "success") => {
    notify(msg, type);
  };


  // ===============================
  // view current prefs
  // ===============================
  const viewBtn = document.getElementById("view-current");
  const currentPrefs = document.getElementById("current-prefs");

  const minScoreInput = document.getElementById("min_score");

  const readMinScore = () => {
    if (!minScoreInput) return 1.0;
    const parsed = parseFloat(minScoreInput.value);
    if (!Number.isFinite(parsed) || parsed < 0) {
      minScoreInput.value = 1.0;
      return 1.0;
    }
    return parsed;
  };

  if (viewBtn && currentPrefs) {
    viewBtn.addEventListener("click", () => {
      fetch("/api/preferences")
        .then(parsePrefsResponse)
        .then(prefs => {
          document.querySelector("#keywords").value = (prefs.keywords || []).join(", ");
          document.querySelector("#excluded_keywords").value = (prefs.excluded_keywords || []).join(", ");
          document.querySelector("#authors").value = (prefs.authors || []).join(", ");
          document.querySelector("#min_score").value =
            typeof prefs.min_score === "number" ? prefs.min_score : 1.0;
          setNumberInput("keyword_weight", prefs.keyword_weight, DEFAULT_WEIGHTS.keyword_weight);
          setNumberInput("author_weight", prefs.author_weight, DEFAULT_WEIGHTS.author_weight);
          setNumberInput("exclude_penalty", prefs.exclude_penalty, DEFAULT_WEIGHTS.exclude_penalty);
          setNumberInput("all_bonus", prefs.all_bonus, DEFAULT_WEIGHTS.all_bonus);

          // categories
          const catSelect = document.getElementById("categories");
          if (catSelect && prefs.categories) {
            [...catSelect.options].forEach(opt => {
              opt.selected = prefs.categories.includes(opt.value);
            });
          }

          const kw = prefs.keywords?.join(", ") || "(none)";
          const excluded = prefs.excluded_keywords?.join(", ") || "(none)";
          const au = prefs.authors?.join(", ") || "(none)";
          const sc = typeof prefs.min_score === "number" ? prefs.min_score : 1.0;
          const cat = prefs.categories?.join(", ") || "(astro-ph)";
          const kwWeight = prefs.keyword_weight ?? DEFAULT_WEIGHTS.keyword_weight;
          const auWeight = prefs.author_weight ?? DEFAULT_WEIGHTS.author_weight;
          const exPenalty = prefs.exclude_penalty ?? DEFAULT_WEIGHTS.exclude_penalty;
          const allBonus = prefs.all_bonus ?? DEFAULT_WEIGHTS.all_bonus;

          currentPrefs.innerHTML = `
            <div class="prefs-summary">
              <strong>keywords:</strong> ${kw}<br>
              <strong>authors:</strong> ${au}<br>
              <strong>excluded keywords:</strong> ${excluded}<br>
              <strong>categories:</strong> ${cat}<br>
              <strong>min score:</strong> ${sc}<br>
              <strong>weights:</strong> kw=${kwWeight}, authors=${auWeight}, exclude=${exPenalty}, all=${allBonus}
            </div>
          `;
        })
        .catch(() => {
          currentPrefs.innerHTML = "<em>error loading preferences.</em>";
        });
    });
  }


  // ===============================
  // load saved prefs on page load
  // ===============================
  if (form) {
    fetch("/api/preferences")
      .then(parsePrefsResponse)
      .then((prefs) => {
        if (prefs) {
          if (prefs.keywords)
            document.getElementById("keywords").value = prefs.keywords.join(", ");
          if (prefs.excluded_keywords)
            document.getElementById("excluded_keywords").value = prefs.excluded_keywords.join(", ");
          if (prefs.authors)
            document.getElementById("authors").value = prefs.authors.join(", ");
          if (typeof prefs.min_score === "number")
            document.getElementById("min_score").value = prefs.min_score;
          setNumberInput("keyword_weight", prefs.keyword_weight, DEFAULT_WEIGHTS.keyword_weight);
          setNumberInput("author_weight", prefs.author_weight, DEFAULT_WEIGHTS.author_weight);
          setNumberInput("exclude_penalty", prefs.exclude_penalty, DEFAULT_WEIGHTS.exclude_penalty);
          setNumberInput("all_bonus", prefs.all_bonus, DEFAULT_WEIGHTS.all_bonus);

          // categories
          const catSelect = document.getElementById("categories");
          if (catSelect && prefs.categories) {
            [...catSelect.options].forEach(opt => {
              opt.selected = prefs.categories.includes(opt.value);
            });
          }

          showMessage("loaded your saved preferences.", "success");
        }
      })
      .catch(() => console.log("no saved prefs found."));


    // ===============================
    // save prefs submission
    // ===============================
    form.addEventListener("submit", (e) => {
      e.preventDefault();

      const selectedCategories = [...document.getElementById("categories").selectedOptions]
        .map(opt => opt.value);

      const data = {
        keywords: document
          .getElementById("keywords")
          .value.split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        excluded_keywords: document
          .getElementById("excluded_keywords")
          .value.split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        authors: document
          .getElementById("authors")
          .value.split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        min_score: readMinScore(),
        categories: selectedCategories
      };
      data.keyword_weight = readNumberInput("keyword_weight", DEFAULT_WEIGHTS.keyword_weight);
      data.author_weight = readNumberInput("author_weight", DEFAULT_WEIGHTS.author_weight);
      data.exclude_penalty = readNumberInput("exclude_penalty", DEFAULT_WEIGHTS.exclude_penalty);
      data.all_bonus = readNumberInput("all_bonus", DEFAULT_WEIGHTS.all_bonus);

      fetch("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
        .then((r) => r.json())
        .then(() => {
          showMessage("preferences saved successfully!", "success");
        })
        .catch(() => {
          showMessage("error saving preferences.", "error");
        });
    });
  }


  // ===============================
  // navbar dashboard link handler
  // ===============================
  const dashLink = document.querySelector("#dashboard-link");
  if (dashLink) {
    const savedEmail = localStorage.getItem("astro_email");
    if (savedEmail) {
      dashLink.href = `/dashboard/${savedEmail}`;
    }

    const emailField = document.getElementById("email");
    if (emailField) {
      emailField.addEventListener("change", () => {
        if (emailField.value.trim()) {
          localStorage.setItem("astro_email", emailField.value.trim());
        }
      });
    }
  }
});
