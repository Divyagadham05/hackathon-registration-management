import React, { useEffect, useMemo, useState } from "react";

const DOMAINS = [
  "Artificial Intelligence",
  "Generative AI",
  "Web Development",
  "Data Science",
  "Cybersecurity",
  "Other",
];
const DEGREES = ["B.Tech", "B.Sc", "BCA", "MCA", "M.Tech", "Other"];
const STATUS_OPTIONS = ["Submitted", "Under Review", "Accepted", "Waitlisted", "Rejected"];

const emptyForm = (user) => ({
  full_name: user?.full_name || "",
  email: user?.email || "",
  mobile_number: "",
  date_of_birth: "",
  college_name: "",
  degree: "",
  department: "",
  year_of_study: "",
  college_location: "",
  participation_type: "Individual",
  team_name: "",
  team_size: 2,
  team_members: [{ name: "", email: "" }],
  team_leader: "",
  domain: "",
  technical_skills: "",
  project_title: "",
  project_idea: "",
  github_url: "",
  accept_rules: false,
  confirm_information: false,
});

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const payload = response.headers.get("content-type")?.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) {
    const error = new Error(payload?.error || "Something went wrong. Please try again.");
    error.fieldErrors = payload?.field_errors || {};
    error.status = response.status;
    throw error;
  }
  return payload;
}

function Icon({ name, size = 20 }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };
  const paths = {
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    spark: <><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    pin: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5" /><path d="M5 17v4h14v-4" /></>,
    logout: <><path d="M10 17l5-5-5-5" /><path d="M15 12H3" /><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></>,
  };
  return <svg {...common}>{paths[name] || paths.spark}</svg>;
}

function Field({ label, name, value, onChange, error, required, hint, as = "input", options, ...props }) {
  const Control = as;
  return (
    <label className={`field ${props.className || ""}`}>
      <span className="field-label">{label}{required && <span className="required"> *</span>}</span>
      {as === "select" ? (
        <select name={name} value={value} onChange={onChange} aria-invalid={Boolean(error)} {...props}>
          <option value="">Choose an option</option>
          {options.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ) : (
        <Control name={name} value={value} onChange={onChange} aria-invalid={Boolean(error)} {...props} />
      )}
      {hint && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}

function App() {
  const [user, setUser] = useState(null);
  const [csrf, setCsrf] = useState("");
  const [eventName, setEventName] = useState("Hack the Future");
  const [page, setPage] = useState("home");
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ full_name: "", email: "", password: "" });
  const [form, setForm] = useState(emptyForm(null));
  const [fieldErrors, setFieldErrors] = useState({});
  const [errorMessage, setErrorMessage] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [registration, setRegistration] = useState(null);
  const [emailSent, setEmailSent] = useState(true);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [adminRows, setAdminRows] = useState([]);
  const [adminFilters, setAdminFilters] = useState({ q: "", participation_type: "", domain: "" });
  const [selectedRegistration, setSelectedRegistration] = useState(null);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    Promise.all([request("/api/csrf"), request("/api/auth"), request("/api/config")])
      .then(([csrfResponse, authResponse, configResponse]) => {
        setCsrf(csrfResponse.csrf_token);
        setUser(authResponse.user);
        setEventName(configResponse.hackathon_name || "Hack the Future");
        setForm(emptyForm(authResponse.user));
      })
      .catch((error) => setErrorMessage(`Could not connect to the application: ${error.message}`))
      .finally(() => setAuthReady(true));
  }, []);

  const activeInitials = useMemo(() => user?.full_name?.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "H", [user]);

  function navigate(nextPage) {
    setErrorMessage("");
    setNotice("");
    setFieldErrors({});
    setMobileMenu(false);
    setPage(nextPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function updateForm(event) {
    const { name, value, type, checked } = event.target;
    setForm((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
    setFieldErrors((current) => ({ ...current, [name]: "" }));
  }

  function updateTeamSize(value) {
    const size = Number(value);
    setForm((current) => ({
      ...current,
      team_size: size,
      team_members: Array.from({ length: Math.max(0, size - 1) }, (_, index) => current.team_members[index] || { name: "", email: "" }),
    }));
    setFieldErrors((current) => ({ ...current, team_size: "", team_members: "" }));
  }

  function updateTeamMember(index, key, value) {
    setForm((current) => {
      const members = [...current.team_members];
      members[index] = { ...members[index], [key]: value };
      return { ...current, team_members: members };
    });
    setFieldErrors((current) => ({ ...current, team_members: "" }));
  }

  async function submitAuth(event) {
    event.preventDefault();
    setBusy(true);
    setErrorMessage("");
    setFieldErrors({});
    try {
      const response = await request(`/api/${authMode === "signup" ? "signup" : "login"}`, {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: JSON.stringify(authForm),
      });
      setUser(response.user);
      if (response.csrf_token) setCsrf(response.csrf_token);
      setForm(emptyForm(response.user));
      navigate("registration");
    } catch (error) {
      setErrorMessage(error.message);
      setFieldErrors(error.fieldErrors);
    } finally {
      setBusy(false);
    }
  }

  async function openRegistration() {
    if (!user) {
      setAuthMode("signup");
      navigate("auth");
      return;
    }
    setBusy(true);
    setErrorMessage("");
    try {
      const response = await request("/api/registration");
      if (response.registration) {
        setRegistration(response.registration);
        setEmailSent(Boolean(response.registration.email_sent));
        setNotice(response.registration.email_notice || "");
        navigate("success");
        setNotice(response.registration.email_notice || "");
      } else {
        setForm(emptyForm(user));
        navigate("registration");
      }
    } catch (error) {
      if (error.status === 401) {
        setAuthMode("signup");
        navigate("auth");
      } else {
        setErrorMessage(error.message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitRegistration(event) {
    event.preventDefault();
    setBusy(true);
    setErrorMessage("");
    setFieldErrors({});
    try {
      const response = await request("/api/registration", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: JSON.stringify(form),
      });
      setRegistration(response.registration);
      setEmailSent(response.email_sent);
      setNotice(response.notification || "");
      navigate("success");
      setNotice(response.notification || "");
    } catch (error) {
      setErrorMessage(error.message);
      setFieldErrors(error.fieldErrors);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setBusy(false);
    }
  }

  async function showMyRegistration() {
    setBusy(true);
    setErrorMessage("");
    try {
      const response = await request("/api/registration");
      setRegistration(response.registration);
      navigate("my-registration");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    try {
      const response = await request("/api/logout", { method: "POST", headers: { "X-CSRF-Token": csrf } });
      if (response.ok) {
        setUser(null);
        setRegistration(null);
        const token = await request("/api/csrf");
        setCsrf(token.csrf_token);
        navigate("home");
      }
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadAdmin() {
    if (!user?.is_admin) {
      setErrorMessage("Administrator access is required.");
      return;
    }
    setBusy(true);
    try {
      const params = new URLSearchParams(Object.entries(adminFilters).filter(([, value]) => value));
      const response = await request(`/api/admin/registrations?${params}`);
      setAdminRows(response.registrations);
      navigate("admin");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshAdmin(filters = adminFilters) {
    try {
      const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      const response = await request(`/api/admin/registrations?${params}`);
      setAdminRows(response.registrations);
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  async function changeStatus(row, status) {
    try {
      await request(`/api/admin/registrations/${encodeURIComponent(row.registration_id)}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrf },
        body: JSON.stringify({ status }),
      });
      await refreshAdmin();
      if (selectedRegistration?.registration_id === row.registration_id) {
        setSelectedRegistration({ ...selectedRegistration, status });
      }
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  function startSignup() {
    setAuthMode("signup");
    navigate("auth");
  }

  if (!authReady) {
    return <div className="boot-screen"><span className="loader" /> Preparing your launchpad...</div>;
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a href="#home" className="brand" onClick={(event) => { event.preventDefault(); navigate("home"); }}>
          <span className="brand-mark"><Icon name="spark" size={20} /></span>
          <span>hack<span className="brand-light">thefuture</span></span>
        </a>
        <button className="mobile-menu-button" aria-label="Toggle navigation" onClick={() => setMobileMenu(!mobileMenu)}><Icon name={mobileMenu ? "close" : "menu"} /></button>
        <nav className={mobileMenu ? "main-nav nav-open" : "main-nav"}>
          <a href="#about" onClick={(event) => { event.preventDefault(); navigate("home"); document.getElementById("about")?.scrollIntoView({ behavior: "smooth" }); }}>About</a>
          <a href="#tracks" onClick={(event) => { event.preventDefault(); navigate("home"); document.getElementById("tracks")?.scrollIntoView({ behavior: "smooth" }); }}>Tracks</a>
          {user && <button className="nav-link" onClick={showMyRegistration}>My registration</button>}
          {user?.is_admin && <button className="nav-link" onClick={loadAdmin}>Organizer</button>}
          {user ? (
            <div className="account-actions">
              <span className="avatar" title={user.full_name}>{activeInitials}</span>
              <button className="text-button" onClick={logout} disabled={busy}><Icon name="logout" size={16} /> Log out</button>
            </div>
          ) : (
            <button className="text-button" onClick={() => { setAuthMode("login"); navigate("auth"); }}>Log in</button>
          )}
          <button className="button button-small button-primary nav-register" onClick={openRegistration} disabled={busy}>
            {user ? "Register" : "Sign up"} <Icon name="arrow" size={16} />
          </button>
        </nav>
      </header>

      {errorMessage && <div className="global-alert" role="alert"><span>{errorMessage}</span><button onClick={() => setErrorMessage("")} aria-label="Dismiss">×</button></div>}

      {page === "home" && (
        <main>
          <section className="hero">
            <div className="hero-orb orb-one" /><div className="hero-orb orb-two" />
            <div className="hero-content">
              <div className="eyebrow"><span className="live-dot" /> REGISTRATION IS OPEN</div>
              <h1>Build what's<br />next. <span>Together.</span></h1>
              <p className="hero-copy">One weekend. Big ideas. Real impact. Join the brightest student builders for a 24-hour sprint to shape a better tomorrow.</p>
              <div className="hero-actions">
                <button className="button button-primary button-large" onClick={openRegistration} disabled={busy}>Register for free <Icon name="arrow" size={18} /></button>
                <button className="button button-quiet button-large" onClick={() => document.getElementById("about")?.scrollIntoView({ behavior: "smooth" })}>Explore the event <span className="play-icon">↓</span></button>
              </div>
              <div className="hero-meta">
                <div className="meta-item"><span className="meta-icon"><Icon name="clock" size={18} /></span><span><b>24 hours</b><small>of building</small></span></div>
                <div className="meta-item"><span className="meta-icon"><Icon name="pin" size={18} /></span><span><b>Innovation Hub</b><small>Campus auditorium</small></span></div>
                <div className="meta-item"><span className="meta-icon"><Icon name="spark" size={18} /></span><span><b>All skill levels</b><small>Bring your curiosity</small></span></div>
              </div>
            </div>
            <div className="hero-art" aria-hidden="true">
              <div className="art-grid" />
              <div className="orbit orbit-a" /><div className="orbit orbit-b" />
              <div className="art-card card-back"><span className="code-bracket">&lt;/&gt;</span><span>MAKE IT<br />MATTER</span></div>
              <div className="art-card card-front"><div className="art-card-top"><span className="tiny-dot" /><span className="tiny-dot" /><span className="tiny-dot" /></div><div className="art-spark"><Icon name="spark" size={48} /></div><span className="art-caption">IDEAS INTO IMPACT</span><div className="art-lines"><i /><i /><i /></div></div>
              <div className="floating-tag tag-top"><span className="tag-icon">✳</span> CREATE</div>
              <div className="floating-tag tag-bottom"><span className="tag-icon">↗</span> COLLABORATE</div>
              <div className="art-star star-a">✦</div><div className="art-star star-b">✧</div>
            </div>
            <div className="hero-bottom-line"><span>MAKE SOMETHING THAT MATTERS</span><span>01 — 02 NOV 2026</span></div>
          </section>

          <section className="event-strip" id="about">
            <div><span className="strip-number">01</span><span><small>WHEN</small><b>November 1–2, 2026</b></span></div>
            <div><span className="strip-number">02</span><span><small>WHERE</small><b>Innovation Hub · Main Campus</b></span></div>
            <div><span className="strip-number">03</span><span><small>WHO</small><b>Students. Dreamers. Doers.</b></span></div>
            <button className="strip-link" onClick={openRegistration}>Save your spot <Icon name="arrow" size={17} /></button>
          </section>

          <section className="section tracks-section" id="tracks">
            <div className="section-heading">
              <div><span className="section-kicker">FIND YOUR FRONTIER</span><h2>Pick a problem.<br /><span>Make a difference.</span></h2></div>
              <p>Explore a challenge that excites you, bring your own idea, and team up with people who think differently.</p>
            </div>
            <div className="track-grid">
              {[
                ["01", "Artificial Intelligence", "Build intelligent tools that make everyday life better.", "track-purple"],
                ["02", "Generative AI", "Reimagine how we create, learn, and work.", "track-orange"],
                ["03", "Web Development", "Create digital experiences that bring people together.", "track-blue"],
                ["04", "Data Science", "Find the insight that changes everything.", "track-green"],
                ["05", "Cybersecurity", "Make the connected world a safer place.", "track-pink"],
                ["06", "Open Innovation", "Got an idea that doesn't fit a box? This one's yours.", "track-yellow"],
              ].map(([number, title, description, color]) => (
                <article className={`track-card ${color}`} key={title}>
                  <div className="track-card-top"><span>{number} / TRACK</span><span className="track-arrow"><Icon name="arrow" size={17} /></span></div>
                  <div className="track-decoration"><Icon name="spark" size={28} /></div>
                  <h3>{title}</h3><p>{description}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="cta-band">
            <div className="cta-pattern" />
            <div><span className="section-kicker">YOUR NEXT BIG THING STARTS HERE</span><h2>Got an idea?<br /><span>Give it a weekend.</span></h2></div>
            <button className="button button-dark button-large" onClick={openRegistration}>Join the hackathon <Icon name="arrow" size={18} /></button>
          </section>
        </main>
      )}

      {page === "auth" && (
        <main className="auth-page">
          <div className="auth-visual">
            <div className="auth-visual-content"><span className="section-kicker">YOUR IDEA HAS A HOME</span><h1>Big things<br />start with<br /><span>showing up.</span></h1><p>Find your people. Build your thing. Make the kind of weekend you’ll still be talking about next year.</p><div className="auth-visual-bottom"><Icon name="spark" size={19} /> NOVEMBER 1–2, 2026 <span>·</span> OPEN TO ALL STUDENTS</div></div>
            <div className="auth-visual-shape shape-a" /><div className="auth-visual-shape shape-b" />
          </div>
          <div className="auth-form-wrap">
            <div className="auth-form">
              <span className="section-kicker">{authMode === "signup" ? "CREATE YOUR ACCOUNT" : "GOOD TO SEE YOU AGAIN"}</span>
              <h2>{authMode === "signup" ? "Join the build." : "Welcome back."}</h2>
              <p className="auth-intro">{authMode === "signup" ? "Make an account to register for the hackathon." : "Log in to continue your hackathon journey."}</p>
              <form onSubmit={submitAuth} noValidate>
                {authMode === "signup" && <Field label="Full name" name="full_name" autoComplete="name" placeholder="Your name" value={authForm.full_name} onChange={(e) => setAuthForm({ ...authForm, full_name: e.target.value })} error={fieldErrors.full_name} required />}
                <Field label="Email address" name="email" type="email" autoComplete="email" placeholder="you@college.edu" value={authForm.email} onChange={(e) => setAuthForm({ ...authForm, email: e.target.value })} error={fieldErrors.email} required />
                <Field label="Password" name="password" type="password" autoComplete={authMode === "signup" ? "new-password" : "current-password"} placeholder={authMode === "signup" ? "At least 10 characters" : "Enter your password"} value={authForm.password} onChange={(e) => setAuthForm({ ...authForm, password: e.target.value })} error={fieldErrors.password} required />
                <button className="button button-primary button-full button-large" disabled={busy}>{busy ? <><span className="loader loader-small" /> Please wait...</> : authMode === "signup" ? <>Create account <Icon name="arrow" size={18} /></> : <>Log in <Icon name="arrow" size={18} /></>}</button>
              </form>
              <p className="auth-switch">{authMode === "signup" ? "Already have an account?" : "New to the hackathon?"} <button onClick={() => { setAuthMode(authMode === "signup" ? "login" : "signup"); setErrorMessage(""); setFieldErrors({}); }}>{authMode === "signup" ? "Log in" : "Create an account"}</button></p>
              <div className="secure-note"><Icon name="lock" size={15} /> Your account details are securely protected.</div>
            </div>
          </div>
        </main>
      )}

      {page === "registration" && user && (
        <main className="form-page">
          <div className="page-topline"><span className="section-kicker">YOUR HACKATHON JOURNEY</span><span className="step-indicator">01 <i /> 01</span></div>
          <div className="form-heading"><h1>Make it <span>official.</span></h1><p>A few details help us make this an unforgettable weekend. You can finish in about 5 minutes.</p></div>
          <div className="form-layout">
            <form className="registration-form" onSubmit={submitRegistration} noValidate>
              {errorMessage && <div className="inline-alert" role="alert">{errorMessage}</div>}
              <section className="form-section">
                <div className="form-section-heading"><span className="form-section-number">01</span><div><h2>About you</h2><p>First, let's get to know you.</p></div></div>
                <div className="field-grid">
                  <Field label="Full name" name="full_name" value={form.full_name} onChange={updateForm} error={fieldErrors.full_name} placeholder="As you'd like it on your badge" required maxLength={100} />
                  <Field label="Email address" name="email" type="email" value={user.email} readOnly hint="Linked to your account" />
                  <Field label="Mobile number" name="mobile_number" type="tel" value={form.mobile_number} onChange={updateForm} error={fieldErrors.mobile_number} placeholder="+91 98765 43210" required />
                  <Field label="Date of birth" name="date_of_birth" type="date" value={form.date_of_birth} onChange={updateForm} error={fieldErrors.date_of_birth} />
                </div>
              </section>
              <section className="form-section">
                <div className="form-section-heading"><span className="form-section-number">02</span><div><h2>Your campus</h2><p>Tell us where you're learning and growing.</p></div></div>
                <div className="field-grid">
                  <Field label="College / university" name="college_name" value={form.college_name} onChange={updateForm} error={fieldErrors.college_name} placeholder="Institution name" required />
                  <Field label="Degree" name="degree" as="select" options={DEGREES} value={form.degree} onChange={updateForm} error={fieldErrors.degree} required />
                  <Field label="Department / branch" name="department" value={form.department} onChange={updateForm} error={fieldErrors.department} placeholder="e.g. Computer Science" required />
                  <Field label="Year of study / graduation" name="year_of_study" value={form.year_of_study} onChange={updateForm} error={fieldErrors.year_of_study} placeholder="e.g. 3rd year or 2027" required />
                  <Field className="field-wide" label="College location" name="college_location" value={form.college_location} onChange={updateForm} error={fieldErrors.college_location} placeholder="City, State" required />
                </div>
              </section>
              <section className="form-section">
                <div className="form-section-heading"><span className="form-section-number">03</span><div><h2>Your crew</h2><p>Hack solo or bring your favorite collaborators.</p></div></div>
                <div className="choice-cards">
                  {["Individual", "Team"].map((type) => <label className={`choice-card ${form.participation_type === type ? "choice-selected" : ""}`} key={type}>
                    <input type="radio" name="participation_type" value={type} checked={form.participation_type === type} onChange={updateForm} />
                    <span className="choice-radio" /><span><b>{type === "Individual" ? "Flying solo" : "Team up"}</b><small>{type === "Individual" ? "I'll take on the challenge myself" : "Better ideas happen together"}</small></span>
                  </label>)}
                </div>
                {fieldErrors.participation_type && <span className="field-error">{fieldErrors.participation_type}</span>}
                {form.participation_type === "Team" && <div className="team-fields">
                  <div className="field-grid">
                    <Field label="Team name" name="team_name" value={form.team_name} onChange={updateForm} error={fieldErrors.team_name} placeholder="Give your team a name" required />
                    <Field label="Team size (including you)" name="team_size" as="select" options={["2", "3", "4", "5"]} value={String(form.team_size)} onChange={(event) => updateTeamSize(event.target.value)} error={fieldErrors.team_size} required />
                    <Field className="field-wide" label="Team leader name" name="team_leader" value={form.team_leader} onChange={updateForm} error={fieldErrors.team_leader} placeholder="Who will be the main contact?" required />
                  </div>
                  <div className="team-member-heading"><b>Other team members</b><span>{form.team_size - 1} {form.team_size - 1 === 1 ? "person" : "people"}</span></div>
                  {form.team_members.map((member, index) => <div className="field-grid member-row" key={index}>
                    <Field label={`Member ${index + 1} name`} value={member.name} onChange={(event) => updateTeamMember(index, "name", event.target.value)} placeholder="Full name" required />
                    <Field label={`Member ${index + 1} email`} type="email" value={member.email} onChange={(event) => updateTeamMember(index, "email", event.target.value)} placeholder="name@college.edu" required />
                  </div>)}
                  {fieldErrors.team_members && <span className="field-error">{fieldErrors.team_members}</span>}
                </div>}
              </section>
              <section className="form-section">
                <div className="form-section-heading"><span className="form-section-number">04</span><div><h2>What you'll build</h2><p>Every great project starts with a spark.</p></div></div>
                <div className="field-grid">
                  <Field label="Hackathon domain" name="domain" as="select" options={DOMAINS} value={form.domain} onChange={updateForm} error={fieldErrors.domain} required />
                  <Field label="Project title" name="project_title" value={form.project_title} onChange={updateForm} error={fieldErrors.project_title} placeholder="Optional — ideas can evolve" />
                  <Field className="field-wide" label="Programming languages & technical skills" name="technical_skills" value={form.technical_skills} onChange={updateForm} error={fieldErrors.technical_skills} placeholder="e.g. Python, React, Figma, machine learning" required />
                  <Field className="field-wide" label="Project idea / problem statement" name="project_idea" as="textarea" rows="4" value={form.project_idea} onChange={updateForm} error={fieldErrors.project_idea} placeholder="What problem would you love to solve? It's okay if your idea is still taking shape." required maxLength={2000} />
                  <Field className="field-wide" label="GitHub profile" name="github_url" type="url" value={form.github_url} onChange={updateForm} error={fieldErrors.github_url} placeholder="https://github.com/yourname" />
                </div>
              </section>
              <section className="form-section declaration-section">
                <div className="form-section-heading"><span className="form-section-number">05</span><div><h2>One last thing</h2><p>Ready to make it official?</p></div></div>
                <label className="check-row"><input type="checkbox" name="accept_rules" checked={form.accept_rules} onChange={updateForm} /><span className="custom-check"><Icon name="check" size={14} /></span><span>I agree to the hackathon <a href="#rules" onClick={(event) => { event.preventDefault(); setNotice("Hackathon rules: participants must follow event staff instructions, respect others, and submit original work created during the event."); }}>rules and terms</a>. <b>*</b></span></label>
                {fieldErrors.accept_rules && <span className="field-error check-error">{fieldErrors.accept_rules}</span>}
                <label className="check-row"><input type="checkbox" name="confirm_information" checked={form.confirm_information} onChange={updateForm} /><span className="custom-check"><Icon name="check" size={14} /></span><span>I confirm the information I've provided is accurate. <b>*</b></span></label>
                {fieldErrors.confirm_information && <span className="field-error check-error">{fieldErrors.confirm_information}</span>}
              </section>
              <div className="form-submit-row"><p><span>*</span> Required fields</p><button className="button button-primary button-large" disabled={busy}>{busy ? <><span className="loader loader-small" /> Submitting...</> : <>Submit registration <Icon name="arrow" size={18} /></>}</button></div>
            </form>
            <aside className="form-aside">
              <div className="aside-card aside-event"><span className="section-kicker">THE COUNTDOWN IS ON</span><div className="aside-date">01<span>—</span>02<small>NOV 2026</small></div><h3>{eventName}</h3><p>Innovation Hub<br />Main Campus</p><div className="aside-rule" /><div className="aside-line"><Icon name="clock" size={17} /> 24 hours of making</div><div className="aside-line"><Icon name="user" size={17} /> Open to all students</div></div>
              <div className="aside-card aside-tip"><div className="tip-icon"><Icon name="spark" size={18} /></div><h3>Good to know</h3><p>Your project idea doesn't need to be perfect. We want to hear what you're curious about — you can figure out the rest at the hackathon.</p></div>
              <div className="help-note"><Icon name="mail" size={17} /><span>Need a hand? <a href="mailto:organizers@example.com">Contact the organizers</a></span></div>
            </aside>
          </div>
        </main>
      )}

      {page === "success" && registration && (
        <main className="success-page">
          <div className="success-card"><div className="success-icon"><Icon name="check" size={34} /></div><span className="section-kicker">YOU'RE IN</span><h1>It's official.<br /><span>Let's build.</span></h1>
            <p className="success-message">Congratulations! Your hackathon registration has been completed successfully.</p>
            <div className="registration-id"><span>YOUR REGISTRATION ID</span><b>{registration.registration_id}</b></div>
            {emailSent ? <p className="email-note"><Icon name="mail" size={18} /> A confirmation email has been sent to <b>{registration.email}</b>. Please check your inbox for further details.</p> : <p className="email-warning"><Icon name="mail" size={18} /> {notice || "Your registration is saved, but the confirmation email could not be delivered."}</p>}
            <div className="success-actions"><button className="button button-primary button-large" onClick={showMyRegistration}>View my registration <Icon name="arrow" size={18} /></button><button className="button button-outline button-large" onClick={() => navigate("home")}>Back to home</button></div>
            <div className="success-confetti confetti-one">✦</div><div className="success-confetti confetti-two">✳</div>
          </div>
        </main>
      )}

      {page === "my-registration" && user && (
        <main className="dashboard-page">
          <div className="page-topline"><span className="section-kicker">YOUR HACKATHON JOURNEY</span><span className={`status-pill status-${(registration?.status || "none").toLowerCase().replace(/\s/g, "-")}`}>{registration?.status || "Not registered"}</span></div>
          {!registration ? <div className="empty-state"><div className="empty-icon"><Icon name="spark" size={28} /></div><span className="section-kicker">YOUR NEXT CHAPTER</span><h1>Not registered <span>yet.</span></h1><p>Your spot is waiting. Tell us a little about yourself and you're in.</p><button className="button button-primary button-large" onClick={() => { setForm(emptyForm(user)); navigate("registration"); }}>Start registration <Icon name="arrow" size={18} /></button></div> :
            <div className="registration-summary"><div className="summary-heading"><div><span className="section-kicker">REGISTRATION CONFIRMED</span><h1>Your place is <span>saved.</span></h1></div><span className="summary-check"><Icon name="check" size={22} /></span></div><div className="summary-id"><span>REGISTRATION ID</span><b>{registration.registration_id}</b><small>Keep this ID for future reference.</small></div>
              <div className="summary-grid">{[
                ["Participant", registration.full_name], ["Email", registration.email], ["Mobile", registration.mobile_number], ["College", registration.college_name], ["Degree & branch", `${registration.degree} · ${registration.department}`], ["Year", registration.year_of_study], ["Participation", registration.participation_type], ["Team", registration.team_name || "—"], ["Domain", registration.domain], ["Project", registration.project_title || "To be decided"], ["Status", registration.status], ["Registered", new Date(registration.created_at + "Z").toLocaleString()],
              ].map(([label, value]) => <div className="summary-item" key={label}><span>{label}</span><b>{value}</b></div>)}</div>
              {registration.project_idea && <div className="summary-idea"><span>PROJECT IDEA</span><p>{registration.project_idea}</p></div>}
              <button className="button button-outline button-large" onClick={() => navigate("home")}>Back to home</button>
            </div>}
        </main>
      )}

      {page === "admin" && user?.is_admin && (
        <main className="admin-page">
          <div className="page-topline"><span className="section-kicker">ORGANIZER CONSOLE</span><a className="button button-outline button-small" href="/api/admin/export.csv"><Icon name="download" size={16} /> Export CSV</a></div>
          <div className="admin-title"><div><h1>Participant <span>directory.</span></h1><p>Review registrations and keep the event moving.</p></div><div className="admin-count"><b>{adminRows.length}</b><span>registrations</span></div></div>
          <div className="admin-filters">
            <label className="search-box"><span className="search-symbol">⌕</span><input aria-label="Search registrations" placeholder="Search name, email, college or ID..." value={adminFilters.q} onChange={(event) => { const next = { ...adminFilters, q: event.target.value }; setAdminFilters(next); refreshAdmin(next); }} /></label>
            <select aria-label="Filter by participation type" value={adminFilters.participation_type} onChange={(event) => { const next = { ...adminFilters, participation_type: event.target.value }; setAdminFilters(next); refreshAdmin(next); }}><option value="">All participation</option><option>Individual</option><option>Team</option></select>
            <select aria-label="Filter by domain" value={adminFilters.domain} onChange={(event) => { const next = { ...adminFilters, domain: event.target.value }; setAdminFilters(next); refreshAdmin(next); }}><option value="">All domains</option>{DOMAINS.map((domain) => <option key={domain}>{domain}</option>)}</select>
          </div>
          <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>PARTICIPANT</th><th>COLLEGE</th><th>TYPE</th><th>DOMAIN</th><th>STATUS</th><th></th></tr></thead><tbody>
            {adminRows.map((row) => <tr key={row.registration_id}><td><button className="participant-link" onClick={() => setSelectedRegistration(row)}><b>{row.full_name}</b><span>{row.email}</span></button></td><td>{row.college_name}</td><td>{row.participation_type}</td><td>{row.domain}</td><td><select className="status-select" aria-label={`Status for ${row.full_name}`} value={row.status} onChange={(event) => changeStatus(row, event.target.value)}>{STATUS_OPTIONS.map((status) => <option key={status}>{status}</option>)}</select></td><td><button className="details-button" onClick={() => setSelectedRegistration(row)}>Details <Icon name="arrow" size={15} /></button></td></tr>)}
            {adminRows.length === 0 && <tr><td colSpan="6" className="table-empty">No registrations match those filters.</td></tr>}
          </tbody></table></div>
        </main>
      )}

      {selectedRegistration && page === "admin" && <div className="modal-backdrop" onClick={() => setSelectedRegistration(null)}><section className="details-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onClick={(event) => event.stopPropagation()}><button className="modal-close" aria-label="Close details" onClick={() => setSelectedRegistration(null)}><Icon name="close" /></button><span className="section-kicker">PARTICIPANT DETAILS</span><h2 id="detail-title">{selectedRegistration.full_name}</h2><p className="modal-id">{selectedRegistration.registration_id} · {selectedRegistration.email}</p><div className="modal-details">{Object.entries({ College: selectedRegistration.college_name, Mobile: selectedRegistration.mobile_number, Degree: selectedRegistration.degree, Department: selectedRegistration.department, "Year of study": selectedRegistration.year_of_study, "College location": selectedRegistration.college_location, Participation: selectedRegistration.participation_type, "Team name": selectedRegistration.team_name || "—", "Team leader": selectedRegistration.team_leader || "—", Domain: selectedRegistration.domain, "Technical skills": selectedRegistration.technical_skills, "Project title": selectedRegistration.project_title || "—", "Project idea": selectedRegistration.project_idea, GitHub: selectedRegistration.github_url || "—" }).map(([label, value]) => <div key={label}><span>{label}</span><p>{value}</p></div>)}</div>{selectedRegistration.team_members?.length > 0 && <div className="modal-team"><b>Team members</b>{selectedRegistration.team_members.map((member) => <p key={member.email}>{member.name} · {member.email}</p>)}</div>}<label className="modal-status">Registration status<select value={selectedRegistration.status} onChange={(event) => changeStatus(selectedRegistration, event.target.value)}>{STATUS_OPTIONS.map((status) => <option key={status}>{status}</option>)}</select></label></section></div>}

      <footer className="site-footer"><a href="#home" className="brand footer-brand" onClick={(event) => { event.preventDefault(); navigate("home"); }}><span className="brand-mark"><Icon name="spark" size={18} /></span><span>hack<span className="brand-light">thefuture</span></span></a><span>MADE FOR THE BUILDERS OF TOMORROW.</span><span>© 2026 {eventName}</span></footer>
      {notice && page === "registration" && <div className="toast-note"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
    </div>
  );
}

export default App;
