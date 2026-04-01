-- Supabase schema (MVP): Products as Single Source of Truth
-- Target: PostgreSQL (Supabase) + RLS enabled
-- Notes:
-- - Uses auth.uid() for multi-tenant (per user) ownership
-- - Stores marketplace tokens encrypted via pgcrypto (optional but recommended)

create extension if not exists pgcrypto;

-- ===== Enums =====
do $$
begin
  if not exists (select 1 from pg_type where typname = 'product_status') then
    create type public.product_status as enum ('draft', 'ready', 'published', 'paused', 'error', 'archived');
  end if;
  if not exists (select 1 from pg_type where typname = 'marketplace_platform') then
    create type public.marketplace_platform as enum ('meli', 'shopee');
  end if;
  if not exists (select 1 from pg_type where typname = 'listing_status') then
    create type public.listing_status as enum ('draft', 'queued', 'published', 'paused', 'closed', 'error', 'unknown');
  end if;
end$$;

-- ===== Products (SSOT) =====
create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),

  title text not null,
  description text not null,
  price numeric(12,2) not null check (price >= 0),
  stock integer not null default 0 check (stock >= 0),
  category_id text null,
  images text[] not null default '{}'::text[],
  status public.product_status not null default 'draft',

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists products_owner_id_idx on public.products(owner_id);
create index if not exists products_status_idx on public.products(status);

-- Keep updated_at in sync
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_products_updated_at on public.products;
create trigger trg_products_updated_at
before update on public.products
for each row execute function public.set_updated_at();

-- ===== Platform listings mapping =====
-- Links internal product to marketplace listing IDs to support later PUT/PATCH updates.
create table if not exists public.platform_listings (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),

  product_id uuid not null references public.products(id) on delete cascade,
  platform public.marketplace_platform not null,
  external_listing_id text not null,

  status public.listing_status not null default 'unknown',
  last_sync_at timestamptz null,
  last_error text null,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (owner_id, platform, external_listing_id),
  unique (owner_id, product_id, platform)
);

create index if not exists platform_listings_product_id_idx on public.platform_listings(product_id);
create index if not exists platform_listings_platform_idx on public.platform_listings(platform);

drop trigger if exists trg_platform_listings_updated_at on public.platform_listings;
create trigger trg_platform_listings_updated_at
before update on public.platform_listings
for each row execute function public.set_updated_at();

-- ===== Marketplace OAuth tokens (encrypted at rest) =====
-- Store tokens per user and platform. Access token refresh is handled by backend.
create table if not exists public.marketplace_tokens (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  platform public.marketplace_platform not null,

  -- Encrypted fields stored as base64 text (server encrypts/decrypts)
  access_token_enc text not null,
  refresh_token_enc text null,

  token_type text null,
  scope text null,
  expires_at timestamptz null,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (owner_id, platform)
);

drop trigger if exists trg_marketplace_tokens_updated_at on public.marketplace_tokens;
create trigger trg_marketplace_tokens_updated_at
before update on public.marketplace_tokens
for each row execute function public.set_updated_at();

-- ===== RLS =====
alter table public.products enable row level security;
alter table public.platform_listings enable row level security;
alter table public.marketplace_tokens enable row level security;

-- Products policies
drop policy if exists "products_select_own" on public.products;
create policy "products_select_own"
on public.products for select
using (owner_id = auth.uid());

drop policy if exists "products_insert_own" on public.products;
create policy "products_insert_own"
on public.products for insert
with check (owner_id = auth.uid());

drop policy if exists "products_update_own" on public.products;
create policy "products_update_own"
on public.products for update
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

drop policy if exists "products_delete_own" on public.products;
create policy "products_delete_own"
on public.products for delete
using (owner_id = auth.uid());

-- Platform listings policies
drop policy if exists "platform_listings_select_own" on public.platform_listings;
create policy "platform_listings_select_own"
on public.platform_listings for select
using (owner_id = auth.uid());

drop policy if exists "platform_listings_insert_own" on public.platform_listings;
create policy "platform_listings_insert_own"
on public.platform_listings for insert
with check (owner_id = auth.uid());

drop policy if exists "platform_listings_update_own" on public.platform_listings;
create policy "platform_listings_update_own"
on public.platform_listings for update
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

drop policy if exists "platform_listings_delete_own" on public.platform_listings;
create policy "platform_listings_delete_own"
on public.platform_listings for delete
using (owner_id = auth.uid());

-- Marketplace tokens policies (backend should use Service Role key; client should typically not touch this)
drop policy if exists "marketplace_tokens_select_own" on public.marketplace_tokens;
create policy "marketplace_tokens_select_own"
on public.marketplace_tokens for select
using (owner_id = auth.uid());

drop policy if exists "marketplace_tokens_insert_own" on public.marketplace_tokens;
create policy "marketplace_tokens_insert_own"
on public.marketplace_tokens for insert
with check (owner_id = auth.uid());

drop policy if exists "marketplace_tokens_update_own" on public.marketplace_tokens;
create policy "marketplace_tokens_update_own"
on public.marketplace_tokens for update
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

drop policy if exists "marketplace_tokens_delete_own" on public.marketplace_tokens;
create policy "marketplace_tokens_delete_own"
on public.marketplace_tokens for delete
using (owner_id = auth.uid());

