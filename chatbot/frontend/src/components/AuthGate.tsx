import { FormEvent, useState } from "react";
import { Bot, Lock, Mail, UserRound } from "lucide-react";
import { login, signup } from "../lib/api";
import type { User } from "../types";

type AuthGateProps = {
  onAuthenticated: (token: string, user: User) => void;
};

export function AuthGate({ onAuthenticated }: AuthGateProps) {
  const [isSigningUp, setIsSigningUp] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const response = isSigningUp
        ? await signup(name.trim(), email.trim(), password)
        : await login(email.trim(), password);
      onAuthenticated(response.access_token, {
        user_id: response.user_id,
        name: response.name,
        email: response.email,
      });
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="brand-mark">
          <Bot size={28} aria-hidden="true" />
        </div>
        <div>
          <p className="eyebrow">RAG Workspace</p>
          <h1>{isSigningUp ? "Create your account" : "Sign in to the chatbot"}</h1>
          <p className="muted-text">
            Access the assistant, document pipeline, indexing controls, and service status from one
            interface.
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {isSigningUp && (
            <label className="field">
              <span>Name</span>
              <div className="input-with-icon">
                <UserRound size={18} aria-hidden="true" />
                <input
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  minLength={2}
                  required
                />
              </div>
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <div className="input-with-icon">
              <Mail size={18} aria-hidden="true" />
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
          </label>
          <label className="field">
            <span>Password</span>
            <div className="input-with-icon">
              <Lock size={18} aria-hidden="true" />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
          </label>

          {error && <div className="error-banner">{error}</div>}

          <button className="primary-button full-width" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Please wait..." : isSigningUp ? "Create account" : "Sign in"}
          </button>
          <button
            className="secondary-button full-width"
            type="button"
            onClick={() => {
              setIsSigningUp((previous) => !previous);
              setError("");
            }}
          >
            {isSigningUp ? "Already have an account? Sign in" : "New here? Create an account"}
          </button>
        </form>
      </section>
    </main>
  );
}
