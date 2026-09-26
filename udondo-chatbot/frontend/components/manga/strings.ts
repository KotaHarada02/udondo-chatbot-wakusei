// 画面の部品の文言。店ごとの文言はサーバーの copy.yaml から受け取る。
// 中国語と韓国語は下訳であり、確認が要る。
import type { Lang, ScreenConfig } from "./api"

export const LANG_LABEL: Record<Lang, string> = {
  ja: "日本語",
  en: "English",
  "zh-Hans": "简体中文",
  "zh-Hant": "繁體中文",
  ko: "한국어",
}

type Strings = {
  aiBadge: string
  placeholder: string
  send: string
  resolved: string
  notResolved: string
  thanks: string
  lineHelp: string
  lineNote: string
  remaining: (n: number) => string
  notice: string
  retry: string
  close: string
  textSize: string
  language: string
  quickTitle: string
  links: Record<string, string>
  limitReached: string
  errors: Record<string, string>
}

const ja: Strings = {
  aiBadge: "AI が案内中",
  placeholder: "ウドンドに話しかける",
  send: "送る",
  resolved: "解決した",
  notResolved: "まだ困っている",
  thanks: "ありがとな",
  lineHelp: "公式 LINE のヘルプを開く",
  lineNote: "店からの返事には時間がかかることがあります",
  remaining: (n) => `この会話で質問できるのは、あと${n}回です`,
  notice: "答えているのは AI です。質問は案内の改善のため保存します。名前や電話番号は入力しないでください。",
  retry: "もう一度つなぐ",
  close: "閉じる",
  textSize: "文字の大きさを変える",
  language: "言語を変える",
  quickTitle: "よくある質問",
  links: { line: "公式 LINE を開く", map: "地図を開く", video: "動画を見る", manga: "漫画を読む", link: "リンクを開く" },
  limitReached: "この会話の質問の回数が上限に達しました。公式 LINE のヘルプをご利用ください。",
  errors: {
    rate_limited: "少し時間をおいてから、もう一度送ってください。",
    unauthorized: "しばらく時間がたったので、つなぎ直しました。もう一度送ってください。",
  },
}

const en: Strings = {
  aiBadge: "AI guide",
  placeholder: "Ask Udondo",
  send: "Send",
  resolved: "Solved",
  notResolved: "Still stuck",
  thanks: "Thanks!",
  lineHelp: "Open official LINE help",
  lineNote: "Replies from the shop may take time",
  remaining: (n) => `${n} questions left in this chat`,
  notice: "An AI is answering. Questions are stored to improve the guide. Please do not enter your name or phone number.",
  retry: "Reconnect",
  close: "Close",
  textSize: "Change text size",
  language: "Change language",
  quickTitle: "Common questions",
  links: { line: "Open official LINE", map: "Open map", video: "Watch video", manga: "Read the manga", link: "Open link" },
  limitReached: "You have reached the question limit for this chat. Please use the official LINE help.",
  errors: {
    rate_limited: "Please wait a moment and try again.",
    unauthorized: "The connection was renewed. Please send your question again.",
  },
}

const zhHans: Strings = {
  ...en,
  aiBadge: "AI 向导",
  placeholder: "向乌冬多提问",
  send: "发送",
  resolved: "已解决",
  notResolved: "还有问题",
  thanks: "谢谢",
  lineHelp: "打开官方 LINE 帮助",
  lineNote: "店铺回复可能需要一些时间",
  remaining: (n) => `本次对话还可以提问 ${n} 次`,
  notice: "回答的是 AI。为改进服务会保存提问内容。请不要输入姓名或电话号码。",
  retry: "重新连接",
  close: "关闭",
  quickTitle: "常见问题",
  links: { line: "打开官方 LINE", map: "打开地图", video: "观看视频", manga: "阅读漫画", link: "打开链接" },
}

const zhHant: Strings = {
  ...en,
  aiBadge: "AI 嚮導",
  placeholder: "向烏冬多提問",
  send: "傳送",
  resolved: "已解決",
  notResolved: "還有問題",
  thanks: "謝謝",
  lineHelp: "開啟官方 LINE 說明",
  lineNote: "店鋪回覆可能需要一些時間",
  remaining: (n) => `本次對話還可以提問 ${n} 次`,
  notice: "回答的是 AI。為改進服務會保存提問內容。請不要輸入姓名或電話號碼。",
  retry: "重新連線",
  close: "關閉",
  quickTitle: "常見問題",
  links: { line: "開啟官方 LINE", map: "開啟地圖", video: "觀看影片", manga: "閱讀漫畫", link: "開啟連結" },
}

const ko: Strings = {
  ...en,
  aiBadge: "AI 안내",
  placeholder: "우돈도에게 물어보기",
  send: "보내기",
  resolved: "해결됐어요",
  notResolved: "아직 곤란해요",
  thanks: "고마워",
  lineHelp: "공식 LINE 도움말 열기",
  lineNote: "가게의 답장은 시간이 걸릴 수 있습니다",
  remaining: (n) => `이 대화에서 ${n}번 더 질문할 수 있습니다`,
  notice: "AI가 답하고 있습니다. 질문은 안내 개선을 위해 저장됩니다. 이름이나 전화번호는 입력하지 마세요.",
  retry: "다시 연결",
  close: "닫기",
  quickTitle: "자주 묻는 질문",
  links: { line: "공식 LINE 열기", map: "지도 열기", video: "동영상 보기", manga: "만화 읽기", link: "링크 열기" },
}

export const STRINGS: Record<Lang, Strings> = { ja, en, "zh-Hans": zhHans, "zh-Hant": zhHant, ko }

export function pick<T>(m: Partial<Record<Lang, T>> | undefined, lang: Lang, fallback: T): T {
  return m?.[lang] ?? m?.ja ?? fallback
}

// サーバーに届かないときでも出せる、最小限の縮退画面の中身
export const OFFLINE_CONFIG: ScreenConfig = {
  shop_name: "惑星のウドンド",
  character_name: "ウドンド",
  languages: ["ja", "en"],
  features: { voice: false, avatar: false, image_input: false },
  greeting_title: { ja: "よく来たな、旅人" },
  greeting: { ja: "" },
  quick_questions: {},
  sfx: {},
  fallback_intro: {
    ja: "すまん、いまは質問に答えられないんだ。代わりに店の使い方をまとめておいたぞ。",
    en: "Sorry, I can't answer right now. Here is how to use the shop instead.",
  },
  fallback_steps: {
    ja: [
      ["入店", "店内の QR から公式 LINE を友だち追加"],
      ["購入", "LINE で PayPay かカード。現金はオレンジ色のポストへ。おつりは出ない"],
      ["作る", "麺は左の茹で麺機で10分。スープは右で袋のまま4分"],
      ["食べる", "トッピングは自由。壁と青いファイルにレシピ"],
      ["片付け", "テーブルを拭き、食器は奥の下膳棚へ"],
      ["退店", "ビンと缶は持ち帰り。忘れ物を確かめる"],
    ],
  },
  links: { line_help: "https://line.me/R/ti/p/@771ypyse" },
  theme: {
    tokens: {
      paper: "#ffffff", ink: "#111111", spot: "#ffd23f", soft: "#4a4a4a", tone: "#c9c9c9",
      alert: "#c8231b", alert_bg: "#fff0ee", border_width: "3px", radius_bubble: "26px", radius_control: "0px",
    },
    variants: { header: "band", character: "panel", bot_message: "manga", user_message: "narration", quick_questions: "grid", fallback_steps: "panels" },
    decorations: { speedlines: true, screentone: true },
  },
  mode: "offline",
}
