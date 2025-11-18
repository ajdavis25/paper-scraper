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

  if (viewBtn && currentPrefs) {
    viewBtn.addEventListener("click", () => {
      fetch("/api/preferences")
        .then(parsePrefsResponse)
        .then(prefs => {
          document.querySelector("#keywords").value = (prefs.keywords || []).join(", ");
          document.querySelector("#excluded_keywords").value = (prefs.excluded_keywords || []).join(", ");
          document.querySelector("#authors").value = (prefs.authors || []).join(", ");
          document.querySelector("#min_score").value = prefs.min_score || 1.0;

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
          const sc = prefs.min_score || 1.0;
          const cat = prefs.categories?.join(", ") || "(astro-ph)";

          currentPrefs.innerHTML = `
            <div class="prefs-summary">
              <strong>keywords:</strong> ${kw}<br>
              <strong>authors:</strong> ${au}<br>
              <strong>excluded keywords:</strong> ${excluded}<br>
              <strong>categories:</strong> ${cat}<br>
              <strong>min score:</strong> ${sc}
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
          if (prefs.min_score)
            document.getElementById("min_score").value = prefs.min_score;

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
        min_score: parseFloat(document.getElementById("min_score").value) || 1.0,
        categories: selectedCategories
      };

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
  // feedback table loader
  // ===============================
  const feedbackTable = document.getElementById("feedback-table");
  if (feedbackTable) {
    console.log("[feedback] loading entries...");
    fetch("/feedback", { headers: { "accept": "application/json" } })
      .then((r) => r.json())
      .then((data) => {
        const body = feedbackTable.querySelector("tbody");
        if (!data.length) {
          body.innerHTML = "<tr><td colspan='5'><em>no feedback found.</em></td></tr>";
          return;
        }

        body.innerHTML = data
          .map(
            (f) => `
          <tr>
            <td>${f.email}</td>
            <td><a href="${f.arxiv_id}" target="_blank">${f.arxiv_id}</a></td>
            <td>${f.liked}</td>
            <td>${f.timestamp}</td>
            <td>${f.source || ""}</td>
          </tr>`
          )
          .join("");
      })
      .catch((err) => {
        console.error("[feedback] failed to load:", err);
        feedbackTable.outerHTML = "<p><em>no feedback found.</em></p>";
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
