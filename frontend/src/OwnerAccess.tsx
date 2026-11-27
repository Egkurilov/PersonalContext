import { useEffect, useState, type FormEvent } from "react";

export function OwnerAccess() {
  const [signedIn, setSignedIn] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/me", { signal: controller.signal, cache: "no-store" })
      .then((response) => setSignedIn(response.ok))
      .catch(() => { if (!controller.signal.aborted) setError("Не удалось проверить сеанс."); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const candidate = String(new FormData(form).get("password") ?? "");
    form.reset();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: candidate }), cache: "no-store",
      });
      if (response.ok) setSignedIn(true);
      else setError(response.status === 429 ? "Слишком много попыток. Попробуйте позже." : "Не удалось войти.");
    } catch {
      setError("Не удалось связаться с приложением.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError("");
    try {
      const refresh = await fetch("/api/v1/auth/csrf", { method: "POST", cache: "no-store" });
      if (refresh.status === 401) { setSignedIn(false); return; }
      if (!refresh.ok) throw new Error("Unavailable");
      const value: unknown = await refresh.json();
      if (!value || typeof value !== "object" || !("csrf" in value) || typeof value.csrf !== "string") {
        throw new Error("Invalid response");
      }
      const response = await fetch("/api/v1/auth/logout", {
        method: "POST", headers: { "X-CSRF-Token": value.csrf }, cache: "no-store",
      });
      if (!response.ok) throw new Error("Unavailable");
      setSignedIn(false);
    } catch {
      setError("Не удалось завершить сеанс. Повторите попытку.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="owner-access">
      <h2 id="owner-access">Доступ владельца</h2>
      {signedIn ? (
        <><p>Вход выполнен.</p><button disabled={busy} onClick={logout}>Выйти</button></>
      ) : (
        <>
          <p>Первый раз настройте владельца через значок PersonalContext в системном трее.</p>
          <form onSubmit={login}>
            <label htmlFor="owner-password">Пароль владельца</label>
            <input id="owner-password" name="password" type="password" autoComplete="current-password" required />
            <button disabled={busy} type="submit">Войти</button>
          </form>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
