import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

interface CurrentUser {
  id: string;
  email: string | null;
}

export function HomePage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSigningOut, setIsSigningOut] = useState(false);

  useEffect(() => {
    let active = true;
    void api
      .get<CurrentUser>("/auth/me")
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .catch((requestError: unknown) => {
        if (!active) return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          void supabase.auth
            .signOut()
            .then(({ error: signOutError }) => {
              if (active && signOutError) setError(signOutError.message);
            })
            .catch((signOutError: unknown) => {
              if (active) {
                setError(
                  signOutError instanceof Error
                    ? signOutError.message
                    : "Unable to clear the expired session.",
                );
              }
            });
          return;
        }
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not verify the authenticated API request.",
        );
      });

    return () => {
      active = false;
    };
  }, [session?.access_token]);

  async function signOut() {
    setIsSigningOut(true);
    try {
      const { error: signOutError } = await supabase.auth.signOut();
      if (signOutError) {
        setError(signOutError.message);
        return;
      }
      navigate("/login", { replace: true });
    } catch (signOutError: unknown) {
      setError(
        signOutError instanceof Error
          ? signOutError.message
          : "Unable to sign out. Please try again.",
      );
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <main className="min-h-svh bg-muted/40 px-4 py-8">
      <header className="mx-auto flex max-w-5xl items-center justify-between border-b pb-5">
        <span className="font-semibold tracking-wide">Rag with Supabase </span>
        <Button
          type="button"
          variant="outline"
          disabled={isSigningOut}
          onClick={() => void signOut()}
        >
          {isSigningOut ? "Signing out..." : "Sign out"}
        </Button>
      </header>
      <section className="mx-auto mt-12 max-w-5xl rounded-xl border bg-card p-8 text-card-foreground shadow-sm">
        <p className="text-sm font-medium text-muted-foreground">
          AUTHENTICATION
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">
          You are signed in
        </h1>
        <p className="mt-2 text-muted-foreground">
          This page confirms that your Supabase session is being sent to FastAPI
          and verified by Supabase Auth.
        </p>
        {user ? (
          <dl className="mt-8 grid gap-4 border-t pt-6 sm:grid-cols-2">
            <div>
              <dt className="text-sm text-muted-foreground">Verified email</dt>
              <dd className="mt-1 font-medium">
                {user.email ?? "Not provided"}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">
                Supabase user ID
              </dt>
              <dd className="mt-1 break-all font-mono text-sm">{user.id}</dd>
            </div>
          </dl>
        ) : (
          <p
            aria-live="polite"
            className={`mt-8 rounded-md border p-3 text-sm ${error ? "border-destructive/30 bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground"}`}
          >
            {error ?? "Verifying your session with the backend..."}
          </p>
        )}
      </section>
    </main>
  );
}
