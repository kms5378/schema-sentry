ALTER TABLE public.purchases
    ALTER COLUMN amount TYPE character varying
    USING amount::character varying;
