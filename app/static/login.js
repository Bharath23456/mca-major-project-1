const form = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const loginButton = document.querySelector("#login-button");
const registerForm = document.querySelector("#register-form");
const registerError = document.querySelector("#register-error");
const registerButton = document.querySelector("#register-button");
const registerPrompt = document.querySelector("#register-switch");
const registrationMessage = document.querySelector("#registration-message");

document.querySelector("#show-register").addEventListener("click", () => {
  form.hidden = true;
  loginError.hidden = true;
  registerForm.hidden = false;
  registerPrompt.hidden = false;
  registrationMessage.hidden = true;
  registerForm.elements.username.focus();
});

document.querySelector("#show-login").addEventListener("click", () => {
  registerForm.hidden = true;
  registerError.hidden = true;
  registerPrompt.hidden = true;
  form.hidden = false;
  form.elements.username.focus();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  loginButton.disabled = true;
  loginButton.textContent = "Signing in…";

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: form.elements.username.value,
        password: form.elements.password.value,
      }),
      cache: "no-store",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Sign in failed (${response.status}).`);
    window.location.assign("/");
  } catch (error) {
    loginError.textContent = error.message || "Sign in failed. Please try again.";
    loginError.hidden = false;
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = "Sign in";
    form.elements.password.value = "";
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  registerError.hidden = true;
  registerButton.disabled = true;
  registerButton.textContent = "Creating account…";

  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: registerForm.elements.username.value,
        email: registerForm.elements.email.value,
        password: registerForm.elements.password.value,
        confirm_password: registerForm.elements.confirm_password.value,
      }),
      cache: "no-store",
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || `Account creation failed (${response.status}).`);
    }

    registerForm.elements.password.value = "";
    registerForm.elements.confirm_password.value = "";
    form.elements.username.value = result.user.username;
    registerForm.hidden = true;
    registerPrompt.hidden = true;
    form.hidden = false;
    registrationMessage.textContent = result.message;
    registrationMessage.hidden = false;
    form.elements.password.focus();
  } catch (error) {
    registerError.textContent = error.message || "Account creation failed. Please try again.";
    registerError.hidden = false;
  } finally {
    registerButton.disabled = false;
    registerButton.textContent = "Create account";
  }
});
