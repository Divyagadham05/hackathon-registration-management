CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS registrations (
    id SERIAL PRIMARY KEY,
    registration_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    mobile_number TEXT NOT NULL,
    date_of_birth TEXT,
    college_name TEXT NOT NULL,
    degree TEXT NOT NULL,
    department TEXT NOT NULL,
    year_of_study TEXT NOT NULL,
    college_location TEXT NOT NULL,
    participation_type TEXT NOT NULL CHECK (participation_type IN ('Individual', 'Team')),
    team_name TEXT,
    team_size INTEGER,
    team_members TEXT NOT NULL DEFAULT '[]',
    team_leader TEXT,
    domain TEXT NOT NULL,
    technical_skills TEXT NOT NULL,
    project_title TEXT,
    project_idea TEXT NOT NULL,
    github_url TEXT,
    status TEXT NOT NULL DEFAULT 'Submitted',
    email_sent BOOLEAN NOT NULL DEFAULT FALSE,
    email_notice TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS food_facilities (
    id SERIAL PRIMARY KEY,
    facility_type TEXT NOT NULL UNIQUE,
    timing TEXT,
    start_time TEXT,
    end_time TEXT,
    items TEXT,
    availability TEXT NOT NULL DEFAULT 'Not Announced Yet',
    price_status TEXT NOT NULL DEFAULT 'Not Announced Yet',
    charges TEXT,
    location TEXT,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tracks (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    number TEXT NOT NULL,
    title TEXT NOT NULL UNIQUE,
    tagline TEXT NOT NULL,
    description TEXT NOT NULL,
    color_class TEXT NOT NULL,
    problem_statements TEXT NOT NULL DEFAULT '[]',
    suggested_tech TEXT NOT NULL DEFAULT '[]',
    resources TEXT NOT NULL DEFAULT '[]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    registration_domain TEXT NOT NULL DEFAULT 'Other',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('faq', 'track', 'food', 'custom')),
    source_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    published BOOLEAN NOT NULL DEFAULT TRUE,
    origin TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    embedding TEXT,
    content_hash TEXT,
    embedding_model TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    normalized_question TEXT NOT NULL UNIQUE,
    times_asked INTEGER NOT NULL DEFAULT 1,
    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved'))
);
