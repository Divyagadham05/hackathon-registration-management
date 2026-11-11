import os
import re

if __package__:
    from .hackathon_faq import (
        OUT_OF_SCOPE_REPLY,
        UNKNOWN_INFO_REPLY,
        is_hackathon_faq_question,
        retrieve_faq_context,
    )
else:
    from hackathon_faq import (
        OUT_OF_SCOPE_REPLY,
        UNKNOWN_INFO_REPLY,
        is_hackathon_faq_question,
        retrieve_faq_context,
    )

KNOWLEDGE_CATEGORIES = (
    (
        "Hackathon Overview",
        re.compile(r"\b(?:hackathon|event|purpose|objective|goal)\b", re.IGNORECASE),
        (
            "Hack the Future is a student hackathon. The website describes a "
            "24-hour sprint for student builders to develop ideas with real-world impact."
        ),
    ),
    (
        "Event Details",
        re.compile(
            r"\b(?:date|when|where|venue|location|duration|24.hours?|tracks?|"
            r"prizes?|awards?|fee|cost|schedule|weekend)\b",
            re.IGNORECASE,
        ),
        (
            "The public homepage lists November 1–2, 2026 at Innovation Hub, Main "
            "Campus, and describes a 24-hour event for college students aged 16 or "
            "older. Participants may come with family. Prize details and any other "
            "event schedule are not announced in the published website information."
        ),
    ),
    (
        "Registration Process",
        re.compile(
            r"\b(?:registration|register|registered|registering|apply|application)\b",
            re.IGNORECASE,
        ),
        (
            "To register, create an account or log in, select Register, complete the "
            "registration form, and submit it. A successful submission displays a "
            "registration ID. A confirmation email is sent only if email delivery "
            "is configured and succeeds."
        ),
    ),
    (
        "Signup and Login",
        re.compile(
            r"\b(?:sign.?up|create an account|account|log.?in|log.?out|logout|"
            r"password|forgot password)\b",
            re.IGNORECASE,
        ),
        (
            "Sign up with your name, email, and password. To log in, use the email "
            "and password for your account. While signed in, use Log out in the "
            "website navigation to end your session."
        ),
    ),
    (
        "User Account",
        re.compile(
            r"\b(?:my registration|update|edit|change|modify|account details|"
            r"registration details)\b",
            re.IGNORECASE,
        ),
        (
            "A signed-in participant can view their own registration. The website "
            "does not currently provide a participant option to edit a submitted "
            "registration. Organizer contact details have not been published."
        ),
    ),
    (
        "Registration Form",
        re.compile(
            r"\b(?:form|details|required|fields?|team|degree|department|"
            r"college|skills|project idea|github)\b",
            re.IGNORECASE,
        ),
        (
            "Required fields include participant name, mobile number, college, "
            "degree, department, year of study, college location, participation "
            "type, hackathon domain, technical skills, project idea, and the two "
            "required confirmations. Team registrations also require team details "
            "and each other member's name and email. Date of birth, project title, "
            "and GitHub profile are optional. The account email is used."
        ),
    ),
    (
        "Food and Refreshment Information",
        re.compile(
            r"\b(?:food|meal|breakfast|lunch|dinner|snacks?|refreshments?|"
            r"drinking water|water|tea|coffee|beverages?|stall)\b",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        "Facilities and Amenities",
        re.compile(
            r"\b(?:facilit(?:y|ies)|amenit(?:y|ies)|parking|wifi|wi-fi|"
            r"accommodation|accessibility)\b",
            re.IGNORECASE,
        ),
        (
            "Only facilities explicitly published by an organizer are available "
            "as confirmed information on the website. Do not assume other amenities."
        ),
    ),
    (
        "Admin and Website Support",
        re.compile(
            r"\b(?:organizers?|organisers?|contact|support|help|website)\b",
            re.IGNORECASE,
        ),
        (
            "Organizer contact details have not been published on this website. "
            "The chatbot can answer questions about the published hackathon and "
            "website information."
        ),
    ),
    (
        "Frequently Asked Questions",
        re.compile(r"\b(?:faq|frequently asked questions|chatbot|assistant)\b", re.IGNORECASE),
        (
            "This assistant answers questions about this hackathon website and "
            "officially confirmed event information. Unknown details are not guessed."
        ),
    ),
)

DEFAULT_CHATBOT_REFUSAL_MESSAGE = (
    "I can only help with questions about the Hack the Future hackathon and this "
    "website, such as registration, teams, schedule, rules, prizes and support. "
    "Please ask me something about those."
)
GREETING_REPLY = (
    "Hi! I can help with Hack the Future registration, teams, schedule, rules, "
    "prizes, and website support. What would you like to know?"
)
HACKATHON_INFO = """\
Hack the Future is a student hackathon described as a 24-hour sprint.
The published dates are November 1–2, 2026, at Innovation Hub, Main Campus.
Participants must be college students aged 16 or older; they may come with family.
Registration offers Artificial Intelligence, Generative AI, Web Development,
Data Science, Cybersecurity, and Other. Teams can have 2 to 5 participants,
including the team leader. Registration requires an account, a completed form,
and submission; successful submission displays a registration ID.
Breakfast is 8:00–9:00 AM, lunch 1:00–2:00 PM, evening snacks 4:00–4:30 PM,
dinner 7:30–8:30 PM, and drinking water is available throughout the event.
Meals are free for eligible participants. Organizer contact details are not
published. Prizes are not announced.

TODO: Confirm the theme, problem statements, judging criteria, prize details,
registration deadline, exact event start/end times, detailed rules and code of
conduct, submission process, certificate policy, and organizer contact details.
"""
GREETING_PATTERN = re.compile(
    r"^(?:hi|hello|hey|good morning|good afternoon|good evening|"
    r"thanks|thank you|thx|what can you do|what do you do|"
    r"what can you help me with)[!.?,\s]*$",
    re.IGNORECASE,
)


def is_hackathon_question(question):
    if not isinstance(question, str) or not is_hackathon_faq_question(question):
        return False
    return True


def get_chatbot_refusal_message():
    return os.environ.get(
        "CHATBOT_REFUSAL_MESSAGE",
        DEFAULT_CHATBOT_REFUSAL_MESSAGE,
    ).strip() or DEFAULT_CHATBOT_REFUSAL_MESSAGE


def get_chatbot_greeting_reply(question):
    if isinstance(question, str) and GREETING_PATTERN.fullmatch(question.strip()):
        return GREETING_REPLY
    return None


def retrieve_hackathon_context(question, food_facilities=(), tracks=None):
    if not is_hackathon_question(question):
        return ""

    sections = []
    for category, pattern, content in KNOWLEDGE_CATEGORIES:
        if not pattern.search(question):
            continue
        if category == "Food and Refreshment Information":
            details = []
            for facility in food_facilities:
                values = []
                for field, label in (
                    ("timing", "timing"),
                    ("start_time", "start time"),
                    ("end_time", "end time"),
                    ("items", "items"),
                    ("location", "location"),
                ):
                    value = facility.get(field)
                    if isinstance(value, str) and value.strip() and value.casefold() != "not announced yet":
                        values.append(f"{label}: {value.strip()}")
                if values:
                    details.append(f"{facility['facility_type']}: {'; '.join(values)}")
            content = (
                "The official schedule is breakfast 8:00–9:00 AM, lunch "
                "1:00–2:00 PM, evening snacks 4:00–4:30 PM, and dinner "
                "7:30–8:30 PM. Breakfast, lunch, evening snacks, and dinner are "
                "completely free for eligible participants. Drinking water is "
                "available throughout the event. Tea and coffee "
                "and specific meal menu items have not been announced."
            )
            if details:
                content += " Current published facility records: " + " | ".join(details)
        elif category == "Facilities and Amenities":
            published_types = [
                facility["facility_type"]
                for facility in food_facilities
            ]
            if published_types:
                content += " Published facilities: " + ", ".join(published_types) + "."
        elif category == "Event Details":
            if tracks is not None:
                track_details = [
                    f"{track['title']}: {track['tagline']}"
                    for track in tracks
                ]
                if track_details:
                    content += " Published tracks: " + "; ".join(track_details) + "."
                else:
                    content += " There are currently no published tracks."
        sections.append(f"{category}:\n{content}")
    faq_context = retrieve_faq_context(question, food_facilities, tracks)
    if faq_context:
        sections.append(f"Relevant FAQ entries:\n{faq_context}")
    return "\n\n".join(sections)
