document.addEventListener("DOMContentLoaded", () => {
  const form =
    document.querySelector("#subscribe-form") ||
    document.querySelector("#unsubscribe-form");
  const isSubscribeForm = form && form.id === "subscribe-form";

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
    e.preventDefault(); // prevent full page reload

    const email = form.querySelector("input[name='email']").value.trim();
    if (!email) return showMessage("please enter your email", "error");

    const passwordInput = form.querySelector("input[name='password']");
    const payload = { email };
    if (passwordInput && passwordInput.value.trim()) {
      payload.password = passwordInput.value;
    }

    fetch(window.location.pathname, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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
        if (isSubscribeForm && data.redirect_url) {
          setTimeout(() => {
            window.location.href = data.redirect_url;
          }, 600);
        }
      })
      .catch(() => showMessage("server error - try again later.", "error"));
  });
});
