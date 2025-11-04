document.addEventListener("DOMContentLoaded", () => {
  console.log("dashboard.js loaded");

  const form = document.getElementById("prefs-form");
  const status = document.getElementById("save-status");


  // ===============================
  // FEEDBACK FORM HANDLER
  // ===============================
  const feedbackForm = document.getElementById("feedback-form");
  const feedbackStatus = document.getElementById("feedback-status");

  if (feedbackForm) {
    feedbackForm.addEventListener("submit", (e) => {
      e.preventDefault();

      const payload = {
        name: document.getElementById("name").value.trim(),
        email: document.getElementById("email").value.trim(),
        message: document.getElementById("message").value.trim(),
      };

      if (!payload.message) {
        feedbackStatus.textContent = "please enter a message before sending.";
        feedbackStatus.className = "save-status error";
        feedbackStatus.style.opacity = 1;
        setTimeout(() => (feedbackStatus.style.opacity = 0), 3000);
        return;
      }

      fetch("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then((r) => r.json())
        .then((data) => {
          feedbackStatus.textContent = data.message || "feedback sent!";
          feedbackStatus.className = "save-status success";
          feedbackStatus.style.opacity = 1;
          setTimeout(() => (feedbackStatus.style.opacity = 0), 3000);
          feedbackForm.reset();
        })
        .catch(() => {
          feedbackStatus.textContent = "error sending feedback.";
          feedbackStatus.className = "save-status error";
          feedbackStatus.style.opacity = 1;
          setTimeout(() => (feedbackStatus.style.opacity = 0), 4000);
        });
    });
  }


  // ===============================
  // HELPER: FADE-IN MESSAGE
  // ===============================
  const showMessage = (msg, color = "green") => {
    if (!status) return;
    status.textContent = msg;
    status.style.color = color;
    status.style.opacity = 0;
    status.style.transition = "opacity 0.6s ease-in-out";
    requestAnimationFrame(() => (status.style.opacity = 1));

    setTimeout(() => {
      status.style.opacity = 0;
    }, 3000);
  };


  // ===============================
  // VIEW CURRENT PREFS
  // ===============================
  const viewBtn = document.getElementById("view-current");
  const currentPrefs = document.getElementById("current-prefs");

  if (viewBtn && currentPrefs) {
    viewBtn.addEventListener("click", () => {
      fetch("/api/preferences")
        .then((r) => r.json())
        .then((data) => {
          if (!data.exists) {
            currentPrefs.innerHTML = "<em>no preferences saved yet.</em>";
            return;
          }
          const prefs = data.data;
          const kw = prefs.keywords?.join(", ") || "(none)";
          const au = prefs.authors?.join(", ") || "(none)";
          const sc = prefs.min_score || 1.0;

          currentPrefs.innerHTML = `
            <div class="prefs-summary">
              <strong>keywords:</strong> ${kw}<br>
              <strong>authors:</strong> ${au}<br>
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
  // LOAD SAVED PREFS ON PAGE LOAD
  // ===============================
  if (form) {
    fetch("/api/preferences")
      .then((r) => r.json())
      .then((data) => {
        if (data.exists && data.data) {
          const prefs = data.data;
          if (prefs.keywords)
            document.getElementById("keywords").value = prefs.keywords.join(", ");
          if (prefs.authors)
            document.getElementById("authors").value = prefs.authors.join(", ");
          if (prefs.min_score)
            document.getElementById("min_score").value = prefs.min_score;
          showMessage("loaded your saved preferences.", "#555");
        }
      })
      .catch(() => console.log("no saved prefs found."));


    // ===============================
    // SAVE PREFS SUBMISSION
    // ===============================
    form.addEventListener("submit", (e) => {
      e.preventDefault();

      const data = {
        keywords: document
          .getElementById("keywords")
          .value.split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        authors: document
          .getElementById("authors")
          .value.split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        min_score:
          parseFloat(document.getElementById("min_score").value) || 1.0,
      };

      fetch("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
        .then((r) => r.json())
        .then(() => {
          showMessage("preferences saved successfully!", "green");
        })
        .catch(() => {
          showMessage("error saving preferences.", "red");
        });
    });
  }
});


// ===============================
// FEEDBACK PAGE TABLE LOADER
// ===============================
const feedbackTable = document.getElementById("feedback-table");
if (feedbackTable) {
  fetch("/feedback")
    .then((r) => r.json())
    .then((data) => {
      const body = feedbackTable.querySelector("tbody");
      data.feedback.forEach((f) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${f.email}</td>
          <td><a href="https://arxiv.org/abs/${f.arxiv_id}" target="_blank">${f.arxiv_id}</a></td>
          <td>${f.liked ? "👍" : "👎"}</td>
          <td>${new Date(f.timestamp).toLocaleString()}</td>
        `;
        body.appendChild(row);
      });
    })
    .catch(() => {
      feedbackTable.outerHTML = "<p><em>no feedback found.</em></p>";
    });
}


// ===============================
// NAVBAR DASHBOARD LINK HANDLER
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  const dashLink = document.querySelector("#dashboard-link");
  if (!dashLink) return;

  // try localStorage
  const savedEmail = localStorage.getItem("astro_email");
  if (savedEmail) {
    dashLink.href = `/dashboard/${savedEmail}`;
  }

  // if the user saves prefs, also store their email
  const emailField = document.getElementById("email");
  if (emailField) {
    emailField.addEventListener("change", () => {
      if (emailField.value.trim()) {
        localStorage.setItem("astro_email", emailField.value.trim());
      }
    });
  }
});
