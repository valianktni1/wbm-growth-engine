const form = document.querySelector("#login-form");
const error = document.querySelector("#login-error");

form.addEventListener("submit", async event => {
  event.preventDefault();
  error.textContent = "";
  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "Signing in…";
  try {
    const payload = Object.fromEntries(new FormData(form));
    const response = await fetch("/api/auth/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Unable to sign in");
    window.location.replace("/");
  } catch (err) {
    error.textContent = err.message;
    button.disabled = false;
    button.textContent = "Sign in securely";
  }
});

