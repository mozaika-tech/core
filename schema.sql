-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- Events table (DO NOT ADD OR REMOVE COLUMNS)
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    discovered_at TIMESTAMPTZ NOT NULL,
    posted_at TIMESTAMPTZ,

    -- Timing
    occurs_from TIMESTAMPTZ,
    occurs_to TIMESTAMPTZ,
    deadline_at TIMESTAMPTZ,

    -- Content
    language TEXT NOT NULL,               -- ISO-639-1: 'uk', 'en', 'pl'
    title TEXT NOT NULL,                  -- Max 120 chars
    raw_text TEXT NOT NULL,

    -- Metadata
    organizer TEXT,
    city TEXT,
    country TEXT,                         -- ISO-3166-1 alpha-2: 'UA', 'PL'
    is_remote BOOLEAN,
    apply_url TEXT,

    -- Search
    embedding VECTOR(384) NOT NULL,       -- multilingual-e5-small, L2-normalized

    -- Status
    status TEXT NOT NULL DEFAULT 'active',

    -- Deduplication
    dedupe_fingerprint TEXT UNIQUE NOT NULL,

    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Categories (controlled vocabulary)
CREATE TABLE categories (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Event-Category junction
CREATE TABLE event_categories (
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, category_id)
);

-- Indexes
CREATE INDEX idx_events_posted_at ON events(posted_at);
CREATE INDEX idx_events_city ON events(city);
CREATE INDEX idx_events_language ON events(language);
CREATE INDEX idx_events_country ON events(country);
CREATE INDEX idx_events_is_remote ON events(is_remote);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_deadline ON events(deadline_at) WHERE deadline_at IS NOT NULL;
CREATE INDEX idx_events_occurs_from ON events(occurs_from) WHERE occurs_from IS NOT NULL;

CREATE INDEX idx_events_embedding ON events
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_event_categories_category ON event_categories(category_id);
CREATE INDEX idx_event_categories_event ON event_categories(event_id);

-- Seed data
INSERT INTO categories (slug, name) VALUES
('internship', 'Стажування'),
('volunteering', 'Волонтерство'),
('grant', 'Гранти'),
('workshop', 'Воркшопи'),
('conference', 'Конференції'),
('job', 'Робота'),
('course', 'Курси'),
('competition', 'Конкурси'),
('hackathon', 'Хакатони'),
('meetup', 'Зустрічі');