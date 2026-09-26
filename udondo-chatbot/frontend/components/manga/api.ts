// bot-api とのやり取り。形は docs の openapi.yaml に合わせる。

export type Lang = "ja" | "en" | "zh-Hans" | "zh-Hant" | "ko"
export type Emotion = "neutral" | "smile" | "think" | "surprise" | "sorry" | "serious"

export type Theme = {
  tokens: Record<string, string>
  variants: {
    header?: "band" | "plain"
    character?: "circle" | "panel"
    bot_message?: "rounded" | "manga"
    user_message?: "bubble" | "narration"
    quick_questions?: "list" | "grid"
    fallback_steps?: "list" | "panels"
  }
  decorations?: { speedlines?: boolean; screentone?: boolean }
}

export type ScreenConfig = {
  shop_name: string
  character_name: string
  languages: Lang[]
  features: { voice: boolean; avatar: boolean; image_input: boolean }
  greeting_title: Partial<Record<Lang, string>>
  greeting: Partial<Record<Lang, string>>
  quick_questions: Partial<Record<Lang, string[]>>
  sfx: Partial<Record<Lang, string>>
  fallback_intro: Partial<Record<Lang, string>>
  fallback_steps: Partial<Record<Lang, [string, string][]>>
  links: { line_help?: string }
  theme: Theme
  mode: string
}

export type Session = { session_id: string; remaining_turns: number; language: Lang; tenant: ScreenConfig }

export type Attachment = { kind: "image" | "video" | "link"; url: string; label?: string }

export type ChatEvent =
  | { name: "meta"; data: { turn_id: string; emotion: Emotion; refs: string[]; out_of_knowledge: boolean; attachments: Attachment[] } }
  | { name: "delta"; data: { text: string } }
  | { name: "safety"; data: { template_id: string; title: string; text: string; note: string } }
  | { name: "done"; data: { turn_id: string; remaining_turns: number } }
  | { name: "degraded"; data: { reason: string } }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

const base = (tenant: string) => `/api/v1/t/${tenant}`

async function asJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let code = "internal"
    let message = r.statusText
    try {
      const body = await r.json()
      code = body.code ?? body.detail?.code ?? code
      message = body.message ?? body.detail?.message ?? message
    } catch {}
    throw new ApiError(r.status, code, message)
  }
  return r.json() as Promise<T>
}

export async function getConfig(tenant: string): Promise<ScreenConfig> {
  return asJson(await fetch(`${base(tenant)}/config`))
}

export async function createSession(tenant: string, language: Lang): Promise<Session> {
  return asJson(
    await fetch(`${base(tenant)}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language }),
    }),
  )
}

export async function sendFeedback(tenant: string, sessionId: string, turnId: string, resolved: boolean) {
  await fetch(`${base(tenant)}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
    body: JSON.stringify({ turn_id: turnId, resolved }),
  })
}

// POST で SSE を受けるため、EventSource ではなく fetch のストリームを読む
export async function* streamChat(
  tenant: string,
  sessionId: string,
  message: string,
  language: Lang,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const r = await fetch(`${base(tenant)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
    body: JSON.stringify({ message, language }),
    signal,
  })
  if (!r.ok || !r.body) {
    await asJson(r)
    return
  }
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      let name = ""
      let data = ""
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7)
        else if (line.startsWith("data: ")) data += line.slice(6)
      }
      if (name && data) yield { name, data: JSON.parse(data) } as ChatEvent
    }
  }
}
