'use client'
import { useCallback, useEffect, useState } from 'react'
import { fetchAgents, setAuthToken } from '@/lib/api'
import { useAuth }                   from '@/contexts/AuthContext'
import type { ApiAgentStatus }       from '@/lib/apiTypes'

// Static frontend: no automatic polling.
// Agent status is fetched ONCE on mount and when the user clicks Refresh.

interface UseAgentStatusResult {
  agents:  ApiAgentStatus[]
  loading: boolean
  error:   string | null
  refetch: () => void
}

export function useAgentStatus(): UseAgentStatusResult {
  const { session } = useAuth()

  const [agents,  setAgents]  = useState<ApiAgentStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!session?.access_token) return
    setAuthToken(session.access_token)
    setLoading(true)
    try {
      const data = await fetchAgents()
      setAgents(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch agent status')
    } finally {
      setLoading(false)
    }
  }, [session])

  // Fire once on mount (or when the session first becomes available).
  // No setInterval — the user triggers any subsequent refresh manually.
  useEffect(() => {
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { agents, loading, error, refetch: load }
}
