import re
from difflib import get_close_matches


FAQ_DATASET = (
    {
        "id": "overview",
        "category": "Hackathon Overview",
        "questions": (
            "What is this hackathon?",
            "What is Hack the Future?",
            "What is the purpose of this hackathon?",
            "What will participants do at the hackathon?",
            "Tell me about the hackathon.",
        ),
        "answer": (
            "Hack the Future is a student hackathon where participants build "
            "innovative projects in a 24-hour sprint."
        ),
    },
    {
        "id": "event_date",
        "category": "Event Details",
        "questions": (
            "When is the hackathon?",
            "What are the hackathon dates?",
            "What is the hackathon date?",
            "What date is the event?",
            "When does Hack the Future take place?",
        ),
        "answer": "The hackathon is scheduled for November 1–2, 2026.",
    },
    {
        "id": "event_venue",
        "category": "Event Details",
        "questions": (
            "Where is the hackathon?",
            "What is the event venue?",
            "What is the hackathon venue?",
            "Where will the event take place?",
            "What is the hackathon location?",
        ),
        "answer": "The event venue is Innovation Hub, Main Campus.",
    },
    {
        "id": "event_duration",
        "category": "Event Details",
        "questions": (
            "How long is the hackathon?",
            "How many hours does the event last?",
            "What are the hackathon start and end times?",
            "What time does the event start?",
        ),
        "answer": (
            "The website describes a 24-hour hackathon. Exact start and end "
            "times have not been announced."
        ),
    },
    {
        "id": "event_tracks",
        "category": "Event Details",
        "questions": (
            "What are the hackathon domains?",
            "Which project domains can I choose?",
            "What tracks are available?",
            "Which areas can we build projects in?",
        ),
        "answer": (
            "The registration form offers Artificial Intelligence, Generative AI, "
            "Web Development, Data Science, Cybersecurity, and Other."
        ),
    },
    {
        "id": "registration_steps",
        "category": "Registration Process",
        "questions": (
            "How do I register?",
            "How can I register for the hackathon?",
            "How do I sign up for the event?",
            "What are the registration steps?",
            "How can I join the hackathon?",
        ),
        "answer": (
            "1. Create an account or log in. 2. Select Register and complete the "
            "form. 3. Submit it to save your registration and receive a registration ID."
        ),
    },
    {
        "id": "signup",
        "category": "Signup and Login",
        "questions": (
            "How do I create an account?",
            "How can I sign up?",
            "What do I need to create an account?",
            "How do I make a website account?",
        ),
        "answer": "Select Sign up and enter your name, email, and password.",
    },
    {
        "id": "password_reset",
        "category": "Signup and Login",
        "questions": (
            "How do I reset my password?",
            "I forgot my password. How can I recover it?",
            "Where is the password reset option?",
        ),
        "answer": (
            "The website does not currently publish a password-reset process. "
            "Please check for organizer updates."
        ),
    },
    {
        "id": "login",
        "category": "Signup and Login",
        "questions": (
            "How do I log in?",
            "How can I sign in?",
            "Where is the login page?",
            "How do I access my account?",
        ),
        "answer": "Select Log in and enter the email and password for your account.",
    },
    {
        "id": "logout",
        "category": "User Account",
        "questions": (
            "How do I log out?",
            "How can I sign out?",
            "Where is the logout button?",
        ),
        "answer": "While signed in, select Log out in the website navigation.",
    },
    {
        "id": "eligibility",
        "category": "Eligibility and Participation",
        "questions": (
            "Who can participate?",
            "Who is eligible for the hackathon?",
            "Can students join?",
            "Is the event open to all students?",
            "Can anyone participate?",
            "What are the eligibility requirements?",
            "What is the minimum age to participate?",
            "How old do I need to be?",
            "What is the age limit?",
            "What is the minimum age?",
            "Can a 15 year old participate?",
            "Can I join if I am 16?",
            "Do I need to be a college student?",
            "Can school students participate?",
        ),
        "answer": "Participants must be at least 16 years old and college students.",
    },
    {
        "id": "family",
        "category": "Eligibility and Participation",
        "questions": (
            "Can I come with my family?",
            "Can my family come with me?",
            "Can I bring my family to the hackathon?",
            "Are family members allowed to come?",
            "Can my parents come?",
            "May my family come along?",
            "Can I bring my parents?",
            "Can my family accompany me?",
        ),
        "answer": (
            "Yes! You can come with your family. However, participants must be "
            "16 years or older and college students."
        ),
    },
    {
        "id": "participation_type",
        "category": "Eligibility and Participation",
        "questions": (
            "Can I participate alone?",
            "Can I join as an individual?",
            "Can I register as a team?",
            "Can I participate with a team?",
        ),
        "answer": "You can register as an individual or as a team.",
    },
    {
        "id": "team_size",
        "category": "Eligibility and Participation",
        "questions": (
            "How many people can be on a team?",
            "What is the team size?",
            "How many members are allowed?",
            "What is the maximum team size?",
        ),
        "answer": "Teams can have 2 to 5 participants, including the team leader.",
    },
    {
        "id": "registration_form",
        "category": "Registration Form",
        "questions": (
            "What details are required during registration?",
            "What information does the registration form ask for?",
            "Which registration fields are required?",
            "What details do I need to register?",
        ),
        "answer": (
            "The form asks for your name, mobile number, college, degree, "
            "department, study year, college location, participation type, domain, "
            "technical skills, project idea, and required confirmations. Team "
            "registrations also need team and member details. Date of birth, "
            "project title, and GitHub profile are optional; your account email "
            "is used for registration."
        ),
    },
    {
        "id": "registration_edit",
        "category": "User Account",
        "questions": (
            "Can I update my registration?",
            "Can I edit my submitted registration?",
            "How do I change my registration details?",
        ),
        "answer": (
            "The website lets you view your submitted registration but does not "
            "currently provide an option to edit it."
        ),
    },
    {
        "id": "breakfast_timing",
        "category": "Food and Refreshment Information",
        "questions": (
            "What time is breakfast?",
            "When is breakfast?",
            "What are breakfast timings?",
            "What time is tiffin?",
        ),
        "answer": "Breakfast is scheduled from 8:00 AM to 9:00 AM.",
        "food_facility": "Breakfast",
        "food_field": "timing",
    },
    {
        "id": "lunch_timing",
        "category": "Food and Refreshment Information",
        "questions": (
            "What time is lunch?",
            "When is lunch?",
            "When is lunch served?",
            "What are lunch timings?",
            "When can I have lunch?",
        ),
        "answer": "Lunch is scheduled from 1:00 PM to 2:00 PM.",
        "food_facility": "Lunch",
        "food_field": "timing",
    },
    {
        "id": "snack_timing",
        "category": "Food and Refreshment Information",
        "questions": (
            "What time are evening snacks?",
            "What are evening snacks timings?",
            "When are snacks served?",
            "What are the snack timings?",
            "When is snack time?",
        ),
        "answer": "Evening snacks are scheduled from 4:00 PM to 4:30 PM.",
        "food_facility": "Evening Snacks",
        "food_field": "timing",
    },
    {
        "id": "dinner_timing",
        "category": "Food and Refreshment Information",
        "questions": (
            "What time is dinner?",
            "When is dinner served?",
            "What are dinner timings?",
            "When can I have dinner?",
        ),
        "answer": "Dinner is scheduled from 7:30 PM to 8:30 PM. Enjoy your dinner!",
        "food_facility": "Dinner",
        "food_field": "timing",
    },
    {
        "id": "meal_prices",
        "category": "Food and Refreshment Information",
        "questions": (
            "Is breakfast free?",
            "Is lunch free?",
            "Is dinner free?",
            "Are evening snacks free?",
            "Is food free?",
            "Is all the food free?",
            "Is the food completely free?",
            "Do we need to pay for lunch?",
            "Do I need to pay for dinner?",
            "Do I have to pay for breakfast?",
            "Do I pay for breakfast?",
            "Do I need to pay for evening snacks?",
            "Do I pay for snacks?",
            "Do participants pay for meals?",
            "Will participants get free lunch?",
            "Is lunch included?",
            "Can I have lunch without paying?",
            "Are participants charged for food?",
            "Is there any charge for dinner?",
            "Will I be charged for breakfast?",
            "Are breakfast and lunch complimentary?",
            "Are meals complimentary?",
            "Are meals free?",
            "Are the meals paid?",
            "Do meals cost money?",
            "How much does food cost?",
            "Is dinner complimentary?",
        ),
        "answer": "Yes! {meal} is completely free for eligible participants. Enjoy your meal! 😊",
        "food_facility": "meal",
        "food_field": "price_status",
    },
    {
        "id": "food_availability",
        "category": "Food and Refreshment Information",
        "questions": (
            "Is food available?",
            "Will food be available for participants?",
            "Are meals available at the event?",
            "Is food provided during the hackathon?",
        ),
        "answer": "Food facilities are available for participants.",
    },
    {
        "id": "food_menu",
        "category": "Food and Refreshment Information",
        "questions": (
            "What food will be served?",
            "What is on the meal menu?",
            "What food items are provided?",
            "What will participants eat?",
        ),
        "answer": "Meal menu items have not been officially announced.",
        "food_facility": "meal",
        "food_field": "items",
    },
    {
        "id": "water",
        "category": "Food and Refreshment Information",
        "questions": (
            "Is drinking water available?",
            "Can I get drinking water?",
            "Will there be water during the event?",
            "Is water available throughout the hackathon?",
        ),
        "answer": "Yes! Drinking water is available throughout the event. 💧",
        "food_facility": "Drinking Water",
        "food_field": "availability",
    },
    {
        "id": "water_price",
        "category": "Food and Refreshment Information",
        "questions": (
            "Is drinking water free?",
            "Is water free?",
            "Do we have to pay for water?",
            "Does drinking water cost anything?",
        ),
        "answer": (
            "Yes! Drinking water is available throughout the event. 💧"
        ),
    },
    {
        "id": "published_facilities",
        "category": "Facilities and Amenities",
        "questions": (
            "What facilities are officially announced?",
            "Which facilities are available?",
            "What amenities are provided?",
            "What facilities can participants use?",
        ),
        "answer": (
            "The announced facilities are breakfast, lunch, evening snacks, dinner, "
            "and drinking water."
        ),
    },
    {
        "id": "other_beverages",
        "category": "Facilities and Amenities",
        "questions": (
            "Is coffee available?",
            "Is tea available?",
            "Are coffee or tea provided?",
            "Are there other beverage stalls?",
        ),
        "answer": "Tea and coffee availability has not been officially announced.",
        "food_facility": "beverages",
        "food_field": "availability",
    },
    {
        "id": "contact",
        "category": "Contact and Technical Support",
        "questions": (
            "How can I contact the organizers?",
            "How do I reach the event organizers?",
            "What is the organizer email?",
            "Who can help me with a website problem?",
            "How can I get technical support?",
        ),
        "answer": (
            "Organizer and technical support contact details have not been "
            "published on the website yet."
        ),
    },
    {
        "id": "unannounced_facilities",
        "category": "Facilities and Amenities",
        "questions": (
            "Is parking available?",
            "What is the event parking policy?",
            "Is Wi-Fi available at the venue?",
            "What is the Wi-Fi policy?",
            "Is accommodation provided?",
            "Is the venue accessible?",
            "Are prizes announced?",
            "What are the prizes?",
            "What prizes are there?",
        ),
        "answer": (
            "That facility or prize information has not been officially announced. "
            "Please check back for updates."
        ),
    },
    {
        "id": "confirmation_email",
        "category": "Registration Process",
        "questions": (
            "Will I get a registration confirmation email?",
            "Does the website send confirmation emails?",
            "Do I receive an email after registering?",
        ),
        "answer": (
            "After you submit, the website displays your registration ID. A "
            "confirmation email is sent only if email delivery is configured and succeeds."
        ),
    },
)

OUT_OF_SCOPE_REPLY = (
    "I can only help with questions about the Hack the Future hackathon and this "
    "website, such as registration, teams, schedule, rules, prizes and support. "
    "Please ask me something about those."
)
UNKNOWN_INFO_REPLY = (
    "That information is not available in the official hackathon information yet. "
    "Please check back for updates."
)
FOOD_INFO_UNAVAILABLE = (
    "Food and refreshment arrangements for this hackathon have not been officially "
    "announced yet. Please check back for updates."
)
OUT_OF_SCOPE_TERMS = re.compile(
    r"\b(?:gold|weather|jokes?|essays?|poems?|math(?:ematics)?|calculate|"
    r"solve|python|javascript|homework|science|history|politics|religion|"
    r"celebrity|celebrities|movie|movies|cricket|sports?|news|medical|legal|"
    r"financial advice|capital of|president of)\b|"
    r"\b(?:write|generate|create)\b.{0,40}\b(?:code|function|essay|poem|"
    r"email|resume|story)\b|"
    r"\b(?:other|another|different)\s+(?:hackathon|company|website|site)\b|"
    r"\b(?:company's|competitor's)\b|"
    r"\b(?:system\s+prompt|chatbot internals?)\b|"
    r"\b(?:your|assistant's|chatbot's|model's)\s+api[_ -]?keys?\b|"
    r"\bignore\b.{0,60}\b(?:instructions?|rules|prompt|restrictions?)\b|"
    r"\b(?:reveal|show|print|repeat|change|override|ignore)\b.{0,60}"
    r"\b(?:instructions?|rules|prompt|role|persona)\b|"
    r"\b(?:act|pretend|roleplay|role-play)\s+as\b|"
    r"\b(?:forget|disregard)\b.{0,60}\b(?:instructions?|rules|prompt)\b",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a", "an", "and", "are", "at", "can", "do", "does", "for", "get", "how",
    "i", "in", "is", "it", "me", "of", "on", "the", "there", "this", "to",
    "we", "what", "when", "where", "will", "with", "you",
}
COMMON_TYPOS = {
    "brekfast": "breakfast",
    "breakfest": "breakfast",
    "cofee": "coffee",
    "diner": "dinner",
    "loggin": "login",
    "regster": "register",
    "regstration": "registration",
    "snaks": "snacks",
}
FAQ_VOCABULARY = {
    token
    for entry in FAQ_DATASET
    for question in entry["questions"]
    for token in TOKEN_PATTERN.findall(question.casefold())
    if token not in STOP_WORDS
}


def _tokens(text):
    normalized = set()
    for token in TOKEN_PATTERN.findall(text.casefold()):
        if token in STOP_WORDS:
            continue
        token = COMMON_TYPOS.get(token, token)
        if token not in FAQ_VOCABULARY and len(token) >= 5:
            suggestion = get_close_matches(token, FAQ_VOCABULARY, n=1, cutoff=0.87)
            if suggestion:
                token = suggestion[0]
        normalized.add(token)
    return normalized


def _faq_entries_with_tokens():
    for entry in FAQ_DATASET:
        question_tokens = [_tokens(question) for question in entry["questions"]]
        yield entry, question_tokens


def match_faqs(question, min_score=0.72):
    query_tokens = _tokens(question)
    if not query_tokens:
        return []

    matches = []
    for entry, variations in _faq_entries_with_tokens():
        best_score = 0.0
        for variation in variations:
            overlap = len(query_tokens & variation)
            if overlap < (1 if len(variation) == 1 else 2):
                continue
            score = (2 * overlap) / (len(query_tokens) + len(variation))
            if score > best_score:
                best_score = score
        if best_score >= min_score:
            matches.append((best_score, entry))

    matches.sort(key=lambda result: result[0], reverse=True)
    has_multiple_questions = len(re.findall(r"[?;]", question)) > 1
    has_multiple_facts = re.search(r"\b(?:and|also|plus)\b", question.casefold())
    if not has_multiple_questions and not has_multiple_facts:
        return matches[:1]
    selected = []
    seen = set()
    for score, entry in matches:
        if entry["id"] in seen or score < matches[0][0] - 0.16:
            continue
        selected.append((score, entry))
        seen.add(entry["id"])
        if len(selected) == 3:
            break
    return selected


def is_hackathon_faq_question(question):
    if not isinstance(question, str) or OUT_OF_SCOPE_TERMS.search(question):
        return False
    if match_faqs(question, min_score=0.58):
        return True
    return any(
        word in question.casefold()
        for word in (
            "hackathon", "event", "website", "registration", "register", "login",
            "sign up", "account", "password", "admin", "form", "team", "squad",
            "support", "contact", "family", "parents", "mom", "dad", "mother",
            "father", "age", "student", "school", "kid", "eligible", "participate",
            "food", "meal", "breakfast", "lunch", "dinner", "snack",
            "facility", "facilities", "amenity", "amenities", "parking", "wifi",
            "water", "organizer", "organiser", "confirmation", "domain", "degree",
            "track", "innovation",
        )
    )


def _published_facility(entry, food_facilities, question):
    facility_type = entry.get("food_facility")
    if not facility_type:
        return None
    if facility_type == "meal":
        normalized_question = question.casefold()
        named_meal = next(
            (
                meal
                for meal in ("Breakfast", "Lunch", "Evening Snacks", "Dinner")
                if re.search(rf"\b{re.escape(meal.casefold())}\b", normalized_question)
                or (
                    meal == "Evening Snacks"
                    and re.search(r"\bsnacks?\b", normalized_question)
                )
            ),
            None,
        )
        if named_meal:
            return next(
                (
                    facility for facility in food_facilities
                    if facility.get("facility_type") == named_meal
                ),
                None,
            )
        published_meals = [
            facility
            for facility in food_facilities
            if facility.get("facility_type")
            in {"Breakfast", "Lunch", "Evening Snacks", "Dinner"}
        ]
        if len(published_meals) != 4:
            return None
        return next(
            (
                facility for facility in published_meals
                if facility.get("price_status") != "Free"
            ),
            published_meals[0],
        )
    if facility_type == "beverages":
        normalized_question = question.casefold()
        requested = [
            facility_type
            for facility_type in ("Tea Stall", "Coffee Stall", "Other Beverages")
            if any(
                alias in normalized_question
                for alias in {
                    "Tea Stall": ("tea",),
                    "Coffee Stall": ("coffee",),
                    "Other Beverages": ("beverage", "drink"),
                }[facility_type]
            )
        ]
        return next(
            (
                facility for facility in food_facilities
                if facility.get("facility_type") in requested
            ),
            None,
        )
    return next(
        (
            facility
            for facility in food_facilities
            if facility.get("facility_type") == facility_type
        ),
        None,
    )


def _meal_price_answer(entry, meal, question):
    if _asks_whether_payment_is_required(question):
        return f"No! {meal} is completely free for eligible participants. Enjoy your meal! 😊"
    return entry["answer"].format(meal=meal)


def _asks_whether_payment_is_required(question):
    normalized_question = question.casefold()
    if re.search(r"\bwithout\s+paying\b", normalized_question):
        return False
    return bool(
        re.search(
            r"\b(?:pay|paid|charge|charged|cost|costs|price|pricing|money)\b",
            normalized_question,
        )
    )


def _confirmed_food_policy_reply(question):
    normalized_question = question.casefold()
    if re.search(r"\b(?:water|hydration)\b", normalized_question) and re.search(
        r"\b(?:available|availability|provided|provide|get|have|free|pay|paid|"
        r"charge|charged|cost|costs|price|pricing)\b",
        normalized_question,
    ):
        return "Yes! Drinking water is available throughout the event. 💧"

    asks_price = re.search(
        r"\b(?:free|complimentary|pay|paid|charge|charged|cost|costs|price|"
        r"pricing|money)\b",
        normalized_question,
    )
    mentions_food = re.search(
        r"\b(?:food|meal|breakfast|tiffin|lunch|dinner|supper|snacks?)\b",
        normalized_question,
    )
    if not asks_price or not mentions_food:
        return None

    meals = [
        (name, pattern)
        for name, pattern in (
            ("Breakfast", r"\b(?:breakfast|tiffin)\b"),
            ("Lunch", r"\blunch\b"),
            ("Evening Snacks", r"\b(?:evening\s+)?snacks?\b"),
            ("Dinner", r"\b(?:dinner|supper)\b"),
        )
        if re.search(pattern, normalized_question)
    ]
    if not meals:
        if _asks_whether_payment_is_required(question):
            return "No! All food is completely free for eligible participants. Enjoy your meals! 😊"
        return "Yes! All food is completely free for eligible participants. Enjoy your meals! 😊"
    return "\n".join(
        _meal_price_answer({"answer": "Yes! {meal} is completely free for eligible participants. Enjoy your meal! 😊"}, meal, question)
        for meal, _ in meals
    )


def _format_food_time(value):
    if not isinstance(value, str) or value.casefold() == "not announced yet":
        return None
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        return value
    hours, minutes = (int(part) for part in value.split(":"))
    suffix = "AM" if hours < 12 else "PM"
    return f"{hours % 12 or 12}:{minutes:02d} {suffix}"


def _resolve_food_answer(entry, food_facilities, question, tracks=None):
    if entry["id"] == "event_tracks" and tracks is not None:
        if not tracks:
            return "There are no currently published hackathon tracks."
        available = "; ".join(f"{track['title']}: {track['tagline']}" for track in tracks)
        return f"Published hackathon tracks: {available}"
    if entry["id"] == "published_facilities" and food_facilities:
        names = ", ".join(facility["facility_type"] for facility in food_facilities)
        return f"Officially published facilities: {names}."
    if entry["id"] == "food_availability":
        return "Food is available and completely free for eligible participants."

    if entry.get("food_field") == "price_status":
        normalized_question = question.casefold()
        named_meals = [
            meal
            for meal in ("Breakfast", "Lunch", "Evening Snacks", "Dinner")
            if re.search(rf"\b{re.escape(meal.casefold())}\b", normalized_question)
            or (
                meal == "Evening Snacks"
                and re.search(r"\bsnacks?\b", normalized_question)
            )
        ]
        if named_meals:
            return "\n".join(
                _meal_price_answer(entry, meal, question)
                for meal in named_meals
            )
        if re.search(
            r"\b(?:pay|paid|charge|charged|cost|costs|price|pricing|money)\b",
            question.casefold(),
        ) and not re.search(
            r"\b(?:free|complimentary|without paying)\b",
            question.casefold(),
        ):
            return "No! All food is completely free for eligible participants. Enjoy your meals! 😊"
        return "Yes! All food is completely free for eligible participants. Enjoy your meals! 😊"

    if entry.get("food_field") == "items":
        normalized_question = question.casefold()
        named_meals = [
            meal
            for meal in ("Breakfast", "Lunch", "Evening Snacks", "Dinner")
            if re.search(rf"\b{re.escape(meal.casefold())}\b", normalized_question)
            or (
                meal == "Evening Snacks"
                and re.search(r"\bsnacks?\b", normalized_question)
            )
        ]
        published_meals = [
            facility for facility in food_facilities
            if facility.get("facility_type")
            in (named_meals or {"Breakfast", "Lunch", "Evening Snacks", "Dinner"})
        ]
        item_answers = [
            f"{facility['facility_type']} items: {facility['items']}."
            for facility in published_meals
            if isinstance(facility.get("items"), str)
            and facility["items"].strip()
            and facility["items"].casefold() != "not announced yet"
        ]
        if item_answers:
            return "\n".join(item_answers)
        return entry["answer"]

    facility = _published_facility(entry, food_facilities, question)
    if not facility:
        return entry["answer"]

    facility_type = entry["food_facility"]
    field = entry["food_field"]
    if field == "timing":
        start = _format_food_time(facility.get("start_time"))
        end = _format_food_time(facility.get("end_time"))
        timing = facility.get("timing")
        if start or end:
            value = f"{start or ''} to {end or ''}".strip()
        elif isinstance(timing, str) and timing.casefold() != "not announced yet":
            value = timing
        else:
            return entry["answer"]
        return f"{facility_type} is scheduled from {value}."

    if field == "availability":
        if facility_type == "Drinking Water":
            return "Yes! Drinking water is available throughout the event. 💧"
        if facility_type == "beverages":
            normalized_question = question.casefold()
            requested = [
                candidate
                for candidate in ("Tea Stall", "Coffee Stall", "Other Beverages")
                if any(
                    alias in normalized_question
                    for alias in {
                        "Tea Stall": ("tea",),
                        "Coffee Stall": ("coffee",),
                        "Other Beverages": ("beverage", "drink"),
                    }[candidate]
                )
            ]
            requested_facilities = [
                candidate for candidate in food_facilities
                if candidate.get("facility_type") in requested
            ]
            if not requested_facilities:
                return entry["answer"]
            answers = []
            for candidate in requested_facilities:
                availability = candidate.get("availability")
                if (
                    not isinstance(availability, str)
                    or not availability.strip()
                    or availability.casefold() == "not announced yet"
                ):
                    availability = "not officially announced"
                answers.append(
                    f"{candidate['facility_type']} availability: {availability}."
                )
            return "\n".join(answers)
        if facility.get("availability") == "Available":
            return entry["answer"]
        if facility.get("availability") == "Unavailable":
            return "Drinking water availability has changed. Please check the latest event updates."
        return entry["answer"]
    return entry["answer"]


def get_faq_reply(question, food_facilities=(), tracks=None):
    clauses = re.split(
        r"[?;]+|\band\s+(?=(?:what|when|where|how|is|are|can|will|do|does)\b)",
        question,
        flags=re.IGNORECASE,
    )
    if len(clauses) > 1:
        replies = []
        for clause in clauses:
            reply = get_faq_reply(clause.strip(), food_facilities, tracks) if clause.strip() else None
            if reply and reply not in replies:
                replies.append(reply)
        if replies:
            return "\n".join(replies)

    food_policy_reply = _confirmed_food_policy_reply(question)
    if food_policy_reply is not None:
        return food_policy_reply

    has_multiple_questions = len(re.findall(r"[?;]", question)) > 1
    has_multiple_facts = re.search(r"\b(?:and|also|plus)\b", question.casefold())
    matches = match_faqs(
        question,
        min_score=0.6 if has_multiple_questions or has_multiple_facts else 0.72,
    )
    if not matches:
        return None
    answers = []
    for _, entry in matches:
        answer = _resolve_food_answer(entry, food_facilities, question, tracks)
        if answer not in answers:
            answers.append(answer)
    return "\n".join(answers)


def retrieve_faq_context(question, food_facilities=(), tracks=None):
    matches = match_faqs(question, min_score=0.5)
    sections = []
    for _, entry in matches:
        answer = _resolve_food_answer(entry, food_facilities, question, tracks)
        sections.append(f"{entry['category']} ({entry['id']}): {answer}")
    return "\n".join(sections)
