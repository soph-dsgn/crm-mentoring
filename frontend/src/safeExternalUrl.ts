/** Only web URLs are rendered as clickable links from persisted user data. */
export function safeExternalUrl(value: string | undefined): string | null {
  const candidate=value?.trim()
  if(!candidate)return null
  try {
    const parsed=new URL(candidate)
    return parsed.protocol==='https:'||parsed.protocol==='http:'?candidate:null
  } catch {
    return null
  }
}
