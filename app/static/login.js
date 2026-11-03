const form = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const loginButton = document.querySelector("#login-button");
const registerForm = document.querySelector("#register-form");
const registerError = document.querySelector("#register-error");
const registerButton = document.querySelector("#register-button");
const registerPrompt = document.querySelector("#register-switch");
const registrationMessage = document.querySelector("#registration-message");
const captchaStatus = document.querySelector("#captcha-status");
const captchaWidget = document.querySelector("#recaptcha-widget");
const passwordToggle = document.querySelector("#password-toggle");
const localTestCaptchaToken = "cloudnetops-local-captcha-test-token";
let captchaConfig = null;
let captchaWidgetId = null;
let captchaReady = false;

async function initializeCaptcha() {
  try {
    const response = await fetch("/api/auth/captcha-config", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "CAPTCHA configuration is unavailable.");
    captchaConfig = result;

    if (captchaConfig.mode === "test") {
      captchaStatus.textContent =
        "Local CAPTCHA test mode is active. Do not use this mode outside local development.";
      captchaReady = true;
      return;
    }
    if (captchaConfig.mode !== "recaptcha" || !captchaConfig.site_key) {
      throw new Error("Google reCAPTCHA is not configured.");
    }

    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://www.google.com/recaptcha/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error("Google reCAPTCHA could not be loaded."));
      document.head.append(script);
    });
    await new Promise((resolve) => window.grecaptcha.ready(resolve));
    captchaWidgetId = window.grecaptcha.render(captchaWidget, {
      sitekey: captchaConfig.site_key,
    });
    captchaStatus.textContent = "Complete the reCAPTCHA checkbox to continue.";
    captchaReady = true;
  } catch (error) {
    captchaStatus.textContent = error.message || "CAPTCHA initialization failed.";
  }
}

function currentCaptchaToken() {
  if (captchaConfig?.mode === "test") return localTestCaptchaToken;
  if (captchaWidgetId === null || !window.grecaptcha) return "";
  return window.grecaptcha.getResponse(captchaWidgetId);
}

passwordToggle.addEventListener("click", () => {
  const visible = form.elements.password.type === "password";
  form.elements.password.type = visible ? "text" : "password";
  passwordToggle.textContent = visible ? "Hide" : "Show";
  passwordToggle.setAttribute("aria-pressed", String(visible));
});

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
  if (!captchaReady) {
    loginError.textContent = "CAPTCHA is not ready. Check the configuration and try again.";
    loginError.hidden = false;
    return;
  }
  const captchaToken = currentCaptchaToken();
  if (!captchaToken) {
    loginError.textContent = "Complete the reCAPTCHA checkbox before signing in.";
    loginError.hidden = false;
    return;
  }
  loginButton.disabled = true;
  loginButton.textContent = "Signing in…";

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: form.elements.username.value,
        password: form.elements.password.value,
        captcha_token: captchaToken,
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
    if (captchaWidgetId !== null && window.grecaptcha) {
      window.grecaptcha.reset(captchaWidgetId);
    }
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

initializeCaptcha();
