"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { CSSProperties, FormEvent } from "react"

import {
  ApiError,
  createSession,
  getConfig,
  sendFeedback,
  streamChat,
  type Attachment,
  type Emotion,
  type Lang,
  type ScreenConfig,
} from "./api"
import { LANG_LABEL, OFFLINE_CONFIG, STRINGS, pick } from "./strings"

const TENANT = process.env.NEXT_PUBLIC_TENANT_ID ?? "udondo"
const CHARACTER_IMAGE = "/images/image.png"

type BotMessage = {
  id: string
  role: "bot"
  text: string
  emotion: Emotion
  pending: boolean
  ook: boolean
  attachments: Attachment[]
  turnId?: string
  feedback?: "yes" | "no"
  safety?: { title: string; text: string; note: string }
}
type UserMessage = { id: string; role: "user"; text: string }
type Message = BotMessage | UserMessage

function detectLang(): Lang {
  if (typeof navigator === "undefined") return "ja"
  const l = navigator.language.toLowerCase()
  if (l.startsWith("ja")) return "ja"
  if (l.startsWith("ko")) return "ko"
  if (l.startsWith("zh")) return l.includes("tw") || l.includes("hk") || l.includes("hant") ? "zh-Hant" : "zh-Hans"
  return "en"
}

function themeStyle(cfg: ScreenConfig): CSSProperties {
  const t = cfg.theme.tokens
  const vars: Record<string, string> = {
    "--paper": t.paper, "--ink": t.ink, "--spot": t.spot, "--soft": t.soft, "--tone": t.tone,
    "--alert": t.alert, "--alert-bg": t.alert_bg, "--bw": t.border_width,
    "--r-bubble": t.radius_bubble, "--r-control": t.radius_control,
  }
  return Object.fromEntries(Object.entries(vars).filter(([, v]) => v)) as CSSProperties
}

let seq = 0
const uid = () => `m${Date.now()}-${seq++}`

export function MangaApp() {
  const [lang, setLang] = useState<Lang>("ja")
  const [cfg, setCfg] = useState<ScreenConfig | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [remaining, setRemaining] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [fallback, setFallback] = useState(false)
  const [large, setLarge] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [viewer, setViewer] = useState<Attachment | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const s = STRINGS[lang]
  const config = cfg ?? OFFLINE_CONFIG
  const variants = config.theme.variants

  const connect = useCallback(async (language: Lang) => {
    try {
      const sess = await createSession(TENANT, language)
      setCfg(sess.tenant)
      setSessionId(sess.session_id)
      setRemaining(sess.remaining_turns)
      setFallback(false)
      return sess.session_id
    } catch {
      try {
        setCfg(await getConfig(TENANT))
      } catch {}
      setFallback(true)
      return null
    }
  }, [])

  useEffect(() => {
    const l = detectLang()
    setLang(l)
    try {
      setLarge(localStorage.getItem("mg-large") === "1")
    } catch {}
    void connect(l)
  }, [connect])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [messages])

  const patchBot = (id: string, fn: (m: BotMessage) => BotMessage) =>
    setMessages((ms) => ms.map((m) => (m.id === id && m.role === "bot" ? fn(m) : m)))

  async function ask(text: string, retried = false) {
    const question = text.trim()
    if (!question || busy) return
    let sid = sessionId
    if (!sid) {
      sid = await connect(lang)
      if (!sid) return
    }
    setBusy(true)
    setNotice(null)
    const botId = uid()
    if (!retried) setMessages((ms) => [...ms, { id: uid(), role: "user", text: question }])
    setMessages((ms) => [...ms, { id: botId, role: "bot", text: "", emotion: "think", pending: true, ook: false, attachments: [] }])
    try {
      for await (const ev of streamChat(TENANT, sid, question, lang)) {
        if (ev.name === "meta") {
          patchBot(botId, (m) => ({ ...m, emotion: ev.data.emotion, ook: ev.data.out_of_knowledge, attachments: ev.data.attachments, turnId: ev.data.turn_id }))
        } else if (ev.name === "delta") {
          patchBot(botId, (m) => ({ ...m, text: m.text + ev.data.text }))
        } else if (ev.name === "safety") {
          patchBot(botId, (m) => ({ ...m, safety: ev.data, text: "" }))
        } else if (ev.name === "done") {
          const extra = ev.data.attachments ?? []
          patchBot(botId, (m) => ({
            ...m,
            pending: false,
            turnId: ev.data.turn_id,
            attachments: [...m.attachments, ...extra.filter((a) => !m.attachments.some((x) => x.url === a.url))],
          }))
          setRemaining(ev.data.remaining_turns)
        } else if (ev.name === "degraded") {
          setMessages((ms) => ms.filter((m) => m.id !== botId))
          if (ev.data.reason === "session_limit") {
            setRemaining(0)
            setNotice(s.limitReached)
          } else {
            setFallback(true)
          }
        }
      }
    } catch (e) {
      setMessages((ms) => ms.filter((m) => m.id !== botId))
      if (e instanceof ApiError && e.status === 401 && !retried) {
        setSessionId(null)
        setBusy(false)
        const fresh = await connect(lang)
        if (fresh) {
          setSessionId(fresh)
          setNotice(s.errors.unauthorized)
        }
        return
      }
      if (e instanceof ApiError && e.status === 429) setNotice(s.errors.rate_limited)
      else setFallback(true)
    } finally {
      patchBot(botId, (m) => ({ ...m, pending: false }))
      setBusy(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const t = input
    setInput("")
    void ask(t)
  }

  function feedback(m: BotMessage, resolved: boolean) {
    if (!sessionId || !m.turnId) return
    patchBot(m.id, (x) => ({ ...x, feedback: resolved ? "yes" : "no" }))
    void sendFeedback(TENANT, sessionId, m.turnId, resolved)
  }

  function toggleLarge() {
    setLarge((v) => {
      try {
        localStorage.setItem("mg-large", v ? "0" : "1")
      } catch {}
      return !v
    })
  }

  const lineUrl = config.links.line_help ?? "#"
  const canAsk = !fallback && remaining !== 0

  return (
    <div className={`mg-root${large ? " mg-large" : ""}`} style={themeStyle(config)}>
      <div className="mg-phone">
        <header className={`mg-header${variants.header === "plain" ? " mg-plain" : ""}`}>
          <span className="mg-header-title mg-display">{config.character_name}</span>
          <span className="mg-badge">{s.aiBadge}</span>
          <button type="button" className="mg-hbtn" aria-label={s.textSize} aria-pressed={large} onClick={toggleLarge}>
            <TextSizeIcon />
          </button>
          <label className="mg-hbtn">
            <GlobeIcon />
            <span className="mg-sr">{s.language}</span>
            <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label={s.language}>
              {(config.languages.length ? config.languages : (["ja", "en"] as Lang[])).map((l) => (
                <option key={l} value={l}>{LANG_LABEL[l]}</option>
              ))}
            </select>
          </label>
        </header>

        {fallback ? (
          <Fallback config={config} lang={lang} lineUrl={lineUrl} onRetry={() => void connect(lang)} />
        ) : (
          <main className="mg-main">
            {messages.length === 0 && <Home config={config} lang={lang} onQuick={(q) => void ask(q)} />}
            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className={`mg-narration${variants.user_message === "bubble" ? " mg-bubble-user" : ""}`}>{m.text}</div>
              ) : (
                <BotRow key={m.id} m={m} lang={lang} variant={variants.bot_message} lineUrl={lineUrl}
                  onFeedback={(r) => feedback(m, r)} onOpen={setViewer} />
              ),
            )}
            {notice && <p className="mg-note" role="status">{notice}</p>}
            {remaining !== null && remaining > 0 && remaining <= 5 && <p className="mg-note">{s.remaining(remaining)}</p>}
            <div ref={bottomRef} />
          </main>
        )}

        {!fallback && (
          <form className="mg-input" onSubmit={onSubmit}>
            <label htmlFor="mg-q" className="mg-sr">{s.placeholder}</label>
            <input id="mg-q" type="text" value={input} maxLength={300} placeholder={s.placeholder}
              onChange={(e) => setInput(e.target.value)} disabled={!canAsk} autoComplete="off" />
            <button type="submit" aria-label={s.send} disabled={busy || !canAsk || !input.trim()}>
              <SendIcon />
            </button>
          </form>
        )}
      </div>
      {viewer && <Viewer a={viewer} closeLabel={s.close} onClose={() => setViewer(null)} />}
    </div>
  )
}

function Home({ config, lang, onQuick }: { config: ScreenConfig; lang: Lang; onQuick: (q: string) => void }) {
  const s = STRINGS[lang]
  const v = config.theme.variants
  const sfx = config.sfx?.[lang]
  const quick = pick(config.quick_questions, lang, [] as string[])
  return (
    <>
      <div className="mg-hero">
        <div className={`mg-panel${config.theme.decorations?.speedlines ? " mg-speedlines" : ""}`}>
          <img src={CHARACTER_IMAGE} alt={config.character_name} />
        </div>
        {sfx ? <div className={`mg-sfx mg-display${config.theme.decorations?.screentone ? " mg-tone" : ""}`} aria-hidden="true">{sfx}</div> : <div />}
      </div>
      <div style={{ paddingTop: 8 }}>
        <div className={`mg-bubble mg-${v.bot_message ?? "rounded"}`}>
          <p>
            <span className="mg-display mg-greet-title">{pick(config.greeting_title, lang, "")}</span>
            <br />
            {pick(config.greeting, lang, "")}
          </p>
        </div>
      </div>
      {quick.length > 0 && (
        <section aria-label={s.quickTitle} className={`mg-quick${v.quick_questions === "list" ? " mg-list" : ""}`}>
          {quick.map((q) => (
            <button key={q} type="button" onClick={() => onQuick(q)}>{q}</button>
          ))}
        </section>
      )}
      <p className="mg-note">{s.notice}</p>
    </>
  )
}

function BotRow({ m, lang, variant, lineUrl, onFeedback, onOpen }: {
  m: BotMessage; lang: Lang; variant?: string; lineUrl: string
  onFeedback: (resolved: boolean) => void; onOpen: (a: Attachment) => void
}) {
  const s = STRINGS[lang]
  if (m.safety) {
    return (
      <section className="mg-safety" aria-label={m.safety.title} role="alert">
        <div className="mg-safety-title mg-display"><AlertIcon />{m.safety.title}</div>
        <p>{m.safety.text}</p>
        <span className="mg-note">{m.safety.note}</span>
      </section>
    )
  }
  return (
    <div className="mg-row">
      <div className="mg-mini mg-tone"><img src={CHARACTER_IMAGE} alt="" /></div>
      <div className="mg-row-body">
        <div className={`mg-bubble mg-${variant ?? "rounded"}`} aria-live="polite" aria-busy={m.pending}>
          {m.text ? <p>{m.text}</p> : <span className="mg-typing" aria-label="考えている"><span /><span /><span /></span>}
          {!m.pending && m.attachments.map((a) =>
            a.kind === "image" ? (
              <button key={a.url} type="button" className="mg-link-card" onClick={() => onOpen(a)}>{a.label ?? "画像を見る"}</button>
            ) : (
              <a key={a.url} className="mg-link-card" href={a.url} target="_blank" rel="noopener noreferrer">
                {s.links[a.label ?? (a.kind === "video" ? "video" : "link")] ?? s.links.link}<ExternalIcon />
              </a>
            ),
          )}
          {!m.pending && m.ook && (
            <>
              <a className="mg-cta" href={lineUrl} target="_blank" rel="noopener noreferrer">{s.lineHelp}<ExternalIcon /></a>
              <span className="mg-note">{s.lineNote}</span>
            </>
          )}
          {!m.pending && m.turnId && m.text && (
            m.feedback ? (
              <span className="mg-note">{s.thanks}</span>
            ) : (
              <div className="mg-chip-row">
                <button type="button" className="mg-chip" onClick={() => onFeedback(true)}>{s.resolved}</button>
                <button type="button" className="mg-chip" onClick={() => onFeedback(false)}>{s.notResolved}</button>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}

function Fallback({ config, lang, lineUrl, onRetry }: { config: ScreenConfig; lang: Lang; lineUrl: string; onRetry: () => void }) {
  const s = STRINGS[lang]
  const steps = pick(config.fallback_steps, lang, pick(OFFLINE_CONFIG.fallback_steps, "ja", []))
  return (
    <main className="mg-main">
      <div className="mg-row">
        <div className="mg-mini mg-tone"><img src={CHARACTER_IMAGE} alt="" /></div>
        <div className="mg-row-body">
          <div className={`mg-bubble mg-${config.theme.variants.bot_message ?? "rounded"}`}>
            <p>{pick(config.fallback_intro, lang, pick(OFFLINE_CONFIG.fallback_intro, lang, ""))}</p>
          </div>
        </div>
      </div>
      <ol className={`mg-steps${config.theme.variants.fallback_steps === "list" ? " mg-list" : ""}`}>
        {steps.map(([title, detail], i) => (
          <li key={title}>
            <b><span className="mg-display mg-step-no">{i + 1}</span>{title}</b>
            <span>{detail}</span>
          </li>
        ))}
      </ol>
      <a className="mg-cta" href={lineUrl} target="_blank" rel="noopener noreferrer">{s.lineHelp}<ExternalIcon /></a>
      <span className="mg-note">{s.lineNote}</span>
      <button type="button" className="mg-cta mg-dark" onClick={onRetry}><RefreshIcon />{s.retry}</button>
    </main>
  )
}

function Viewer({ a, closeLabel, onClose }: { a: Attachment; closeLabel: string; onClose: () => void }) {
  return (
    <div className="mg-viewer" role="dialog" aria-modal="true" aria-label={a.label}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="mg-display">{a.label}</span>
        <button type="button" className="mg-hbtn" style={{ color: "#fff" }} aria-label={closeLabel} onClick={onClose}><CloseIcon /></button>
      </div>
      <img src={a.url} alt={a.label ?? ""} />
    </div>
  )
}

const svgProps = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2.2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true }
const SendIcon = () => <svg {...svgProps}><path d="M4 12l16-8l-6 16l-3-7z" /></svg>
const GlobeIcon = () => <svg {...svgProps} width={16} height={16}><circle cx="12" cy="12" r="9" /><path d="M3 12h18" /><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z" /></svg>
const TextSizeIcon = () => <svg {...svgProps}><path d="M4 7V5h11v2" /><path d="M9.5 5v14" /><path d="M7 19h5" /><path d="M15 12v-1.5h6V12" /><path d="M18 10.5V19" /></svg>
const ExternalIcon = () => <svg {...svgProps} width={16} height={16}><path d="M14 4h6v6" /><path d="M20 4l-9 9" /><path d="M18 14v5H5V6h5" /></svg>
const AlertIcon = () => <svg {...svgProps} width={24} height={24}><path d="M12 3l10 18H2z" /><path d="M12 10v5" /><path d="M12 18h.01" /></svg>
const RefreshIcon = () => <svg {...svgProps} width={18} height={18}><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 5v6h-6" /></svg>
const CloseIcon = () => <svg {...svgProps} width={22} height={22}><path d="M6 6l12 12" /><path d="M18 6L6 18" /></svg>
