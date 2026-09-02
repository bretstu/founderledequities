-- The page's own count of real visits and clicks. One row per event.
-- Applied once:  wrangler d1 execute fle-hits --remote --file=ops/hits-schema.sql
CREATE TABLE IF NOT EXISTS hits (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      TEXT NOT NULL,        -- ISO time the batch arrived
  day     TEXT NOT NULL,        -- YYYY-MM-DD, for grouping
  vid     TEXT NOT NULL,        -- visitor id the browser keeps for itself (random, no PII)
  sid     TEXT NOT NULL,        -- session id, one per tab
  kind    TEXT NOT NULL,        -- view | section | open | click | sort | day | window | table | switch
  name    TEXT NOT NULL,        -- what: page, board, activity, drawer, gopro, chip, ...
  detail  TEXT,                 -- which: a ticker, a chip label, a column, a date
  path    TEXT,                 -- the address as loaded, with ?day= and #section
  ref     TEXT,                 -- document.referrer on the page view
  country TEXT,                 -- the country Cloudflare attaches; nothing finer
  pro     INTEGER DEFAULT 0,    -- signed in as a subscriber at the time
  device  TEXT                  -- desktop | mobile
);
CREATE INDEX IF NOT EXISTS hits_day ON hits(day);
CREATE INDEX IF NOT EXISTS hits_sid ON hits(sid);
CREATE INDEX IF NOT EXISTS hits_kind ON hits(kind, name);
