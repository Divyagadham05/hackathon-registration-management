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
