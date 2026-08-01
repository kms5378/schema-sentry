CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE public.players (
    player_id bigint PRIMARY KEY,
    nickname character varying(50) NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE public.matches (
    match_id bigint PRIMARY KEY,
    region character varying(20) NOT NULL,
    started_at timestamptz NOT NULL
);

CREATE TABLE public.sessions (
    session_id bigint PRIMARY KEY,
    player_id bigint NOT NULL REFERENCES public.players(player_id),
    started_at timestamptz NOT NULL,
    ended_at timestamptz
);

CREATE TABLE public.purchases (
    purchase_id bigint PRIMARY KEY,
    player_id bigint NOT NULL REFERENCES public.players(player_id),
    purchased_at timestamptz NOT NULL,
    amount numeric(12,2) NOT NULL
);

CREATE TABLE mart.daily_revenue (
    date date PRIMARY KEY,
    revenue numeric(18,2) NOT NULL
);

INSERT INTO public.players VALUES
    (1, 'alpha', '2026-01-01T00:00:00Z'),
    (2, 'bravo', '2026-01-01T00:00:00Z');

INSERT INTO public.purchases VALUES
    (101, 1, '2026-08-01T01:00:00Z', 1200.00),
    (102, 2, '2026-08-01T02:00:00Z', 800.00),
    (103, 1, '2026-08-02T01:00:00Z', 500.00);
