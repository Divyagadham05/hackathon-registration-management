import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import Chatbot from "./Chatbot.jsx";

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
const FOOD_FACILITY_TYPES = [
  "Breakfast",
  "Lunch",
  "Evening Snacks",
  "Dinner",
  "Tea Stall",
  "Coffee Stall",
  "Other Beverages",
  "Drinking Water",
];
const OFFICIAL_FOOD_SCHEDULE = [
  { facility_type: "Breakfast", icon: "🌅", details: "8:00 AM to 9:00 AM" },
  { facility_type: "Lunch", icon: "☀️", details: "1:00 PM to 2:00 PM" },
  { facility_type: "Evening Snacks", icon: "☕", details: "4:00 PM to 4:30 PM" },
  { facility_type: "Dinner", icon: "🌙", details: "7:30 PM to 8:30 PM" },
  { facility_type: "Drinking Water", icon: "💧", details: "Available throughout the event" },
];
const FOOD_AVAILABILITY_OPTIONS = ["Available", "Unavailable", "Not Announced Yet"];
const FOOD_PRICE_OPTIONS = ["Free", "Paid", "Not Announced Yet"];

function getTrackSlugFromHash() {
  const match = window.location.hash.match(/^#\/tracks\/([^/]+)$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

const emptyFoodForm = () => ({
  facility_type: "",
  timing: "",
  start_time: "",
  end_time: "",
  items: "",
  availability: "Not Announced Yet",
  price_status: "Not Announced Yet",
  charges: "",
  location: "",
  published: false,
});

const emptyTrackForm = () => ({
  slug: "",
  number: "",
  title: "",
  tagline: "",
  description: "",
  color_class: "track-purple",
  problem_statements: "",
  suggested_tech: "",
  resources: "",
  sort_order: 0,
  published: false,
  registration_domain: "Other",
});

function formatFoodTime(value) {
  if (!value) return "";
  const [hours, minutes] = value.split(":").map(Number);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes)) return value;
  return `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${hours < 12 ? "AM" : "PM"}`;
}

function displayFoodTiming(facility) {
  const startTime = facility.start_time === "Not Announced Yet" ? "" : facility.start_time;
  const endTime = facility.end_time === "Not Announced Yet" ? "" : facility.end_time;
  if (startTime && endTime) {
    return `${formatFoodTime(startTime)} – ${formatFoodTime(endTime)}`;
  }
  if (startTime) return formatFoodTime(startTime);
  if (endTime) return formatFoodTime(endTime);
  return facility.timing || "Not Announced Yet";
}

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
  let response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The assistant is taking longer than usual to respond. Please retry in a moment.");
    }
    throw new Error("Could not reach the application server. Check your connection and try again.");
  }

  let payload = null;
  if (response.headers.get("content-type")?.includes("application/json")) {
    try {
      payload = await response.json();
    } catch {
      throw new Error(`The application server returned an invalid response (HTTP ${response.status}).`);
    }
  }
  if (!response.ok) {
    const message = payload?.error || (
      [502, 503, 504].includes(response.status)
        ? "The backend is starting up or temporarily unavailable. Please retry in a few seconds."
        : response.status === 404
          ? "The API route was not found. Check that the backend is deployed and API_BACKEND_URL is correct."
          : `The request failed (HTTP ${response.status}). Please try again.`
    );
    const error = new Error(message);
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
  const [page, setPage] = useState(() => getTrackSlugFromHash() ? "track" : "home");
  const [trackSlug, setTrackSlug] = useState(getTrackSlugFromHash);
  const [tracks, setTracks] = useState([]);
  const [tracksLoading, setTracksLoading] = useState(true);
  const [tracksError, setTracksError] = useState("");
  const [activeTrack, setActiveTrack] = useState(null);
  const [trackDetailState, setTrackDetailState] = useState("idle");
  const [trackDetailError, setTrackDetailError] = useState("");
  const [pendingRegistrationDomain, setPendingRegistrationDomain] = useState("");
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
  const [adminSection, setAdminSection] = useState("registrations");
  const [foodFacilities, setFoodFacilities] = useState([]);
  const [foodForm, setFoodForm] = useState(emptyFoodForm);
  const [editingFoodId, setEditingFoodId] = useState(null);
  const [savingFood, setSavingFood] = useState(false);
  const [adminTracks, setAdminTracks] = useState([]);
  const [trackForm, setTrackForm] = useState(emptyTrackForm);
  const [editingTrackId, setEditingTrackId] = useState(null);
  const [savingTrack, setSavingTrack] = useState(false);
  const [selectedRegistration, setSelectedRegistration] = useState(null);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState([]);
  const [knowledgeGaps, setKnowledgeGaps] = useState([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState(null);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [knowledgeError, setKnowledgeError] = useState("");
  const [knowledgeSearch, setKnowledgeSearch] = useState("");
  const [knowledgeOrigin, setKnowledgeOrigin] = useState("");
  const [knowledgeForm, setKnowledgeForm] = useState({ title: "", content: "", published: true });
  const [editingKnowledgeId, setEditingKnowledgeId] = useState(null);
  const [savingKnowledge, setSavingKnowledge] = useState(false);
  const [knowledgeFieldErrors, setKnowledgeFieldErrors] = useState({});
  const [knowledgeMessage, setKnowledgeMessage] = useState("");
  const [knowledgeChunksDocument, setKnowledgeChunksDocument] = useState(null);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeMode, setKnowledgeMode] = useState("hybrid");
  const [knowledgeResults, setKnowledgeResults] = useState([]);
  const [knowledgeSearchLoading, setKnowledgeSearchLoading] = useState(false);
  const [knowledgeSearchError, setKnowledgeSearchError] = useState("");
  const [knowledgeReindexing, setKnowledgeReindexing] = useState(false);
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

  useEffect(() => {
    let active = true;
    request("/api/tracks")
      .then((response) => {
        if (active) setTracks(response.tracks);
      })
      .catch((error) => {
        if (active) setTracksError(error.message);
      })
      .finally(() => {
        if (active) setTracksLoading(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const handleHashChange = () => {
      const slug = getTrackSlugFromHash();
      if (slug) {
        setTrackSlug(slug);
        setPage("track");
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      setTrackSlug(null);
      if (window.location.hash === "#tracks" || window.location.hash === "#about") {
        setPage("home");
        const sectionId = window.location.hash.slice(1);
        window.requestAnimationFrame(() => {
          document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth" });
        });
      } else {
        setPage((current) => current === "track" ? "home" : current);
      }
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    if (!trackSlug) {
      setActiveTrack(null);
      setTrackDetailState("idle");
      setTrackDetailError("");
      return;
    }
    let active = true;
    setTrackDetailState("loading");
    setTrackDetailError("");
    request(`/api/tracks/${encodeURIComponent(trackSlug)}`)
      .then((response) => {
        if (!active) return;
        setActiveTrack(response.track);
        setTrackDetailState("loaded");
      })
      .catch((error) => {
        if (!active) return;
        setActiveTrack(null);
        setTrackDetailState(error.status === 404 ? "not-found" : "error");
        if (error.status !== 404) setTrackDetailError(error.message);
      });
    return () => { active = false; };
  }, [trackSlug]);

  const activeInitials = useMemo(() => user?.full_name?.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "H", [user]);

  function navigate(nextPage) {
    if (window.location.hash.startsWith("#/tracks/") && nextPage !== "track") {
      window.location.hash = "";
    }
    setErrorMessage("");
    setNotice("");
    setFieldErrors({});
    setMobileMenu(false);
    setPage(nextPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openTrack(track) {
    const hash = `#/tracks/${encodeURIComponent(track.slug)}`;
    if (window.location.hash === hash) {
      setTrackSlug(track.slug);
      setPage("track");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      window.location.hash = hash;
    }
  }

  function backToTracks() {
    if (window.location.hash === "#tracks") {
      setPage("home");
      document.getElementById("tracks")?.scrollIntoView({ behavior: "smooth" });
    } else {
      window.location.hash = "tracks";
    }
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
      setForm({ ...emptyForm(response.user), domain: pendingRegistrationDomain });
      setPendingRegistrationDomain("");
      navigate("registration");
    } catch (error) {
      setErrorMessage(error.message);
      setFieldErrors(error.fieldErrors);
    } finally {
      setBusy(false);
    }
  }

  async function openRegistration(trackDomain = "") {
    const registrationDomain = typeof trackDomain === "string" ? trackDomain : "";
    setPendingRegistrationDomain(registrationDomain);
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
        setForm({ ...emptyForm(user), domain: registrationDomain });
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
      const [registrationResponse, foodResponse, trackResponse] = await Promise.all([
        request(`/api/admin/registrations?${params}`),
        request("/api/admin/food-facilities"),
        request("/api/admin/tracks"),
      ]);
      setAdminRows(registrationResponse.registrations);
      setFoodFacilities(foodResponse.food_facilities);
      setAdminTracks(trackResponse.tracks);
      setAdminSection("registrations");
      navigate("admin");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadKnowledgeDocuments(search = knowledgeSearch, origin = knowledgeOrigin) {
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    if (origin) params.set("origin", origin);
    const response = await request(`/api/admin/knowledge/documents?${params}`);
    setKnowledgeDocuments(response.documents);
  }

  async function loadKnowledge() {
    setKnowledgeLoading(true);
    setKnowledgeError("");
    try {
      const [statusResponse, documentResponse, gapResponse] = await Promise.all([
        request("/api/admin/knowledge/status"),
        request("/api/admin/knowledge/documents"),
        request("/api/admin/knowledge/gaps"),
      ]);
      setKnowledgeStatus(statusResponse);
      setKnowledgeDocuments(documentResponse.documents);
      setKnowledgeGaps(gapResponse.gaps);
    } catch (error) {
      setKnowledgeError(error.message);
    } finally {
      setKnowledgeLoading(false);
    }
  }

  async function refreshKnowledge() {
    try {
      const [statusResponse, gapResponse] = await Promise.all([
        request("/api/admin/knowledge/status"),
        request("/api/admin/knowledge/gaps"),
      ]);
      setKnowledgeStatus(statusResponse);
      setKnowledgeGaps(gapResponse.gaps);
      await loadKnowledgeDocuments();
      setKnowledgeError("");
    } catch (error) {
      setKnowledgeError(error.message);
    }
  }

  async function saveKnowledgeDocument(event) {
    event.preventDefault();
    setSavingKnowledge(true);
    setKnowledgeFieldErrors({});
    setKnowledgeError("");
    setKnowledgeMessage("");
    try {
      const response = await request(
        editingKnowledgeId === null
          ? "/api/admin/knowledge/documents"
          : `/api/admin/knowledge/documents/${editingKnowledgeId}`,
        {
          method: editingKnowledgeId === null ? "POST" : "PUT",
          headers: { "X-CSRF-Token": csrf },
          body: JSON.stringify(knowledgeForm),
        },
      );
      setKnowledgeMessage(
        response.embedding_pending
          ? "Saved. This answer will use keyword search until embeddings finish."
          : "Saved.",
      );
      setKnowledgeForm({ title: "", content: "", published: true });
      setEditingKnowledgeId(null);
      await refreshKnowledge();
    } catch (error) {
      setKnowledgeError(error.message);
      setKnowledgeFieldErrors(error.fieldErrors || {});
    } finally {
      setSavingKnowledge(false);
    }
  }

  async function editKnowledgeDocument(document) {
    setKnowledgeError("");
    try {
      const response = await request(`/api/admin/knowledge/documents/${document.id}`);
      const item = response.document;
      setKnowledgeForm({
        title: item.title,
        content: item.content,
        published: item.published,
      });
      setEditingKnowledgeId(item.id);
      setKnowledgeFieldErrors({});
      setKnowledgeMessage("");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      setKnowledgeError(error.message);
    }
  }

  async function deleteKnowledgeDocument(document) {
    if (!window.confirm(`Delete the custom knowledge document "${document.title}"?`)) return;
    setKnowledgeError("");
    try {
      await request(`/api/admin/knowledge/documents/${document.id}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrf },
      });
      if (editingKnowledgeId === document.id) {
        setEditingKnowledgeId(null);
        setKnowledgeForm({ title: "", content: "", published: true });
      }
      await refreshKnowledge();
    } catch (error) {
      setKnowledgeError(error.message);
    }
  }

  async function toggleKnowledgePublication(document) {
    setKnowledgeError("");
    try {
      const response = await request(`/api/admin/knowledge/documents/${document.id}/publish`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrf },
        body: JSON.stringify({ published: !document.published }),
      });
      setKnowledgeMessage(
        response.embedding_pending
          ? "Publication saved. Embeddings are pending; keyword search remains available."
          : `Document ${response.published ? "published" : "hidden"}.`,
      );
      await refreshKnowledge();
    } catch (error) {
      setKnowledgeError(error.message);
    }
  }

  async function viewKnowledgeChunks(document) {
    setKnowledgeError("");
    try {
      const response = await request(`/api/admin/knowledge/documents/${document.id}`);
      setKnowledgeChunksDocument(response.document);
    } catch (error) {
      setKnowledgeError(error.message);
    }
  }

  async function handleKnowledgeGap(gap, action) {
    setKnowledgeError("");
    if (action === "answer") {
      setKnowledgeForm({ title: gap.question.slice(0, 120), content: "", published: true });
      setEditingKnowledgeId(null);
      setKnowledgeFieldErrors({});
      setKnowledgeMessage("");
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (action === "delete" && !window.confirm("Delete this knowledge-gap question?")) return;
    try {
      if (action === "delete") {
        await request(`/api/admin/knowledge/gaps/${gap.id}`, {
          method: "DELETE",
          headers: { "X-CSRF-Token": csrf },
        });
      } else {
        await request(`/api/admin/knowledge/gaps/${gap.id}`, {
          method: "PATCH",
          headers: { "X-CSRF-Token": csrf },
          body: JSON.stringify({ status: "resolved" }),
        });
      }
      await refreshKnowledge();
    } catch (error) {
      setKnowledgeError(error.message);
    }
  }

  async function reindexKnowledge() {
    setKnowledgeReindexing(true);
    setKnowledgeError("");
    setKnowledgeMessage("");
    try {
      const result = await request("/api/admin/knowledge/reindex", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
      });
      setKnowledgeMessage(
        `Reindexed ${Object.values(result.counts).reduce((sum, count) => sum + count.documents, 0)} system documents; ` +
        `${result.chunks_embedded} chunks embedded, ${result.chunks_skipped_unchanged} unchanged.`,
      );
      await refreshKnowledge();
    } catch (error) {
      setKnowledgeError(error.message);
    } finally {
      setKnowledgeReindexing(false);
    }
  }

  async function searchKnowledge(event) {
    event.preventDefault();
    if (!knowledgeQuery.trim()) {
      setKnowledgeSearchError("Enter a question to test retrieval.");
      return;
    }
    setKnowledgeSearchLoading(true);
    setKnowledgeSearchError("");
    try {
      const params = new URLSearchParams({
        q: knowledgeQuery.trim(),
        k: "4",
        mode: knowledgeMode,
      });
      const response = await request(`/api/admin/knowledge/search?${params}`);
      setKnowledgeResults(response.results);
    } catch (error) {
      setKnowledgeSearchError(error.message);
      setKnowledgeResults([]);
    } finally {
      setKnowledgeSearchLoading(false);
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

  async function loadFoodPage() {
    setBusy(true);
    try {
      const response = await request("/api/food-facilities");
      setFoodFacilities(response.food_facilities);
      navigate("food");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshAdminFood() {
    const response = await request("/api/admin/food-facilities");
    setFoodFacilities(response.food_facilities);
  }

  async function refreshAdminTracks() {
    const response = await request("/api/admin/tracks");
    setAdminTracks(response.tracks);
    setTracks(response.tracks.filter((track) => track.published));
  }

  function editTrack(track) {
    setEditingTrackId(track.id);
    setTrackForm({
      slug: track.slug,
      number: track.number,
      title: track.title,
      tagline: track.tagline,
      description: track.description,
      color_class: track.color_class,
      problem_statements: track.problem_statements.join("\n"),
      suggested_tech: track.suggested_tech.join("\n"),
      resources: track.resources.map((resource) => `${resource.label} | ${resource.url}`).join("\n"),
      sort_order: track.sort_order,
      published: track.published,
      registration_domain: track.registration_domain,
    });
  }

  async function saveTrack(event) {
    event.preventDefault();
    setSavingTrack(true);
    setErrorMessage("");
    const resources = trackForm.resources.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
      const separator = line.indexOf("|");
      return separator < 0
        ? { label: line, url: "" }
        : { label: line.slice(0, separator).trim(), url: line.slice(separator + 1).trim() };
    });
    const payload = {
      ...trackForm,
      problem_statements: trackForm.problem_statements.split("\n").map((item) => item.trim()).filter(Boolean),
      suggested_tech: trackForm.suggested_tech.split("\n").map((item) => item.trim()).filter(Boolean),
      resources,
    };
    try {
      await request(
        editingTrackId === null ? "/api/admin/tracks" : `/api/admin/tracks/${editingTrackId}`,
        {
          method: editingTrackId === null ? "POST" : "PATCH",
          headers: { "X-CSRF-Token": csrf },
          body: JSON.stringify(payload),
        },
      );
      await refreshAdminTracks();
      setEditingTrackId(null);
      setTrackForm(emptyTrackForm());
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setSavingTrack(false);
    }
  }

  async function deleteTrack(track) {
    if (!window.confirm(`Delete the ${track.title} track?`)) return;
    setErrorMessage("");
    try {
      await request(`/api/admin/tracks/${track.id}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrf },
      });
      await refreshAdminTracks();
      if (editingTrackId === track.id) {
        setEditingTrackId(null);
        setTrackForm(emptyTrackForm());
      }
    } catch (error) {
      setErrorMessage(error.message);
    }
  }

  function editFoodFacility(facility) {
    setEditingFoodId(facility.id);
    setFoodForm({
      facility_type: facility.facility_type,
      timing: facility.timing || "",
      start_time: facility.start_time || "",
      end_time: facility.end_time || "",
      items: facility.items || "",
      availability: facility.availability || "Not Announced Yet",
      price_status: facility.price_status || "Not Announced Yet",
      charges: facility.charges || "",
      location: facility.location || "",
      published: Boolean(facility.published),
    });
  }

  async function saveFoodFacility(event) {
    event.preventDefault();
    setSavingFood(true);
    setErrorMessage("");
    try {
      await request(
        editingFoodId === null
          ? "/api/admin/food-facilities"
          : `/api/admin/food-facilities/${editingFoodId}`,
        {
          method: editingFoodId === null ? "POST" : "PUT",
          headers: { "X-CSRF-Token": csrf },
          body: JSON.stringify(foodForm),
        },
      );
      await refreshAdminFood();
      setEditingFoodId(null);
      setFoodForm(emptyFoodForm());
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setSavingFood(false);
    }
  }

  async function deleteFoodFacility(facility) {
    if (!window.confirm(`Delete the ${facility.facility_type} information?`)) return;
    setErrorMessage("");
    try {
      await request(`/api/admin/food-facilities/${facility.id}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrf },
      });
      await refreshAdminFood();
      if (editingFoodId === facility.id) {
        setEditingFoodId(null);
        setFoodForm(emptyFoodForm());
      }
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
          <a href="#about" onClick={(event) => { event.preventDefault(); navigate("home"); window.location.hash = "about"; document.getElementById("about")?.scrollIntoView({ behavior: "smooth" }); }}>About</a>
          <a href="#tracks" onClick={(event) => { event.preventDefault(); navigate("home"); window.location.hash = "tracks"; document.getElementById("tracks")?.scrollIntoView({ behavior: "smooth" }); }}>Tracks</a>
          <button className="nav-link" onClick={loadFoodPage} disabled={busy}>Food &amp; Facilities</button>
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
              {tracksLoading ? (
                <p className="track-list-message" role="status">Loading hackathon tracks...</p>
              ) : tracksError ? (
                <div className="track-list-message" role="alert">
                  <p>We couldn't load the tracks right now. Please try again in a moment.</p>
                  <button className="details-button" type="button" onClick={() => {
                    setTracksLoading(true);
                    setTracksError("");
                    request("/api/tracks")
                      .then((response) => setTracks(response.tracks))
                      .catch((error) => setTracksError(error.message))
                      .finally(() => setTracksLoading(false));
                  }}>Try again</button>
                </div>
              ) : tracks.length === 0 ? (
                <p className="track-list-message">Tracks will be announced here soon.</p>
              ) : tracks.map((track) => (
                <button
                  type="button"
                  className={`track-card ${track.color_class}`}
                  key={track.id}
                  onClick={() => openTrack(track)}
                  aria-label={`Open ${track.title} track`}
                >
                  <div className="track-card-top"><span>{track.number} / TRACK</span><span className="track-arrow"><Icon name="arrow" size={17} /></span></div>
                  <div className="track-decoration"><Icon name="spark" size={28} /></div>
                  <h3>{track.title}</h3><p>{track.tagline}</p>
                </button>
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

      {page === "track" && (
        <main className="track-detail-page">
          {trackDetailState === "loading" && <div className="track-detail-message" role="status"><span className="loader" /> Loading track details...</div>}
          {trackDetailState === "not-found" && (
            <section className="track-detail-message">
              <span className="section-kicker">TRACK DIRECTORY</span>
              <h1>Track not found.</h1>
              <p>This track may have been unpublished or the link may be incorrect.</p>
              <button type="button" className="button button-outline button-large" onClick={backToTracks}>Back to all tracks <Icon name="arrow" size={18} /></button>
            </section>
          )}
          {trackDetailState === "error" && (
            <section className="track-detail-message" role="alert">
              <span className="section-kicker">TRACK DIRECTORY</span>
              <h1>We couldn't load this track.</h1>
              <p>{trackDetailError}</p>
              <button type="button" className="button button-outline button-large" onClick={backToTracks}>Back to all tracks <Icon name="arrow" size={18} /></button>
            </section>
          )}
          {trackDetailState === "loaded" && activeTrack && (
            <>
              <section className={`track-detail-hero ${activeTrack.color_class}`}>
                <button type="button" className="track-back-link" onClick={backToTracks}>← Back to all tracks</button>
                <span className="track-detail-number">{activeTrack.number} / TRACK</span>
                <h1>{activeTrack.title}</h1>
                <p>{activeTrack.tagline}</p>
                <div className="track-detail-decoration"><Icon name="spark" size={86} /></div>
              </section>
              <section className="track-detail-content">
                <div className="track-detail-intro">
                  <span className="section-kicker">ABOUT THIS TRACK</span>
                  <p>{activeTrack.description}</p>
                </div>
                <div className="track-detail-columns">
                  <section className="track-detail-panel">
                    <span className="section-kicker">IDEAS TO GET YOU STARTED</span>
                    <h2>Example problem statements</h2>
                    <ul>{activeTrack.problem_statements.map((statement) => <li key={statement}>{statement}</li>)}</ul>
                  </section>
                  <section className="track-detail-panel">
                    <span className="section-kicker">TOOLS YOU COULD USE</span>
                    <h2>Suggested tech stack</h2>
                    <div className="track-tech-chips">{activeTrack.suggested_tech.map((technology) => <span className="track-tech-chip" key={technology}>{technology}</span>)}</div>
                    {activeTrack.resources.length > 0 && (
                      <div className="track-resource-list">
                        <h3>Helpful resources</h3>
                        {activeTrack.resources.map((resource) => <a key={`${resource.label}-${resource.url}`} href={resource.url} target="_blank" rel="noopener noreferrer">{resource.label} <span aria-hidden="true">↗</span></a>)}
                      </div>
                    )}
                  </section>
                </div>
                <div className="track-detail-actions">
                  <button type="button" className="button button-outline button-large" onClick={backToTracks}>Back to all tracks</button>
                  <button type="button" className="button button-primary button-large" onClick={() => openRegistration(activeTrack.registration_domain)} disabled={busy}>Register for this track <Icon name="arrow" size={18} /></button>
                </div>
              </section>
            </>
          )}
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
              <div className="help-note"><Icon name="mail" size={17} /><span>Organizer contact details have not been published on this website yet.</span></div>
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
          <div className="page-topline">
            <span className="section-kicker">ORGANIZER CONSOLE</span>
            {adminSection === "registrations" && <a className="button button-outline button-small" href="/api/admin/export.csv"><Icon name="download" size={16} /> Export CSV</a>}
          </div>
          <div className="admin-tabs" role="tablist" aria-label="Organizer dashboard sections">
            <button type="button" role="tab" aria-selected={adminSection === "registrations"} className={adminSection === "registrations" ? "admin-tab admin-tab-active" : "admin-tab"} onClick={() => setAdminSection("registrations")}>Registrations</button>
            <button type="button" role="tab" aria-selected={adminSection === "food"} className={adminSection === "food" ? "admin-tab admin-tab-active" : "admin-tab"} onClick={() => setAdminSection("food")}>Food &amp; Facilities</button>
            <button type="button" role="tab" aria-selected={adminSection === "tracks"} className={adminSection === "tracks" ? "admin-tab admin-tab-active" : "admin-tab"} onClick={() => setAdminSection("tracks")}>Tracks</button>
            <button type="button" role="tab" aria-selected={adminSection === "knowledge"} className={adminSection === "knowledge" ? "admin-tab admin-tab-active" : "admin-tab"} onClick={() => { setAdminSection("knowledge"); loadKnowledge(); }}>Knowledge</button>
          </div>
          {adminSection === "registrations" ? (
            <>
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
            </>
          ) : adminSection === "food" ? (
            <section className="food-admin-section">
              <div className="admin-title"><div><h1>Food <span>&amp; facilities.</span></h1><p>Manage the details shown to participants and in the FAQ assistant.</p></div></div>
              <form className="food-editor" onSubmit={saveFoodFacility}>
                <div className="food-editor-heading">
                  <div><span className="section-kicker">{editingFoodId === null ? "ADD FACILITY DETAILS" : "EDIT FACILITY DETAILS"}</span><h2>{editingFoodId === null ? "Add food & beverage information" : `Update ${foodForm.facility_type}`}</h2></div>
                  {editingFoodId !== null && <button type="button" className="text-button" onClick={() => { setEditingFoodId(null); setFoodForm(emptyFoodForm()); }}>Cancel edit</button>}
                </div>
                <div className="field-grid">
                  <Field label="Food facility" name="facility_type" as="select" options={FOOD_FACILITY_TYPES.filter((type) => editingFoodId !== null || !foodFacilities.some((facility) => facility.facility_type === type))} value={foodForm.facility_type} onChange={(event) => setFoodForm({ ...foodForm, facility_type: event.target.value })} required disabled={editingFoodId !== null} />
                  {foodForm.facility_type !== "Drinking Water" && <>
                    <Field label="Start time" name="start_time" type="time" value={foodForm.start_time} onChange={(event) => setFoodForm({ ...foodForm, start_time: event.target.value })} />
                    <Field label="End time" name="end_time" type="time" value={foodForm.end_time} onChange={(event) => setFoodForm({ ...foodForm, end_time: event.target.value })} />
                  </>}
                  {!["Drinking Water"].includes(foodForm.facility_type) && <Field className="field-wide" label={foodForm.facility_type === "Tea Stall" || foodForm.facility_type === "Coffee Stall" || foodForm.facility_type === "Other Beverages" ? "Beverages provided" : "Food items provided"} name="items" as="textarea" rows="3" value={foodForm.items} onChange={(event) => setFoodForm({ ...foodForm, items: event.target.value })} placeholder="Enter items or beverages; use a new line for each" maxLength={2000} />}
                  <Field label="Availability" name="availability" as="select" options={FOOD_AVAILABILITY_OPTIONS} value={foodForm.availability} onChange={(event) => setFoodForm({ ...foodForm, availability: event.target.value })} required />
                  <Field label={foodForm.facility_type === "Drinking Water" ? "Water is" : "Free or paid"} name="price_status" as="select" options={FOOD_PRICE_OPTIONS} value={foodForm.price_status} onChange={(event) => setFoodForm({ ...foodForm, price_status: event.target.value, charges: event.target.value === "Paid" ? foodForm.charges : "" })} required />
                  {foodForm.price_status === "Paid" && <Field label="Price / charges" name="charges" value={foodForm.charges} onChange={(event) => setFoodForm({ ...foodForm, charges: event.target.value })} placeholder="Enter the paid price" maxLength={100} required />}
                  <Field className="field-wide" label={foodForm.facility_type === "Drinking Water" ? "Water station locations" : foodForm.facility_type?.includes("Stall") ? "Stall location" : "Food serving location"} name="location" as="textarea" rows="2" value={foodForm.location} onChange={(event) => setFoodForm({ ...foodForm, location: event.target.value })} placeholder={foodForm.facility_type === "Drinking Water" ? "Enter each water station location" : "e.g. Main dining hall"} maxLength={300} />
                </div>
                <label className="food-publish-toggle"><input type="checkbox" checked={foodForm.published} onChange={(event) => setFoodForm({ ...foodForm, published: event.target.checked })} /><span>Publish these details to participants and the assistant</span></label>
                <p className="food-card-intro">Unpublished drafts are visible only in the organizer dashboard.</p>
                <button className="button button-primary button-small" type="submit" disabled={savingFood || !foodForm.facility_type}>{savingFood ? "Saving..." : foodForm.published ? "Save & publish" : "Save draft"}</button>
              </form>
              <div className="food-admin-grid">
                {FOOD_FACILITY_TYPES.map((type) => {
                  const facility = foodFacilities.find((item) => item.facility_type === type);
                  return (
                    <article className="food-admin-card" key={type}>
                      <div><span className="section-kicker">FOOD &amp; FACILITIES</span><h3>{type}</h3></div>
                      {type !== "Drinking Water" && <p><b>Serving time:</b> {facility ? displayFoodTiming(facility) : "Not Announced Yet"}</p>}
                      {type !== "Drinking Water" && <p className="food-card-items"><b>Items:</b> {facility?.items || "Not Announced Yet"}</p>}
                      <p><b>Availability:</b> {facility?.availability || "Not Announced Yet"}</p>
                      <p><b>Pricing:</b> {facility?.price_status === "Free" ? "FREE" : facility?.price_status === "Paid" ? `PAID · ${facility.charges || "Not Announced Yet"}` : "Not Announced Yet"}</p>
                      <p><b>Location:</b> {facility?.location || "Not Announced Yet"}</p>
                      <p><b>Publication:</b> {facility?.published ? "Published to participants" : "Draft — not public"}</p>
                      <div className="food-admin-actions">
                        {facility ? (
                          <>
                            <button type="button" className="details-button" onClick={() => editFoodFacility(facility)}>Edit</button>
                            <button type="button" className="food-delete-button" onClick={() => deleteFoodFacility(facility)}>Delete</button>
                          </>
                        ) : (
                          <button type="button" className="details-button" onClick={() => { setEditingFoodId(null); setFoodForm({ ...emptyFoodForm(), facility_type: type }); }}>Add details</button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          ) : adminSection === "tracks" ? (
            <section className="food-admin-section track-admin-section">
              <div className="admin-title"><div><h1>Hackathon <span>tracks.</span></h1><p>Edit the public track pages and choose which ones participants can see.</p></div><div className="admin-count"><b>{adminTracks.length}</b><span>tracks</span></div></div>
              <form className="food-editor" onSubmit={saveTrack}>
                <div className="food-editor-heading">
                  <div><span className="section-kicker">{editingTrackId === null ? "ADD TRACK" : "EDIT TRACK"}</span><h2>{editingTrackId === null ? "Create a track" : `Update ${trackForm.title}`}</h2></div>
                  {editingTrackId !== null && <button type="button" className="text-button" onClick={() => { setEditingTrackId(null); setTrackForm(emptyTrackForm()); }}>Cancel edit</button>}
                </div>
                <div className="field-grid">
                  <Field label="Track title" name="title" value={trackForm.title} onChange={(event) => setTrackForm({ ...trackForm, title: event.target.value })} required maxLength={100} />
                  <Field label="URL slug" name="slug" value={trackForm.slug} onChange={(event) => setTrackForm({ ...trackForm, slug: event.target.value })} placeholder="example-track" required maxLength={100} />
                  <Field label="Track number" name="number" value={trackForm.number} onChange={(event) => setTrackForm({ ...trackForm, number: event.target.value })} placeholder="01" required maxLength={3} />
                  <Field label="Sort order" name="sort_order" type="number" min="0" value={trackForm.sort_order} onChange={(event) => setTrackForm({ ...trackForm, sort_order: Number(event.target.value) })} required />
                  <Field className="field-wide" label="Tagline" name="tagline" value={trackForm.tagline} onChange={(event) => setTrackForm({ ...trackForm, tagline: event.target.value })} required maxLength={180} />
                  <Field className="field-wide" label="Description" name="description" as="textarea" rows="3" value={trackForm.description} onChange={(event) => setTrackForm({ ...trackForm, description: event.target.value })} required maxLength={2000} />
                  <Field className="field-wide" label="Example problem statements (one per line)" name="problem_statements" as="textarea" rows="5" value={trackForm.problem_statements} onChange={(event) => setTrackForm({ ...trackForm, problem_statements: event.target.value })} required />
                  <Field className="field-wide" label="Suggested technologies (one per line)" name="suggested_tech" as="textarea" rows="3" value={trackForm.suggested_tech} onChange={(event) => setTrackForm({ ...trackForm, suggested_tech: event.target.value })} required />
                  <Field className="field-wide" label="Resources (one per line: label | https://...)" name="resources" as="textarea" rows="3" value={trackForm.resources} onChange={(event) => setTrackForm({ ...trackForm, resources: event.target.value })} hint="Use HTTPS links. Leave blank if no resources are available." />
                  <Field label="Card color" name="color_class" as="select" options={["track-purple", "track-orange", "track-blue", "track-green", "track-pink", "track-yellow"]} value={trackForm.color_class} onChange={(event) => setTrackForm({ ...trackForm, color_class: event.target.value })} required />
                  <Field label="Registration domain" name="registration_domain" as="select" options={DOMAINS} value={trackForm.registration_domain} onChange={(event) => setTrackForm({ ...trackForm, registration_domain: event.target.value })} required />
                </div>
                <label className="food-publish-toggle"><input type="checkbox" checked={trackForm.published} onChange={(event) => setTrackForm({ ...trackForm, published: event.target.checked })} /><span>Publish this track to participants and the assistant</span></label>
                <p className="food-card-intro">Unpublished tracks are hidden from the public track list and assistant.</p>
                <button className="button button-primary button-small" type="submit" disabled={savingTrack}>{savingTrack ? "Saving..." : trackForm.published ? "Save & publish" : "Save draft"}</button>
              </form>
              <div className="track-admin-grid">
                {adminTracks.map((track) => (
                  <article className="track-admin-card" key={track.id}>
                    <div className={`track-admin-swatch ${track.color_class}`} aria-hidden="true" />
                    <span className="section-kicker">{track.number} / {track.published ? "PUBLISHED" : "DRAFT"}</span>
                    <h3>{track.title}</h3>
                    <p>{track.tagline}</p>
                    <p><b>Registration domain:</b> {track.registration_domain}</p>
                    <div className="food-admin-actions">
                      <button type="button" className="details-button" onClick={() => editTrack(track)}>Edit</button>
                      <button type="button" className="food-delete-button" onClick={() => deleteTrack(track)}>Delete</button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : (
            <section className="knowledge-admin-section">
              <div className="admin-title">
                <div><h1>Knowledge <span>base.</span></h1><p>Manage official answers, test retrieval, and review unanswered questions.</p></div>
              </div>
              {knowledgeError && <p className="inline-alert" role="alert">{knowledgeError}</p>}
              {knowledgeMessage && <p className="knowledge-success" role="status">{knowledgeMessage}</p>}
              {knowledgeLoading && <p className="knowledge-muted">Loading knowledge tools...</p>}

              <div className="knowledge-status-bar">
                <div><span>Documents</span><b>{knowledgeStatus?.document_count ?? "—"}</b></div>
                <div><span>Chunks</span><b>{knowledgeStatus?.chunk_count ?? "—"}</b></div>
                <div><span>Embedded chunks</span><b>{knowledgeStatus?.embedded_chunk_count ?? "—"}</b></div>
                <div><span>Embeddings</span><b>{knowledgeStatus ? (knowledgeStatus.embeddings_available ? "Available" : "Unavailable") : "—"}</b></div>
                <button className="button button-primary button-small" type="button" onClick={reindexKnowledge} disabled={knowledgeReindexing}>
                  {knowledgeReindexing ? "Reindexing..." : "Reindex now"}
                </button>
              </div>

              <form className="food-editor knowledge-editor" onSubmit={saveKnowledgeDocument}>
                <div className="food-editor-heading">
                  <div>
                    <span className="section-kicker">{editingKnowledgeId === null ? "ADD CUSTOM KNOWLEDGE" : "EDIT CUSTOM KNOWLEDGE"}</span>
                    <h2>{editingKnowledgeId === null ? "Create an answer" : "Update this answer"}</h2>
                  </div>
                  {editingKnowledgeId !== null && <button type="button" className="text-button" onClick={() => { setEditingKnowledgeId(null); setKnowledgeForm({ title: "", content: "", published: true }); setKnowledgeFieldErrors({}); }}>Cancel edit</button>}
                </div>
                <Field label="Title" name="title" value={knowledgeForm.title} onChange={(event) => setKnowledgeForm({ ...knowledgeForm, title: event.target.value })} error={knowledgeFieldErrors.title} required minLength={3} maxLength={120} />
                <label className="field">
                  <span className="field-label">Answer content <span className="required">*</span></span>
                  <textarea name="content" rows="6" value={knowledgeForm.content} onChange={(event) => setKnowledgeForm({ ...knowledgeForm, content: event.target.value })} aria-invalid={Boolean(knowledgeFieldErrors.content)} minLength={20} maxLength={4000} />
                  <span className="field-hint">{knowledgeForm.content.length}/4000 characters · minimum 20</span>
                  {knowledgeFieldErrors.content && <span className="field-error">{knowledgeFieldErrors.content}</span>}
                </label>
                <label className="food-publish-toggle"><input type="checkbox" checked={knowledgeForm.published} onChange={(event) => setKnowledgeForm({ ...knowledgeForm, published: event.target.checked })} /><span>Publish this answer for chatbot retrieval</span></label>
                <div className="knowledge-form-actions">
                  <button className="button button-primary button-small" type="submit" disabled={savingKnowledge}>{savingKnowledge ? "Saving..." : "Save answer"}</button>
                  <span className="knowledge-muted">Content is stored and displayed as plain text.</span>
                </div>
              </form>

              <section className="knowledge-panel">
                <div className="knowledge-panel-heading"><div><span className="section-kicker">KNOWLEDGE DOCUMENTS</span><h2>Documents</h2></div></div>
                <div className="knowledge-filters">
                  <label className="search-box"><span className="search-symbol">⌕</span><input aria-label="Search knowledge documents" placeholder="Search title or content..." value={knowledgeSearch} onChange={(event) => { const value = event.target.value; setKnowledgeSearch(value); loadKnowledgeDocuments(value, knowledgeOrigin).catch((error) => setKnowledgeError(error.message)); }} /></label>
                  <select aria-label="Filter knowledge documents" value={knowledgeOrigin} onChange={(event) => { const value = event.target.value; setKnowledgeOrigin(value); loadKnowledgeDocuments(knowledgeSearch, value).catch((error) => setKnowledgeError(error.message)); }}>
                    <option value="">All sources</option><option value="system">System</option><option value="admin">Custom</option>
                  </select>
                </div>
                {knowledgeLoading ? <p className="knowledge-muted">Loading documents...</p> : knowledgeDocuments.length === 0 ? <p className="knowledge-empty">No knowledge documents match this filter.</p> : (
                  <div className="knowledge-document-list">
                    {knowledgeDocuments.map((document) => (
                      <article className="knowledge-document" key={document.id}>
                        <div className="knowledge-document-main">
                          <div className="knowledge-badges">
                            <span className={`knowledge-origin knowledge-origin-${document.origin}`}>{document.origin === "admin" ? "Custom" : "System"}</span>
                            <span className={`knowledge-published ${document.published ? "is-published" : "is-hidden"}`}>{document.published ? "Published" : "Hidden"}</span>
                          </div>
                          <h3>{document.title}</h3>
                          <p>{document.chunk_count} chunks · {document.embedded_chunk_count} embedded · Updated {document.updated_at}</p>
                        </div>
                        <div className="knowledge-document-actions">
                          {document.origin === "admin" && <button type="button" className="details-button" onClick={() => editKnowledgeDocument(document)}>Edit</button>}
                          <button type="button" className="details-button" onClick={() => viewKnowledgeChunks(document)}>View chunks</button>
                          <button type="button" className="details-button" onClick={() => toggleKnowledgePublication(document)}>{document.published ? "Unpublish" : "Publish"}</button>
                          {document.origin === "admin" && <button type="button" className="food-delete-button" onClick={() => deleteKnowledgeDocument(document)}>Delete</button>}
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="knowledge-panel">
                <div className="knowledge-panel-heading"><div><span className="section-kicker">RETRIEVAL CHECK</span><h2>Test search</h2></div></div>
                <form className="knowledge-search-form" onSubmit={searchKnowledge}>
                  <label className="search-box"><span className="search-symbol">⌕</span><input aria-label="Test knowledge retrieval" placeholder="Ask a question to test the index..." value={knowledgeQuery} onChange={(event) => setKnowledgeQuery(event.target.value)} /></label>
                  <select aria-label="Retrieval mode" value={knowledgeMode} onChange={(event) => setKnowledgeMode(event.target.value)}>
                    <option value="hybrid">Hybrid</option><option value="bm25">Keyword</option><option value="semantic">Semantic</option>
                  </select>
                  <button className="button button-primary button-small" type="submit" disabled={knowledgeSearchLoading}>{knowledgeSearchLoading ? "Searching..." : "Search"}</button>
                </form>
                {knowledgeSearchError && <p className="field-error" role="alert">{knowledgeSearchError}</p>}
                {!knowledgeSearchLoading && knowledgeQuery && knowledgeResults.length === 0 && !knowledgeSearchError && <p className="knowledge-empty">No matching chunks found. Try another question or check publication status.</p>}
                <div className="knowledge-results">
                  {knowledgeResults.map((result, index) => (
                    <article className="knowledge-result" key={`${result.source_key}-${index}`}>
                      <div><span className="section-kicker">#{index + 1} · {result.source_type}</span><h3>{result.title}</h3></div>
                      <p>{result.chunk_text}</p>
                      <small>BM25 {result.bm25_score == null ? "—" : result.bm25_score.toFixed(3)} · Semantic {result.semantic_score == null ? "—" : result.semantic_score.toFixed(3)} · Fused {result.fused_score == null ? "—" : result.fused_score.toFixed(4)}</small>
                    </article>
                  ))}
                </div>
              </section>

              <section className="knowledge-panel">
                <div className="knowledge-panel-heading"><div><span className="section-kicker">QUESTIONS NEEDING AN ANSWER</span><h2>Knowledge gaps</h2></div></div>
                {knowledgeGaps.filter((gap) => gap.status === "open").length === 0 ? <p className="knowledge-empty">No open questions. Unanswered event questions will appear here.</p> : (
                  <div className="knowledge-gap-list">
                    {knowledgeGaps.filter((gap) => gap.status === "open").map((gap) => (
                      <article className="knowledge-gap" key={gap.id}>
                        <div><h3>{gap.question}</h3><p>Asked {gap.times_asked} {gap.times_asked === 1 ? "time" : "times"} · Last seen {gap.last_seen}</p></div>
                        <div className="knowledge-document-actions">
                          <button type="button" className="details-button" onClick={() => handleKnowledgeGap(gap, "answer")}>Add answer</button>
                          <button type="button" className="details-button" onClick={() => handleKnowledgeGap(gap, "resolve")}>Mark resolved</button>
                          <button type="button" className="food-delete-button" onClick={() => handleKnowledgeGap(gap, "delete")}>Delete</button>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </section>
          )}
        </main>
      )}

      {page === "food" && (
        <main className="food-page">
          <div className="page-topline"><span className="section-kicker">PARTICIPANT INFORMATION</span><span className="food-updated-note">Details are updated by the organizers</span></div>
          <div className="admin-title"><div><h1>🍽️ Food <span>&amp; Facilities.</span></h1></div></div>
          <p className="food-status-message">Food and drinking water facilities are available for participants.</p>
          <p className="food-schedule-note">Official meal schedule for registered participants.</p>
          <div className="food-schedule-list">
            {OFFICIAL_FOOD_SCHEDULE.map((sample) => {
              const publishedFacility = foodFacilities.find(
                (facility) => facility.facility_type === sample.facility_type && facility.published,
              );
              const officialTiming = publishedFacility && sample.facility_type !== "Drinking Water"
                ? displayFoodTiming(publishedFacility)
                : "";
              const details = sample.facility_type === "Drinking Water" && publishedFacility
                ? publishedFacility.availability || sample.details
                : officialTiming && officialTiming !== "Not Announced Yet"
                  ? officialTiming
                  : sample.details;

              return (
                <article className="food-schedule-row" key={sample.facility_type}>
                  <span className="food-schedule-icon" aria-hidden="true">{sample.icon}</span>
                  <h2>{sample.facility_type}</h2>
                  <p>{details}</p>
                </article>
              );
            })}
          </div>
        </main>
      )}

      {selectedRegistration && page === "admin" && <div className="modal-backdrop" onClick={() => setSelectedRegistration(null)}><section className="details-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title" onClick={(event) => event.stopPropagation()}><button className="modal-close" aria-label="Close details" onClick={() => setSelectedRegistration(null)}><Icon name="close" /></button><span className="section-kicker">PARTICIPANT DETAILS</span><h2 id="detail-title">{selectedRegistration.full_name}</h2><p className="modal-id">{selectedRegistration.registration_id} · {selectedRegistration.email}</p><div className="modal-details">{Object.entries({ College: selectedRegistration.college_name, Mobile: selectedRegistration.mobile_number, Degree: selectedRegistration.degree, Department: selectedRegistration.department, "Year of study": selectedRegistration.year_of_study, "College location": selectedRegistration.college_location, Participation: selectedRegistration.participation_type, "Team name": selectedRegistration.team_name || "—", "Team leader": selectedRegistration.team_leader || "—", Domain: selectedRegistration.domain, "Technical skills": selectedRegistration.technical_skills, "Project title": selectedRegistration.project_title || "—", "Project idea": selectedRegistration.project_idea, GitHub: selectedRegistration.github_url || "—" }).map(([label, value]) => <div key={label}><span>{label}</span><p>{value}</p></div>)}</div>{selectedRegistration.team_members?.length > 0 && <div className="modal-team"><b>Team members</b>{selectedRegistration.team_members.map((member) => <p key={member.email}>{member.name} · {member.email}</p>)}</div>}<label className="modal-status">Registration status<select value={selectedRegistration.status} onChange={(event) => changeStatus(selectedRegistration, event.target.value)}>{STATUS_OPTIONS.map((status) => <option key={status}>{status}</option>)}</select></label></section></div>}

      {knowledgeChunksDocument && page === "admin" && <div className="modal-backdrop" onClick={() => setKnowledgeChunksDocument(null)}><section className="details-modal knowledge-chunks-modal" role="dialog" aria-modal="true" aria-labelledby="knowledge-chunks-title" onClick={(event) => event.stopPropagation()}><button className="modal-close" aria-label="Close chunks" onClick={() => setKnowledgeChunksDocument(null)}><Icon name="close" /></button><span className="section-kicker">INDEXED CHUNKS</span><h2 id="knowledge-chunks-title">{knowledgeChunksDocument.title}</h2><div className="knowledge-chunk-list">{knowledgeChunksDocument.chunks.map((chunk) => <article className="knowledge-chunk" key={chunk.id}><span>Chunk {chunk.chunk_index + 1} · {chunk.token_count} tokens · {chunk.embedded ? "Embedded" : "Keyword only"}</span><pre>{chunk.text}</pre></article>)}</div></section></div>}

      <footer className="site-footer"><a href="#home" className="brand footer-brand" onClick={(event) => { event.preventDefault(); navigate("home"); }}><span className="brand-mark"><Icon name="spark" size={18} /></span><span>hack<span className="brand-light">thefuture</span></span></a><span>MADE FOR THE BUILDERS OF TOMORROW.</span><span>© 2026 {eventName}</span></footer>
      {notice && page === "registration" && <div className="toast-note"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      {user && createPortal(<Chatbot request={request} csrf={csrf} />, document.body)}
    </div>
  );
}

export default App;
