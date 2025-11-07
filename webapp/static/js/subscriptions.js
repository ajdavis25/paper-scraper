document.addEventListener("DOMContentLoaded", () => {
  const form =
    document.querySelector("#subscribe-form") ||
    document.querySelector("#unsubscribe-form");

  if (!form) return;

  const showMessage = (text, type = "info") => {
    if (window.toastifyNotify) {
      window.toastifyNotify(text, type);
    } else if (window.Toastify) {
      Toastify({
        text,
        className: "toastify-" + type,
      }).showToast();
    } else {
      console.log(`[${type}] ${text}`);
    }
  };

  form.addEventListener("submit", (e) => {
    e.preventDefault();  // prevent full page reload

    const email = form.querySelector("input[name='email']").value.trim();
    if (!email) return showMessage("please enter your email", "error");

    fetch(window.location.pathname, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    })
      .then((r) => r.json())
      .then((data) => {
        const type =
          data.status === "success"
            ? "success"
            : data.status === "info"
            ? "info"
            : "error";
        showMessage(data.message, type);
        form.reset();
      })
      .catch(() => showMessage("server error — try again later.", "error"));
  });
});
