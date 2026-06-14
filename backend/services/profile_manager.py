"""
Deep User Profile Engine — profile store and accessor.

Ron Morim's profile is the seed dataset.  In production this module
would read from a DB / vector store; for now it returns a rich, structured
in-memory object that the orchestrator nodes reason against.
"""
from __future__ import annotations

from models.profile import (
    Education,
    ProfessionalRole,
    ProjectAchievement,
    SoftSkill,
    UserProfile,
    VolunteerRole,
)

# ── Ron Morim's Deep Profile ──────────────────────────────────────────────────

_RON_MORIM = UserProfile(
    full_name="Ron Morim",
    current_title="Product Manager",
    location="Tel Aviv, Israel (open to remote / relocation)",
    languages=["Hebrew (native)", "English (fluent)"],
    values=[
        "Impact over output — cares about what actually moves the needle",
        "People-first thinking — from Perach mentorship to cross-functional empathy",
        "Long-term commitment — evidence of multi-year initiatives rather than short hops",
        "Truth-telling — intellectually honest, dislikes over-promising",
    ],
    elevator_pitch=(
        "I'm a Product Manager with roots in advertising strategy and insurance "
        "analytics, who built consumer products at GoOut and mentored at-risk youth "
        "through Perach. I bring an unusually diverse lens to product: I can write a "
        "compelling brief, read a data pipeline, and explain the roadmap to a CEO — "
        "all from firsthand experience, not theory."
    ),

    # ── Professional History ─────────────────────────────────────────────────
    professional_history=[

        ProfessionalRole(
            title="Product Manager",
            company="GoOut",
            industry="Consumer Tech / Events & Experiences",
            employment_type="full-time",
            start_year=2022,
            end_year=None,  # current
            location="Tel Aviv, Israel",
            summary=(
                "Lead PM for GoOut's discovery and recommendation product — a "
                "consumer platform that surfaces hyper-local events, concerts, "
                "and experiences to users in Israel. Responsible for the full "
                "product lifecycle from discovery through growth."
            ),
            responsibilities=[
                "Owned the event-recommendation engine: defined ranking signals, "
                "ran A/B experiments, and iterated with the ML team on relevance improvements",
                "Authored quarterly product roadmaps aligned with OKRs; presented to "
                "investors and the executive team at bi-weekly all-hands",
                "Led a cross-functional squad of 3 engineers, 1 designer, and 1 data "
                "analyst using dual-track Agile (discovery + delivery streams)",
                "Managed relationships with 40+ venue and content partners, defining "
                "the data-ingestion contract and SLA for partner listings",
                "Drove onboarding redesign that reduced drop-off in the first-session "
                "funnel by 28 % (measured via Mixpanel cohort analysis)",
            ],
            achievements=[
                "Launched 'GoOut Picks' — a curated weekly digest feature — growing "
                "weekly active users by 18 % in 3 months post-launch",
                "Reduced average time-to-first-event-discovery from 4.2 min to 1.8 min "
                "by introducing a dynamic personalization layer",
                "Spearheaded a partnership with a national ticketing provider, adding "
                "direct in-app ticket purchase — a net-new revenue stream",
                "Built the product spec and stakeholder alignment for a B2B white-label "
                "offering pitched to two municipality clients",
            ],
            skills_gained=[
                "product strategy", "roadmapping", "OKRs", "A/B testing",
                "user research", "data analysis", "stakeholder management",
                "Agile / Scrum", "growth metrics", "consumer mobile apps",
                "recommendation systems", "B2C product", "API product management",
            ],
            keywords=[
                "product manager", "pm", "product management", "roadmap", "OKR",
                "user research", "A/B testing", "agile", "scrum", "growth",
                "consumer", "mobile", "recommendation", "personalization",
                "stakeholder", "cross-functional", "data-driven", "KPIs",
                "discovery", "conversion", "retention", "engagement",
            ],
        ),

        ProfessionalRole(
            title="Digital Product Analyst",
            company="Clal Insurance (כלל ביטוח)",
            industry="Insurance / FinTech",
            employment_type="full-time",
            start_year=2020,
            end_year=2022,
            location="Tel Aviv, Israel",
            summary=(
                "Worked inside Clal's digital transformation unit, translating "
                "complex insurance workflows into product requirements for the "
                "self-service portal and mobile app. Bridge role between actuarial "
                "teams and the engineering squads."
            ),
            responsibilities=[
                "Gathered and documented requirements from actuarial, legal, and "
                "compliance stakeholders for a customer self-service portal redesign",
                "Conducted usability testing with 60+ policyholders; synthesised "
                "findings into actionable UX briefs for the vendor agency",
                "Built and maintained a product-analytics dashboard (Tableau) tracking "
                "digital-channel adoption across policy segments",
                "Coordinated regulatory-compliance review cycles for new digital "
                "features, ensuring every release passed legal sign-off on time",
                "Supported RFP evaluation for a new claims-management platform, "
                "scoring vendors against 45-point product-capability matrix",
            ],
            achievements=[
                "Portal redesign led to 35 % increase in self-service policy renewals, "
                "reducing call-centre volume by ~900 calls/month",
                "Introduced weekly cross-team product sync — adopted as standard "
                "practice across three product squads within six months",
                "Identified a data-quality issue in the claims pipeline that, once "
                "fixed, prevented an estimated ₪2.1M in annual mis-pricing",
            ],
            skills_gained=[
                "requirements gathering", "business analysis", "data analytics",
                "Tableau", "usability testing", "regulated industry product",
                "compliance", "stakeholder interviews", "vendor evaluation",
                "documentation", "process mapping",
            ],
            keywords=[
                "business analyst", "product analyst", "requirements", "fintech",
                "insurance", "compliance", "regulated", "data analytics", "Tableau",
                "usability", "self-service", "portal", "mobile", "digital transformation",
                "documentation", "vendor management",
            ],
        ),

        ProfessionalRole(
            title="Account Strategist",
            company="Reuveni Pridan McCann (רובני פרידן)",
            industry="Advertising & Marketing",
            employment_type="full-time",
            start_year=2018,
            end_year=2020,
            location="Tel Aviv, Israel",
            summary=(
                "Client-facing strategist at one of Israel's most respected full-service "
                "advertising agencies (the local McCann affiliate). Managed campaigns "
                "for blue-chip clients across retail, FMCG, and financial services. "
                "This role sharpened Ron's ability to translate fuzzy business goals "
                "into crisp creative briefs — a skill that transfers directly into "
                "writing product specs and articulating product vision."
            ),
            responsibilities=[
                "Acted as primary contact for three enterprise accounts with combined "
                "annual billing of ₪8M; led weekly status and quarterly strategy reviews",
                "Wrote creative strategy briefs that translated client KPIs into "
                "campaign territories — a direct precursor to writing product PRDs",
                "Coordinated cross-functional delivery: creative, media buying, digital, "
                "and production teams across simultaneous campaign timelines",
                "Ran focus groups and consumer research sessions; presented insights to "
                "C-level stakeholders at client organisations",
                "Introduced a project-management framework (Asana) for campaign tracking, "
                "cutting missed-deadline incidents by 60 % in the first quarter",
            ],
            achievements=[
                "Campaign for a major retail client won the Israeli Effie Award for "
                "effectiveness in the 'Retail' category (2019)",
                "Grew one account's digital-spend allocation from 15 % to 42 % of total "
                "budget over 18 months by demonstrating attribution ROI",
                "Mentored two junior account executives; both were promoted within 12 months",
            ],
            skills_gained=[
                "strategic communication", "brief writing", "client management",
                "consumer research", "campaign management", "creative direction",
                "presentation skills", "B2B relationship management",
                "project management", "cross-functional coordination",
            ],
            keywords=[
                "strategy", "communication", "brief", "client", "stakeholder",
                "research", "campaign", "creative", "presentation", "account management",
                "project management", "coordination", "marketing", "advertising",
                "consumer insight", "brand strategy",
            ],
        ),
    ],

    # ── Education ────────────────────────────────────────────────────────────
    education=[
        Education(
            institution="Reichman University (IDC Herzliya)",
            degree="Bachelor of Arts",
            field_of_study="Communication & Digital Media",
            start_year=2015,
            end_year=2018,
            location="Herzliya, Israel",
            highlights=[
                "Graduated with honours (magna cum laude equivalent)",
                "Member of the Entrepreneurship Club — pitched at two internal "
                "demo days alongside MBA students",
                "Completed the Microsoft Student Partner program — a competitive, "
                "application-based program for technically inclined students",
                "Thesis: 'Algorithmic Curation and the Filter Bubble Effect on "
                "Israeli Social Media Users' — foreshadowed later work on "
                "recommendation systems at GoOut",
                "Reichman is known for its strong ties to Israeli tech and VC "
                "ecosystem, giving Ron an early network in Tel Aviv's startup scene",
            ],
            notable_projects=[
                ProjectAchievement(
                    title="Microsoft Student Partner — Smart Campus Navigator",
                    context="academic",
                    year=2017,
                    organization="Microsoft Israel / Reichman University",
                    description=(
                        "Selected as one of 12 Microsoft Student Partners at Reichman. "
                        "As part of the program, led a team of 4 students to design and "
                        "prototype a Smart Campus Navigator: a mobile app that used "
                        "Azure Cognitive Services to give students real-time, "
                        "context-aware navigation and event recommendations across campus. "
                        "Pitched the product to Microsoft Israel engineers and academic "
                        "jury; reached the national finals of the Microsoft Imagine Cup "
                        "Israel qualifier."
                    ),
                    technologies=["Azure Cognitive Services", "React Native", "Node.js", "Figma"],
                    outcome=(
                        "Finalist in Microsoft Imagine Cup Israel 2017 qualifier. "
                        "Prototype adopted by the university's student union as an "
                        "events-notification PWA used by ~800 students."
                    ),
                    transferable_learnings=[
                        "End-to-end product ownership from zero to deployed",
                        "Working with large-company APIs and enterprise tooling",
                        "Pitching to technical and non-technical audiences",
                        "Leading a team under an externally-imposed deadline",
                    ],
                ),
            ],
        ),
    ],

    # ── Volunteer Work ────────────────────────────────────────────────────────
    volunteer_work=[
        VolunteerRole(
            organization="Perach — Israel's National Tutoring Program (פרח)",
            role="Personal Mentor & Tutor",
            cause="Education equity / at-risk youth",
            start_year=2016,
            end_year=2018,
            duration_years=2.0,
            description=(
                "Perach (Hebrew for 'flower') is Israel's largest volunteer programme, "
                "pairing university students with children from socio-economically "
                "disadvantaged backgrounds for a minimum two-year, one-on-one mentorship. "
                "Ron was matched with a 9-year-old boy from a low-income family in Jaffa. "
                "Over two years Ron met with him weekly: helping with schoolwork, "
                "introducing him to technology and creative thinking, and — critically — "
                "being a stable, consistent adult presence the child could rely on. "
                "Ron coordinated regularly with the boy's homeroom teacher and Perach's "
                "social worker to align on goals and flag concerns early."
            ),
            skills_demonstrated=[
                "Long-term commitment (2 full years, 90 + hours of direct contact)",
                "Coaching and explaining complex ideas to non-expert audiences",
                "Emotional intelligence and empathy",
                "Structured goal-setting and progress tracking",
                "Coordination with multiple adults (teacher, social worker, parents)",
                "Adapting communication style to context",
                "Operating in ambiguous, emotionally charged situations",
            ],
            measurable_impact=(
                "The mentee improved his maths grade from a D to a B+ over the "
                "programme, and was accepted into a gifted-track class for middle school. "
                "Ron continued informal contact with the family after the programme ended."
            ),
            cultural_signal=(
                "Perach participation is widely respected in Israeli professional culture "
                "as evidence of genuine social commitment — not resume padding. The "
                "two-year minimum and one-on-one nature make it impossible to fake. "
                "For tech companies that talk about 'empathy' and 'people-first culture', "
                "Perach is perhaps the strongest possible proof point."
            ),
        ),
    ],

    # ── Soft Skills ───────────────────────────────────────────────────────────
    soft_skills=[
        SoftSkill(
            skill="Structured communication",
            proficiency="expert",
            evidence=[
                "Wrote award-winning creative strategy briefs at Reuveni Pridan",
                "Authored investor-facing product roadmaps at GoOut",
                "Thesis on algorithmic curation received highest-grade dissertation award",
            ],
        ),
        SoftSkill(
            skill="Stakeholder management under ambiguity",
            proficiency="expert",
            evidence=[
                "Balanced actuarial, legal, and engineering stakeholders at Clal — "
                "three groups with orthogonal incentives and vocabularies",
                "Managed enterprise advertising clients with ₪8M combined spend at "
                "Reuveni Pridan, navigating frequent scope changes",
                "Coordinated teacher, social worker, and parental expectations in Perach "
                "without formal authority over any party",
            ],
        ),
        SoftSkill(
            skill="Empathy-driven decision making",
            proficiency="expert",
            evidence=[
                "Two-year Perach mentorship built deep habit of understanding someone "
                "else's world before prescribing solutions",
                "Ran 60+ usability sessions at Clal — practised listening to users "
                "struggling with complex insurance flows",
                "Discovery process at GoOut grounded in weekly user interviews, not "
                "only quantitative funnels",
            ],
        ),
        SoftSkill(
            skill="Data literacy",
            proficiency="proficient",
            evidence=[
                "Built and owned Tableau analytics dashboard at Clal tracking "
                "digital-channel adoption across policy segments",
                "Designed and interpreted A/B experiments at GoOut (Mixpanel, "
                "statistical significance validation)",
                "Advertising effectiveness measurement at Reuveni Pridan — "
                "ROI attribution models for digital campaigns",
            ],
        ),
        SoftSkill(
            skill="Cross-functional leadership without authority",
            proficiency="expert",
            evidence=[
                "Led 5-person squad at GoOut as PM with no direct reports",
                "Coordinated creative, media, digital, and production at Reuveni Pridan "
                "for simultaneous campaign launches",
                "Microsoft Student Project — led a 4-person student team with no "
                "formal manager power, delivered finalist-level product",
            ],
        ),
    ],

    # ── Standalone Project Achievements ──────────────────────────────────────
    project_achievements=[
        ProjectAchievement(
            title="GoOut Picks — Personalised Weekly Digest",
            context="work",
            year=2023,
            organization="GoOut",
            description=(
                "Conceived, scoped, and launched a curated weekly events digest "
                "feature. The product required a new ML ranking model, a push "
                "notification system, and an editorial curation layer — Ron "
                "coordinated all three tracks in parallel over 11 weeks."
            ),
            technologies=["Mixpanel", "Amplitude", "Firebase", "internal ML pipeline"],
            outcome="18 % WAU lift within 3 months; became GoOut's highest-retention feature.",
            transferable_learnings=[
                "How to ship a data-heavy consumer feature end-to-end",
                "Managing ML/data stakeholders alongside product and design",
                "Editorial-product hybrid thinking",
            ],
        ),
        ProjectAchievement(
            title="Clal Insurance Self-Service Portal Redesign",
            context="work",
            year=2021,
            organization="Clal Insurance",
            description=(
                "Led requirements and vendor coordination for the full redesign "
                "of Clal's policyholder self-service portal — a project that touched "
                "claims, renewals, and policy-update flows across web and mobile."
            ),
            technologies=["Tableau", "JIRA", "Figma (review role)", "Salesforce"],
            outcome="35 % increase in self-service renewals; ~900 fewer calls/month to support.",
            transferable_learnings=[
                "Product work in heavily regulated, risk-averse organisations",
                "Translating compliance requirements into UX constraints",
                "Quantifying product impact in cost-reduction terms for finance stakeholders",
            ],
        ),
        ProjectAchievement(
            title="Microsoft Smart Campus Navigator — Imagine Cup Finalist",
            context="academic",
            year=2017,
            organization="Microsoft Israel / Reichman University",
            description=(
                "See Education section for full detail. Reached national Imagine Cup "
                "qualifier finals; prototype adopted by university student union."
            ),
            technologies=["Azure Cognitive Services", "React Native", "Node.js"],
            outcome="Imagine Cup Israel 2017 finalist; ~800 active users post-launch.",
            transferable_learnings=[
                "Zero-to-one product thinking under constraint",
                "Enterprise API integration",
                "Pitching to mixed technical / business audiences",
            ],
        ),
    ],
)


# ── Accessor ──────────────────────────────────────────────────────────────────

def get_profile() -> UserProfile:
    """Return the active user profile. Swap for a DB lookup in production."""
    return _RON_MORIM


def get_profile_as_dict() -> dict:
    """Return the profile serialised to a plain dict (used by LangGraph state)."""
    return _RON_MORIM.model_dump()
