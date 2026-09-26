-- 接客 bot の見本の無料版で使うテーブル。Supabase の SQL エディタで一度だけ流す。
-- 既存の knowledge_base テーブルはそのまま知識として読む。
-- RLS を有効にし、ポリシーは置かない。サーバーはサービスロールの鍵で読み書きし、ブラウザからは読めない。

create table if not exists bot_sessions (
  id text primary key,
  tenant_id text not null,
  created_at timestamptz not null default now(),
  last_active_at timestamptz not null default now(),
  language text not null,
  turn_count integer not null default 0,
  ip_hash text not null
);

create table if not exists bot_turns (
  id text primary key,
  tenant_id text not null,
  session_id text not null references bot_sessions(id) on delete cascade,
  seq integer not null,
  created_at timestamptz not null default now(),
  mode text not null default 'text',
  language text not null,
  user_text_masked text not null,
  bot_text text not null,
  emotion text,
  refs jsonb not null default '[]',
  out_of_knowledge boolean not null default false,
  safety_id text,
  resolved boolean,
  latency_first_ms integer,
  latency_total_ms integer,
  error text
);
create index if not exists bot_turns_session_seq on bot_turns (session_id, seq);

create table if not exists bot_usage (
  id bigserial primary key,
  tenant_id text not null,
  session_id text not null,
  turn_id text not null,
  kind text not null,
  provider text not null,
  model text not null,
  input_tokens integer not null default 0,
  cached_tokens integer not null default 0,
  output_tokens integer not null default 0,
  thinking_tokens integer not null default 0,
  cost_usd numeric(12, 6) not null default 0,
  cost_jpy numeric(12, 4) not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists bot_daily_costs (
  tenant_id text not null,
  day date not null,
  cost_jpy numeric(12, 4) not null default 0,
  conversations integer not null default 0,
  turns integer not null default 0,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, day)
);

create table if not exists bot_unanswered (
  id text primary key,
  tenant_id text not null,
  session_id text not null,
  turn_id text not null,
  question_masked text not null,
  language text not null,
  reason text not null,
  status text not null default 'open',
  created_at timestamptz not null default now()
);

create table if not exists bot_rate_limits (
  tenant_id text not null,
  key text not null,
  count integer not null default 0,
  created_at timestamptz not null default now(),
  primary key (tenant_id, key)
);

alter table bot_sessions enable row level security;
alter table bot_turns enable row level security;
alter table bot_usage enable row level security;
alter table bot_daily_costs enable row level security;
alter table bot_unanswered enable row level security;
alter table bot_rate_limits enable row level security;

create or replace function bot_add_daily_cost(
  p_tenant_id text, p_day date, p_jpy numeric, p_conversations integer, p_turns integer
) returns void language sql as $$
  insert into bot_daily_costs (tenant_id, day, cost_jpy, conversations, turns)
  values (p_tenant_id, p_day, p_jpy, p_conversations, p_turns)
  on conflict (tenant_id, day) do update set
    cost_jpy = bot_daily_costs.cost_jpy + excluded.cost_jpy,
    conversations = bot_daily_costs.conversations + excluded.conversations,
    turns = bot_daily_costs.turns + excluded.turns,
    updated_at = now();
$$;

create or replace function bot_hit(p_tenant_id text, p_key text) returns integer language sql as $$
  insert into bot_rate_limits (tenant_id, key, count) values (p_tenant_id, p_key, 1)
  on conflict (tenant_id, key) do update set count = bot_rate_limits.count + 1
  returning count;
$$;

-- レート制限の古い行は、1日以上前のものを消してよい。
-- delete from bot_rate_limits where created_at < now() - interval '1 day';
