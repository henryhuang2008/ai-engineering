function requiredEnv(name: string, value: string | undefined): string {
  const normalized = value?.trim()
  if (!normalized) {
    throw new Error(`Missing required environment variable: ${name}`)
  }
  return normalized
}

function requiredUrl(name: string, value: string | undefined): string {
  const normalized = requiredEnv(name, value)
  try {
    return new URL(normalized).toString().replace(/\/+$/, '')
  } catch {
    throw new Error(`${name} must be a valid absolute URL`)
  }
}

export const env = {
  apiBaseUrl: requiredUrl('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL),
  supabaseUrl: requiredUrl('VITE_SUPABASE_URL', import.meta.env.VITE_SUPABASE_URL),
  supabaseAnonKey: requiredEnv(
    'VITE_SUPABASE_ANON_KEY',
    import.meta.env.VITE_SUPABASE_ANON_KEY,
  ),
}
