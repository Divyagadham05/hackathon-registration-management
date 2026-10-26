CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    email_sent INTEGER NOT NULL DEFAULT 0,
    email_notice TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
