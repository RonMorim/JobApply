import { NextRequest, NextResponse } from 'next/server'
import { createClient }              from '@supabase/supabase-js'

const LOG = '[JobApply-Debug][check-email]'

const WHITELIST = new Set(['ronmorim98@gmail.com'])

function getAdminSupabase() {
  const url     = process.env.NEXT_PUBLIC_SUPABASE_URL  ?? ''
  const service = process.env.SUPABASE_SERVICE_ROLE_KEY ?? ''
  if (!url || !service) return null
  return createClient(url, service, { auth: { persistSession: false, autoRefreshToken: false } })
}

export async function POST(req: NextRequest) {
  let email: string
  try {
    const body = (await req.json()) as { email?: unknown }
    if (typeof body.email !== 'string' || !body.email.includes('@')) {
      return NextResponse.json({ error: 'Invalid email.' }, { status: 400 })
    }
    email = body.email.trim().toLowerCase()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON.' }, { status: 400 })
  }

  console.log(`${LOG} checking "${email}"`)

  if (WHITELIST.has(email)) {
    console.log(`${LOG} "${email}" → exists (whitelist)`)
    return NextResponse.json({ exists: true })
  }

  const supabase = getAdminSupabase()
  if (!supabase) {
    console.warn(`${LOG} admin client unavailable (SUPABASE_SERVICE_ROLE_KEY not set) — failing open`)
    return NextResponse.json({ exists: false })
  }

  try {
    const { data, error } = await supabase.auth.admin.listUsers({ perPage: 1000 })
    if (error) {
      console.error(`${LOG} listUsers error:`, error.message, '— failing open')
      return NextResponse.json({ exists: false })
    }
    const found = data.users.some(u => u.email?.toLowerCase() === email)
    console.log(`${LOG} "${email}" → exists: ${found} (scanned ${data.users.length} users)`)
    return NextResponse.json({ exists: found })
  } catch (err) {
    console.error(`${LOG} unexpected error:`, err, '— failing open')
    return NextResponse.json({ exists: false })
  }
}
