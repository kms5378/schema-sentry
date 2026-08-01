ALTER TABLE public.purchases
    ALTER COLUMN amount TYPE numeric(12,2)
    USING amount::numeric;
