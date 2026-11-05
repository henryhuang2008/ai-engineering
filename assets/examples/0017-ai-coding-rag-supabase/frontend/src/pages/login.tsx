import { useState, type FormEvent } from "react";
import { Navigate, Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

type AuthMode = "sign-in" | "sign-up";

export function LoginPage() {
  const { session, isLoading, error: sessionError } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (isLoading) {
    return <LoadingPage />;
  }
  if (session) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setIsSubmitting(true);

    try {
      const result =
        mode === "sign-in"
          ? await supabase.auth.signInWithPassword({ email, password })
          : await supabase.auth.signUp({ email, password });

      if (result.error) {
        setError(result.error.message);
      } else if (mode === "sign-up" && !result.data.session) {
        setMode("sign-in");
        setNotice("Check your email to confirm your account, then sign in.");
      } else {
        navigate("/", { replace: true });
      }
    } catch (submitError: unknown) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to complete sign-in. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const isSignUp = mode === "sign-up";

  return (
    <main className="flex min-h-svh items-center justify-center bg-muted/40 px-4 py-10">
      <section className="w-full max-w-md rounded-xl border bg-card p-8 text-card-foreground shadow-sm">
        <Link
          to="/"
          className="text-sm font-semibold tracking-wide text-muted-foreground"
        >
          Rag with Supabase
        </Link>
        <h1 className="mt-8 text-3xl font-semibold tracking-tight">
          {isSignUp ? "Create your account" : "Welcome back"}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Sign in to continue to your research workspace.
        </p>

        {(error || sessionError) && (
          <p
            role="alert"
            className="mt-6 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
          >
            {error ?? sessionError}
          </p>
        )}
        {notice && (
          <p
            role="status"
            className="mt-6 rounded-md border bg-muted p-3 text-sm"
          >
            {notice}
          </p>
        )}

        <form className="mt-6 space-y-5" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={isSignUp ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <Button className="w-full" type="submit" disabled={isSubmitting}>
            {isSubmitting
              ? "Please wait..."
              : isSignUp
                ? "Create account"
                : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          {isSignUp ? "Already have an account?" : "New to Rag with Supabase ?"}{" "}
          <button
            className="font-medium text-foreground underline-offset-4 hover:underline"
            type="button"
            onClick={() => {
              setMode(isSignUp ? "sign-in" : "sign-up");
              setError(null);
              setNotice(null);
            }}
          >
            {isSignUp ? "Sign in" : "Create an account"}
          </button>
        </p>
      </section>
    </main>
  );
}

function LoadingPage() {
  return (
    <main className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
      Loading your session...
    </main>
  );
}
